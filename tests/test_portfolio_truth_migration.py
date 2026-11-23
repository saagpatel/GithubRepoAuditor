from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from github_repo_auditor.portfolio_truth_metadata import build_warnings
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from github_repo_auditor.portfolio_truth_sources import checkout_collision_summary
from github_repo_auditor.portfolio_truth_validate import (
    canonicalize_prior_security_truth_payload,
)


def test_prior_checkout_declaration_case_tie_is_migrated_in_both_copies(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    repo = workspace / "Repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "remote",
            "add",
            "origin",
            "https://github.com/fixture/repo",
        ],
        check=True,
    )
    (repo / "README.md").write_text("# Repo\n")

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "absent.yaml",
        include_notion=False,
        repo_status_by_name={"Repo": {"archived": False}},
    )
    payload = result.snapshot.to_dict()
    project = payload["projects"][0]
    assert project["identity"]["path"] == "Repo"
    assert project["identity"]["repo_full_name"] == "fixture/repo"

    # c3b12ce produced and validated this group with PYTHONHASHSEED=1.
    group = json.loads(
        (
            Path(__file__).parent
            / "fixtures/portfolio_truth/0.12-case-only-checkout-collision.json"
        ).read_text()
    )
    project["repository_state"]["checkout_authority"] = deepcopy(group)
    payload["source_summary"]["checkout_collisions"] = checkout_collision_summary(
        [group]
    )
    payload["warnings"] = build_warnings(
        catalog_errors=payload["source_summary"]["catalog_errors"],
        catalog_warnings=payload["source_summary"]["catalog_warnings"],
        unresolved_duplicates=payload["source_summary"][
            "unresolved_duplicate_display_names"
        ],
        checkout_collisions=[group],
    )
    payload["schema_version"] = "0.12.0"
    original = deepcopy(payload)
    assert group["declared_checkout_paths"] == ["repo", "Repo"]

    canonical = canonicalize_prior_security_truth_payload(payload)

    expected = ["Repo", "repo"]
    assert (
        canonical["projects"][0]["repository_state"]["checkout_authority"][
            "declared_checkout_paths"
        ]
        == expected
    )
    assert (
        canonical["source_summary"]["checkout_collisions"]["groups"][0][
            "declared_checkout_paths"
        ]
        == expected
    )
    assert payload == original

    invalid_evidence = deepcopy(payload)
    invalid_group = invalid_evidence["source_summary"]["checkout_collisions"]["groups"][
        0
    ]
    invalid_group["declared_path_evidence"][0]["target_checkout_path"] = "Repo"
    invalid_evidence["projects"][0]["repository_state"]["checkout_authority"] = (
        deepcopy(invalid_group)
    )
    with pytest.raises(ValueError, match="Declared checkout paths do not match"):
        canonicalize_prior_security_truth_payload(invalid_evidence)
