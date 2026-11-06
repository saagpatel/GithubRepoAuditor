from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from github_repo_auditor.portfolio_truth_publish import (
    _workspace_path_is_directory,
    _workspace_inventory_gap,
    publish_portfolio_truth,
)
from github_repo_auditor.portfolio_truth_validate import (
    _snapshot_from_payload,
    validate_truth_snapshot,
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
    assert first["source_summary"]["workspace_inventory_comparison"] == {
        "state": "first_run",
    }
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

    original_is_dir = Path.is_dir

    def omit_beta(path: Path) -> bool:
        if path == workspace / "Beta":
            return False
        return original_is_dir(path)

    with patch.object(Path, "is_dir", omit_beta):
        second = _publish(workspace, output, first_at.replace(minute=1))
    assert second["source_summary"]["workspace_inventory_gap"] == {
        "missing_project_keys": [beta_key],
        "baseline_generated_at": first["generated_at"],
        "missing_project_paths": {beta_key: "Beta"},
    }

    def omit_beta_and_gamma(path: Path) -> bool:
        if path in {workspace / "Beta", workspace / "Gamma"}:
            return False
        return original_is_dir(path)

    with patch.object(Path, "is_dir", omit_beta_and_gamma):
        repeated = _publish(workspace, output, first_at.replace(minute=2))
    assert repeated["source_summary"]["workspace_inventory_gap"] == {
        "missing_project_keys": sorted([beta_key, gamma_key]),
        "baseline_generated_at": first["generated_at"],
        "missing_project_paths": {beta_key: "Beta", gamma_key: "Gamma"},
    }

    shutil.rmtree(workspace / "Beta")
    shutil.rmtree(workspace / "Gamma")
    deleted = _publish(workspace, output, first_at.replace(minute=3))
    assert "workspace_inventory_gap" not in deleted["source_summary"]

    _make_project(workspace, "Beta")
    _make_project(workspace, "Gamma")
    recovered = _publish(workspace, output, first_at.replace(minute=4))
    assert "workspace_inventory_gap" not in recovered["source_summary"]

    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    _make_project(other_workspace, "Alpha")
    different_root = _publish(other_workspace, output, first_at.replace(minute=5))
    assert "workspace_inventory_gap" not in different_root["source_summary"]
    assert different_root["source_summary"]["workspace_inventory_comparison"] == {
        "state": "unavailable",
        "reason": "workspace_root_changed",
    }


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
        latest,
        workspace_root=workspace,
        current_project_keys=set(),
        current_project_paths=set(),
    ) == (
        {
            "missing_project_keys": ["repo:saagar/alpha"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
        },
        None,
    )

    latest.write_bytes(b"\xff\xfe invalid utf-8")
    assert _workspace_inventory_gap(
        latest,
        workspace_root=workspace,
        current_project_keys=set(),
        current_project_paths=set(),
    ) == (None, "prior_snapshot_unreadable")


@pytest.mark.parametrize(
    "malformed_gap",
    [
        {
            "missing_project_keys": ["Alpha", "Alpha"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
        },
        ["not", "a", "mapping"],
    ],
)
def test_same_root_malformed_gap_marks_comparison_unavailable(
    tmp_path: Path, malformed_gap: object
) -> None:
    workspace = tmp_path / "workspace"
    _make_project(workspace, "Alpha")
    output = tmp_path / "output"
    generated_at = datetime(2026, 11, 6, 10, tzinfo=timezone.utc)
    baseline = _publish(workspace, output, generated_at)
    latest = output / "portfolio-truth-latest.json"
    baseline["source_summary"]["workspace_inventory_gap"] = malformed_gap
    latest.write_text(json.dumps(baseline), encoding="utf-8")

    recovered = _publish(workspace, output, generated_at.replace(minute=1))

    assert recovered["source_summary"]["workspace_inventory_comparison"] == {
        "state": "unavailable",
        "reason": "prior_inventory_gap_malformed",
    }
    assert "workspace_inventory_gap" not in recovered["source_summary"]


@pytest.mark.parametrize(
    "gap",
    [
        {"missing_project_keys": ["Beta"], "baseline_generated_at": ""},
        {
            "missing_project_keys": ["Beta", "Beta"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
        },
        {
            "missing_project_keys": ["Gamma", "Beta"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
        },
        {
            "missing_project_keys": ["supp:calendar"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
        },
        {
            "missing_project_keys": ["Alpha"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
        },
        {
            "missing_project_keys": ["Beta"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
            "missing_project_paths": {"Alpha": "Alpha"},
        },
        {
            "missing_project_keys": ["Beta"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
            "missing_project_paths": {"Beta": "../outside"},
        },
        {
            "missing_project_keys": ["Beta"],
            "baseline_generated_at": "2026-11-06T10:00:00+00:00",
            "missing_project_paths": {"Beta": "Alpha"},
        },
    ],
)
def test_invalid_workspace_inventory_gap_is_rejected(
    tmp_path: Path, gap: dict[str, object]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _make_project(workspace, "Alpha")
    _make_project(workspace, "Beta")
    snapshot = _publish(
        workspace,
        tmp_path / "output",
        datetime(2026, 11, 6, 10, tzinfo=timezone.utc),
    )
    snapshot["source_summary"]["workspace_inventory_gap"] = gap

    with pytest.raises(ValueError, match="workspace inventory gap"):
        validate_truth_snapshot(_snapshot_from_payload(snapshot))


def test_invalid_workspace_inventory_comparison_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _make_project(workspace, "Alpha")
    snapshot = _publish(
        workspace,
        tmp_path / "output",
        datetime(2026, 11, 6, 10, tzinfo=timezone.utc),
    )
    snapshot["source_summary"]["workspace_inventory_comparison"] = {
        "state": "complete",
        "reason": "unknown",
    }

    with pytest.raises(ValueError, match="workspace inventory comparison"):
        validate_truth_snapshot(_snapshot_from_payload(snapshot))


def test_workspace_path_removal_requires_a_confirmed_missing_path(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Project").mkdir()

    assert _workspace_path_is_directory(workspace, "Project")
    assert _workspace_path_is_directory(workspace, "../outside")
    assert _workspace_path_is_directory(tmp_path / "unavailable", "Project")

    with patch.object(Path, "stat", side_effect=PermissionError("denied")):
        assert _workspace_path_is_directory(workspace, "Project")

    (workspace / "Project").rmdir()
    assert not _workspace_path_is_directory(workspace, "Project")

    (workspace / "DanglingProject").symlink_to(tmp_path / "removed-target")
    assert not _workspace_path_is_directory(workspace, "DanglingProject")


def test_workspace_path_rekey_at_same_path_resolves_prior_key(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project_path = workspace / "Project"
    project_path.mkdir(parents=True)
    latest = tmp_path / "portfolio-truth-latest.json"
    latest.write_text(
        json.dumps(
            {
                "workspace_root": str(workspace),
                "generated_at": "2026-11-06T10:00:00+00:00",
                "projects": [
                    {
                        "identity": {
                            "project_key": "repo:old-name",
                            "path": "Project",
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _workspace_inventory_gap(
        latest,
        workspace_root=workspace,
        current_project_keys={"repo:new-name"},
        current_project_paths={"Project"},
    ) == (None, None)


def test_workspace_path_excluded_by_current_policy_resolves_gap(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    excluded_path = workspace / "smoke-export"
    excluded_path.mkdir(parents=True)
    latest = tmp_path / "portfolio-truth-latest.json"
    latest.write_text(
        json.dumps(
            {
                "workspace_root": str(workspace),
                "generated_at": "2026-11-06T10:00:00+00:00",
                "projects": [
                    {
                        "identity": {
                            "project_key": "repo:old-smoke-project",
                            "path": "smoke-export",
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _workspace_inventory_gap(
        latest,
        workspace_root=workspace,
        current_project_keys=set(),
        current_project_paths=set(),
    ) == (None, None)
