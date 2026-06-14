from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from src.portfolio_truth_render import render_portfolio_report_markdown, render_registry_markdown
from src.portfolio_truth_types import truth_latest_path
from src.portfolio_truth_validate import (
    validate_portfolio_report_markdown,
    validate_publish_targets,
    validate_registry_markdown,
    validate_truth_snapshot,
)
from src.project_registry import build_project_registry, load_source_paths


@dataclass(frozen=True)
class PortfolioTruthPublishResult:
    snapshot_path: Path
    latest_path: Path
    registry_output: Path
    portfolio_report_output: Path
    project_count: int
    registry_changed: bool
    report_changed: bool
    project_registry_path: Path | None = None


class PortfolioTruthPublishError(RuntimeError):
    """Raised when publishing would corrupt or misrepresent portfolio truth."""


_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _REPO_ROOT / "config"


def _build_project_registry_json(snapshot, *, include_notion: bool) -> str:
    """Render the canonical cross-store project registry from a snapshot.

    External sources (bridge-db, Notion snapshot, memory) degrade gracefully
    when absent, so this never fails the publish run.
    """
    overrides_config_path = _CONFIG_DIR / "project-registry-overrides.json"
    sources = load_source_paths(overrides_config_path)

    scoring_pageids: dict[str, str] = {}
    if include_notion and sources.get("scoring_data_source_id"):
        try:
            from src.notion_client import get_notion_token
            from src.project_registry import fetch_scoring_pageids

            token = get_notion_token()
            if token:
                scoring_pageids = fetch_scoring_pageids(
                    str(sources["scoring_data_source_id"]), token
                )
        except Exception:
            scoring_pageids = {}

    registry = build_project_registry(
        snapshot.to_dict(),
        bridge_db_path=sources["bridge_db"],
        notion_snapshot_path=sources["notion_snapshot"],
        notion_project_map_path=_CONFIG_DIR / "notion-project-map.json",
        memory_dir=sources["memory_dir"],
        scoring_pageids=scoring_pageids,
        overrides_config_path=overrides_config_path,
        generated_at=snapshot.generated_at,
    )
    return json.dumps(registry, indent=2) + "\n"


def publish_portfolio_truth(
    *,
    workspace_root: Path,
    output_dir: Path,
    registry_output: Path,
    portfolio_report_output: Path,
    catalog_path: Path | None = None,
    legacy_registry_path: Path | None = None,
    include_notion: bool = True,
    release_count_by_name: dict[str, int] | None = None,
    security_alerts_by_name: dict[str, dict] | None = None,
) -> PortfolioTruthPublishResult:
    validate_publish_targets(
        workspace_root=workspace_root,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
    )
    build_result = build_portfolio_truth_snapshot(
        workspace_root=workspace_root,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=include_notion,
        release_count_by_name=release_count_by_name,
        security_alerts_by_name=security_alerts_by_name,
    )
    validate_truth_snapshot(build_result.snapshot)

    snapshot_stamp = build_result.snapshot.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_path = output_dir / f"portfolio-truth-{snapshot_stamp}.json"
    latest_path = truth_latest_path(output_dir)
    _guard_against_notion_context_drop(
        build_result.snapshot.source_summary,
        latest_path=latest_path,
        include_notion=include_notion,
    )
    latest_name = latest_path.name
    snapshot_json = json.dumps(build_result.snapshot.to_dict(), indent=2) + "\n"
    project_registry_path = output_dir / "project-registry.json"
    project_registry_json = _build_project_registry_json(
        build_result.snapshot, include_notion=include_notion
    )
    registry_markdown = render_registry_markdown(build_result.snapshot)
    report_markdown = render_portfolio_report_markdown(build_result.snapshot, latest_name)

    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=output_dir, suffix=".registry-check.md"
    ) as handle:
        temp_registry_path = Path(handle.name)
    try:
        validate_registry_markdown(registry_markdown, build_result.snapshot, temp_registry_path)
        validate_portfolio_report_markdown(report_markdown)
    finally:
        if temp_registry_path.exists():
            temp_registry_path.unlink()

    targets = {
        snapshot_path: snapshot_json,
        latest_path: snapshot_json,
        registry_output: registry_markdown,
        portfolio_report_output: report_markdown,
        project_registry_path: project_registry_json,
    }
    changed: dict[Path, bool] = {
        registry_output: _content_changed(registry_output, registry_markdown),
        portfolio_report_output: _content_changed(portfolio_report_output, report_markdown),
        snapshot_path: True,
        latest_path: True,
        project_registry_path: True,
    }
    temp_files = {path: _stage_text(path, content) for path, content in targets.items()}
    originals = {path: (path.read_text() if path.exists() else None) for path in targets}
    published: list[Path] = []

    try:
        for path, staged in temp_files.items():
            if path in {registry_output, portfolio_report_output} and not changed[path]:
                staged.unlink(missing_ok=True)
                continue
            staged.replace(path)
            published.append(path)
    except Exception:
        for path in reversed(published):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(original)
        for staged in temp_files.values():
            staged.unlink(missing_ok=True)
        raise

    for staged in temp_files.values():
        staged.unlink(missing_ok=True)

    return PortfolioTruthPublishResult(
        snapshot_path=snapshot_path,
        latest_path=latest_path,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
        project_count=len(build_result.snapshot.projects),
        registry_changed=changed[registry_output],
        report_changed=changed[portfolio_report_output],
        project_registry_path=project_registry_path,
    )


def _stage_text(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=target.parent, suffix=f".{target.name}.tmp"
    ) as handle:
        handle.write(content)
        return Path(handle.name)


def _content_changed(path: Path, content: str) -> bool:
    if not path.exists():
        return True
    return path.read_text() != content


def _guard_against_notion_context_drop(
    source_summary: dict[str, object],
    *,
    latest_path: Path,
    include_notion: bool,
) -> None:
    """Avoid overwriting local truth when Notion bootstrap silently disappears."""
    if not include_notion or not _notion_project_context_configured():
        return
    current_rows = _int_value(source_summary.get("notion_context_rows"))
    if current_rows != 0:
        return
    previous_rows = _previous_notion_context_rows(latest_path)
    if previous_rows is None or previous_rows <= 0:
        return
    raise PortfolioTruthPublishError(
        "Refusing to publish portfolio truth with 0 Notion context rows because "
        f"{latest_path} currently has {previous_rows}. Load NOTION_TOKEN or run "
        "with an explicit no-Notion path before replacing local portfolio truth."
    )


def _notion_project_context_configured() -> bool:
    path = _CONFIG_DIR / "notion-config.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(str(data.get("projects_data_source_id", "")).strip())


def _previous_notion_context_rows(latest_path: Path) -> int | None:
    try:
        data = json.loads(latest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    source_summary = data.get("source_summary", {})
    if not isinstance(source_summary, dict):
        return None
    return _int_value(source_summary.get("notion_context_rows"))


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
