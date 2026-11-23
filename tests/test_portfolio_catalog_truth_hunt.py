from __future__ import annotations

from github_repo_auditor.portfolio_catalog import catalog_entry_for_repo


def test_catalog_does_not_apply_another_checkout_path_lifecycle_by_basename() -> None:
    catalog = {
        "repos": {
            "retired/legacy-app": {
                "lifecycle_state": "archived",
                "catalog_key": "retired/legacy-app",
                "has_explicit_entry": True,
            }
        }
    }

    entry = catalog_entry_for_repo(
        {
            "name": "legacy-app",
            "full_name": "current-owner/legacy-app",
            "path": "apps/legacy-app",
        },
        catalog,
    )

    assert entry["has_explicit_entry"] is False
    assert entry["lifecycle_state"] == ""
