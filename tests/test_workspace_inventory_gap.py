from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from github_repo_auditor.portfolio_truth_publish import (
    _workspace_inventory_gap,
    publish_portfolio_truth,
)


def _make_project(workspace: Path, name: str) -> None:
    path = workspace / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text(f"# {name}\n\nSynthetic inventory fixture.\n")


def _publish(workspace: Path, output: Path, at: datetime) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    result = publish_portfolio_truth(
        workspace_root=workspace,
        output_dir=output,
        registry_output=workspace / "project-registry.md",
        portfolio_report_output=workspace / "PORTFOLIO-AUDIT-REPORT.md",
        catalog_path=workspace.parent / "missing-portfolio-catalog.yaml",
        include_notion=False,
        now=at,
    )
    return json.loads(result.latest_path.read_text(encoding="utf-8"))


def test_workspace_inventory_gap_tracks_disappearance_recovery_and_root_change(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _make_project(workspace, "Alpha")
    _make_project(workspace, "Beta")
    _make_project(workspace, "Gamma")
    output = tmp_path / "output"
    first_at = datetime(2026, 11, 6, 10, tzinfo=timezone.utc)

    first = _publish(workspace, output, first_at)
    assert "workspace_inventory_gap" not in first["source_summary"]
    beta_key = next(
        project["identity"]["project_key"]
        for project in first["projects"]
        if project["identity"]["display_name"] == "Beta"
    )
    gamma_key = next(
        project["identity"]["project_key"]
        for project in first["projects"]
        if project["identity"]["display_name"] == "Gamma"
    )

    shutil.rmtree(workspace / "Beta")
    second = _publish(workspace, output, first_at.replace(minute=1))
    assert second["source_summary"]["workspace_inventory_gap"] == {
        "missing_project_keys": [beta_key],
        "baseline_generated_at": first["generated_at"],
    }

    shutil.rmtree(workspace / "Gamma")
    repeated = _publish(workspace, output, first_at.replace(minute=2))
    assert repeated["source_summary"]["workspace_inventory_gap"] == {
        "missing_project_keys": sorted([beta_key, gamma_key]),
        "baseline_generated_at": first["generated_at"],
    }

    _make_project(workspace, "Beta")
    _make_project(workspace, "Gamma")
    recovered = _publish(workspace, output, first_at.replace(minute=3))
    assert "workspace_inventory_gap" not in recovered["source_summary"]

    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    _make_project(other_workspace, "Alpha")
    different_root = _publish(other_workspace, output, first_at.replace(minute=4))
    assert "workspace_inventory_gap" not in different_root["source_summary"]


def test_workspace_inventory_gap_excludes_supplementary_keys_and_ignores_bad_prior(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    latest = tmp_path / "portfolio-truth-latest.json"
    latest.write_text(
        json.dumps(
            {
                "workspace_root": str(workspace),
                "generated_at": "2026-11-06T10:00:00+00:00",
                "projects": [
                    {"identity": {"project_key": "repo:saagar/alpha"}},
                    {"identity": {"project_key": "supp:calendar"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _workspace_inventory_gap(
        latest, workspace_root=workspace, current_project_keys=set()
    ) == {
        "missing_project_keys": ["repo:saagar/alpha"],
        "baseline_generated_at": "2026-11-06T10:00:00+00:00",
    }

    latest.write_bytes(b"\xff\xfe invalid utf-8")
    assert (
        _workspace_inventory_gap(
            latest, workspace_root=workspace, current_project_keys=set()
        )
        is None
    )
