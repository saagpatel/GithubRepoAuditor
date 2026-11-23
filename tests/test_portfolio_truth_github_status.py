from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from github_repo_auditor.github_security_coverage import (
    GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
    _remote_repository_result,
)
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

    selected = _select_repo_status_entry(statuses, "FIRST-Owner/Shared", "shared")

    assert selected is not None
    assert selected["archived"] is True
    assert _select_repo_status_entry(statuses, "unrelated/shared", "shared") is None
    assert _select_repo_status_entry(statuses, None, "shared") is None


def test_null_github_archive_flag_uses_observed_receipt(tmp_path: Path) -> None:
    repo = tmp_path / "sample"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "remote",
            "add",
            "origin",
            "https://github.com/fixture/sample",
        ],
        check=True,
    )
    now = datetime(2025, 1, 3, tzinfo=timezone.utc)
    full_name = "fixture/sample"
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("repos:\n  sample:\n    lifecycle_state: dormant\n")
    result = build_portfolio_truth_snapshot(
        workspace_root=tmp_path,
        catalog_path=catalog,
        include_notion=False,
        now=now,
        repo_status_by_name={
            "sample": {
                "full_name": full_name,
                "source": "github_api",
                "archived": None,
            }
        },
        security_alerts_by_name={
            full_name: {
                "receipt_schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
                "receipt_state": "fresh",
                "repository": _remote_repository_result(
                    state="observed",
                    observed_at=now.isoformat(),
                    default_branch="main",
                    head_sha="b" * 40,
                    archived=True,
                ),
            }
        },
    )

    (project,) = result.snapshot.projects
    assert (
        project.derived.archived,
        project.derived.attention_state,
        project.provenance["github.archived"]["source"],
    ) == (True, "archived", "github-graphql-default-branch-head-v1")
