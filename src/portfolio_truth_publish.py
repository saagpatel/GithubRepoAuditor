from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from src.portfolio_truth_render import render_portfolio_report_markdown, render_registry_markdown
from src.portfolio_truth_validate import (
    validate_portfolio_report_markdown,
    validate_publish_targets,
    validate_registry_markdown,
    validate_truth_snapshot,
)


@dataclass(frozen=True)
class PortfolioTruthPublishResult:
    snapshot_path: Path
    latest_path: Path
    registry_output: Path
    portfolio_report_output: Path
    project_count: int
    registry_changed: bool
    report_changed: bool


def publish_portfolio_truth(
    *,
    workspace_root: Path,
    output_dir: Path,
    registry_output: Path,
    portfolio_report_output: Path,
    catalog_path: Path | None = None,
    legacy_registry_path: Path | None = None,
    include_notion: bool = True,
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
    )
    validate_truth_snapshot(build_result.snapshot)

    snapshot_stamp = build_result.snapshot.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_path = output_dir / f"portfolio-truth-{snapshot_stamp}.json"
    latest_path = output_dir / "portfolio-truth-latest.json"
    latest_name = latest_path.name
    snapshot_json = json.dumps(build_result.snapshot.to_dict(), indent=2) + "\n"
    registry_markdown = render_registry_markdown(build_result.snapshot)
    report_markdown = render_portfolio_report_markdown(build_result.snapshot, latest_name)

    with tempfile.NamedTemporaryFile("w", delete=False, dir=output_dir, suffix=".registry-check.md") as handle:
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
    }
    changed: dict[Path, bool] = {
        registry_output: _content_changed(registry_output, registry_markdown),
        portfolio_report_output: _content_changed(portfolio_report_output, report_markdown),
        snapshot_path: True,
        latest_path: True,
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
    )


def _stage_text(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=target.parent, suffix=f".{target.name}.tmp") as handle:
        handle.write(content)
        return Path(handle.name)


def _content_changed(path: Path, content: str) -> bool:
    if not path.exists():
        return True
    return path.read_text() != content
