from __future__ import annotations

from pathlib import Path

from github_repo_auditor.portfolio_truth_reconcile import (
    _select_repo_status_entry,
    build_portfolio_truth_snapshot,
)
from github_repo_auditor.portfolio_truth_status import (
    _repo_status_entries_from_metadata,
)


def test_github_archive_status_joins_same_named_repositories_by_owner() -> None:
    statuses = _repo_status_entries_from_metadata(
        [
            {
                "name": "shared",
                "full_name": "first-owner/shared",
                "archived": True,
            },
            {
                "name": "shared",
                "full_name": "second-owner/shared",
                "archived": False,
            },
        ],
        source="github_api",
    )

    selected = _select_repo_status_entry(statuses, "first-owner/shared", "shared")

    assert selected is not None
    assert selected["archived"] is True
    assert _select_repo_status_entry(statuses, "unrelated/shared", "shared") is None
    assert _select_repo_status_entry(statuses, None, "shared") is None


def test_empty_name_keyed_status_defers_to_independent_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "Widget"
    project.mkdir(parents=True)
    (project / "sample.bin").touch()
    remote = {"Widget": {"repository": {"state": "observed", "archived": True}}}

    for security, expected in ((remote, True), ({}, None)):
        snapshot = build_portfolio_truth_snapshot(
            workspace_root=workspace,
            catalog_path=tmp_path / "absent.yaml",
            include_notion=False,
            repo_status_by_name={"Widget": {}},
            security_alerts_by_name=security,
        ).snapshot
        (row,) = snapshot.projects
        assert row.derived.archived is expected
        if expected is True:
            assert row.provenance["github.archived"]["source"] == "github_security"
        else:
            assert "github.archived" not in row.provenance
