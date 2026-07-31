from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.portfolio_truth_reconcile import (
    build_portfolio_truth_snapshot,
    load_prior_notion_context,
)
from src.portfolio_truth_render import render_portfolio_report_markdown, render_registry_markdown
from src.portfolio_truth_lineage import resolve_notion_origin
from src.portfolio_truth_types import truth_latest_path
from src.producer_preflight import ProducerEvidence, verify_evidence_still_current
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
_PUBLISH_JOURNAL_NAME = ".portfolio-truth-publish-journal.json"


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
    allow_empty_notion: bool = False,
    release_count_by_name: dict[str, int] | None = None,
    security_alerts_by_name: dict[str, dict] | None = None,
    security_coverage_metadata: dict[str, object] | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
    producer_evidence: ProducerEvidence | None = None,
    producer_repo_root: Path | None = None,
    require_producer_evidence: bool = False,
) -> PortfolioTruthPublishResult:
    if require_producer_evidence and producer_evidence is None:
        raise PortfolioTruthPublishError(
            "Canonical publication requires validated producer evidence."
        )
    if producer_evidence is not None:
        if producer_repo_root is None:
            raise PortfolioTruthPublishError(
                "producer_repo_root is required with producer evidence."
            )
        try:
            verify_evidence_still_current(producer_repo_root, producer_evidence)
        except ValueError as exc:
            raise PortfolioTruthPublishError(str(exc)) from exc
    validate_publish_targets(
        workspace_root=workspace_root,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
    )
    latest_path = truth_latest_path(output_dir)
    project_registry_path = output_dir / "project-registry.json"
    _recover_interrupted_publication(
        output_dir,
        allowed_targets={latest_path, registry_output, portfolio_report_output, project_registry_path},
    )
    notion_context_fallback = (
        load_prior_notion_context(latest_path) if allow_empty_notion else None
    )
    prior_notion_generated_at = resolve_notion_origin(latest_path)
    build_result = build_portfolio_truth_snapshot(
        workspace_root=workspace_root,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=include_notion,
        notion_context_fallback=notion_context_fallback,
        release_count_by_name=release_count_by_name,
        security_alerts_by_name=security_alerts_by_name,
        security_coverage_metadata=security_coverage_metadata,
        repo_status_by_name=repo_status_by_name,
        producer=producer_evidence.to_dict() if producer_evidence else {},
        prior_notion_generated_at=prior_notion_generated_at,
    )
    validate_truth_snapshot(build_result.snapshot)
    if producer_evidence is not None and producer_repo_root is not None:
        try:
            verify_evidence_still_current(producer_repo_root, producer_evidence)
        except ValueError as exc:
            raise PortfolioTruthPublishError(str(exc)) from exc

    snapshot_stamp = build_result.snapshot.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_path = output_dir / f"portfolio-truth-{snapshot_stamp}.json"
    _guard_against_notion_context_drop(
        build_result.snapshot.source_summary,
        latest_path=latest_path,
        include_notion=include_notion,
        allow_empty_notion=allow_empty_notion,
    )
    latest_name = latest_path.name
    snapshot_json = json.dumps(build_result.snapshot.to_dict(), indent=2) + "\n"
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
    backups = {
        path: (_stage_bytes(path, path.read_bytes()) if path.exists() else None)
        for path in targets
    }
    journal_path = output_dir / _PUBLISH_JOURNAL_NAME
    _write_publish_journal(journal_path, temp_files=temp_files, backups=backups)

    try:
        for path, staged in temp_files.items():
            if path in {registry_output, portfolio_report_output} and not changed[path]:
                continue
            staged.replace(path)
    except BaseException:
        _recover_interrupted_publication(
            output_dir,
            allowed_targets={
                latest_path,
                registry_output,
                portfolio_report_output,
                project_registry_path,
            },
        )
        raise

    _cleanup_publish_transaction(journal_path, temp_files.values(), backups.values())

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
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _stage_bytes(target: Path, content: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", delete=False, dir=target.parent, suffix=f".{target.name}.bak"
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_publish_journal(
    journal_path: Path,
    *,
    temp_files: dict[Path, Path],
    backups: dict[Path, Path | None],
) -> None:
    journal_targets: list[dict[str, object]] = []
    for target in temp_files:
        backup = backups[target]
        journal_targets.append(
            {
                "target": str(target.resolve()),
                "staged": str(temp_files[target].resolve()),
                "backup": str(backup.resolve()) if backup is not None else None,
                "existed": backup is not None,
            }
        )
    payload = {
        "schema": "PortfolioTruthPublishJournalV1",
        "targets": journal_targets,
    }
    staged_journal = _stage_text(
        journal_path, json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    staged_journal.replace(journal_path)
    _fsync_directory(journal_path.parent)


def _allowed_recovery_target(
    target: Path, *, output_dir: Path, allowed_targets: set[Path]
) -> bool:
    resolved = target.resolve()
    if resolved in {path.resolve() for path in allowed_targets}:
        return True
    return (
        resolved.parent == output_dir.resolve()
        and resolved.name.startswith("portfolio-truth-")
        and resolved.name.endswith(".json")
        and resolved.name != "portfolio-truth-latest.json"
    )


def _recover_interrupted_publication(
    output_dir: Path, *, allowed_targets: set[Path]
) -> None:
    journal_path = output_dir / _PUBLISH_JOURNAL_NAME
    if not journal_path.exists():
        return
    try:
        payload = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortfolioTruthPublishError(
            f"Cannot recover interrupted publication: invalid journal {journal_path}"
        ) from exc
    if payload.get("schema") != "PortfolioTruthPublishJournalV1":
        raise PortfolioTruthPublishError(
            f"Cannot recover interrupted publication: unsupported journal {journal_path}"
        )
    rows = payload.get("targets")
    if not isinstance(rows, list):
        raise PortfolioTruthPublishError(
            f"Cannot recover interrupted publication: malformed journal {journal_path}"
        )

    staged_paths: list[Path] = []
    backup_paths: list[Path] = []
    for row in rows:
        if not isinstance(row, dict):
            raise PortfolioTruthPublishError(
                f"Cannot recover interrupted publication: malformed journal {journal_path}"
            )
        target = Path(str(row.get("target", "")))
        staged = Path(str(row.get("staged", "")))
        backup_value = row.get("backup")
        backup = Path(str(backup_value)) if backup_value else None
        if not _allowed_recovery_target(
            target, output_dir=output_dir, allowed_targets=allowed_targets
        ):
            raise PortfolioTruthPublishError(
                f"Cannot recover interrupted publication target outside contract: {target}"
            )
        if staged.resolve().parent != target.resolve().parent:
            raise PortfolioTruthPublishError(
                f"Cannot recover interrupted publication: invalid staged path for {target}"
            )
        if backup is not None and backup.resolve().parent != target.resolve().parent:
            raise PortfolioTruthPublishError(
                f"Cannot recover interrupted publication: invalid backup path for {target}"
            )
        if backup is None:
            target.unlink(missing_ok=True)
        else:
            if not backup.exists():
                raise PortfolioTruthPublishError(
                    f"Cannot recover interrupted publication: backup missing for {target}"
                )
            restored = _stage_bytes(target, backup.read_bytes())
            restored.replace(target)
            backup_paths.append(backup)
        staged_paths.append(staged)
        _fsync_directory(target.parent)

    _cleanup_publish_transaction(journal_path, staged_paths, backup_paths)


def _cleanup_publish_transaction(
    journal_path: Path,
    staged_paths: Iterable[Path],
    backup_paths: Iterable[Path | None],
) -> None:
    for path in staged_paths:
        path.unlink(missing_ok=True)
    for backup_path in backup_paths:
        if backup_path is not None:
            backup_path.unlink(missing_ok=True)
    journal_path.unlink(missing_ok=True)
    if journal_path.parent.exists():
        _fsync_directory(journal_path.parent)


def _content_changed(path: Path, content: str) -> bool:
    if not path.exists():
        return True
    return path.read_text() != content


def _guard_against_notion_context_drop(
    source_summary: dict[str, object],
    *,
    latest_path: Path,
    include_notion: bool,
    allow_empty_notion: bool = False,
) -> None:
    """Avoid overwriting local truth when Notion bootstrap silently disappears."""
    if allow_empty_notion:
        # Operator explicitly opted into publishing without live Notion (a headless or
        # scheduled refresh); prior advisory is carried forward where available.
        return
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
