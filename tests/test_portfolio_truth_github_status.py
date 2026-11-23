from __future__ import annotations

from github_repo_auditor.portfolio_truth_reconcile import _select_repo_status_entry
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
