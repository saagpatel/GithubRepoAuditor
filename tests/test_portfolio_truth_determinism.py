import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth
from github_repo_auditor.portfolio_truth_reconcile import (
    MaterializationContext,
    build_portfolio_truth_snapshot,
)
from github_repo_auditor.portfolio_truth_render import _group_projects
from github_repo_auditor.portfolio_truth_sources import _dedupe_checkouts_by_origin
from github_repo_auditor.portfolio_truth_types import (
    AdvisoryFields,
    DeclaredFields,
    DerivedFields,
    IdentityFields,
    PortfolioTruthProject,
)
from github_repo_auditor.portfolio_truth_status import (
    load_repo_status_from_audit_by_name,
)


@pytest.mark.parametrize(
    "variation", ["report-order", "readme-order", "clock-zone", "metadata-order"]
)
def test_published_truth_bytes_ignore_listing_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variation: str
) -> None:
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_publish.load_source_paths",
        lambda _: dict(bridge_db=None, notion_snapshot=None, memory_dir=None),
    )
    workspace = tmp_path / "workspace"
    repo = workspace / "sample"
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
            "https://github.com/fixture/sample",
        ],
        check=True,
    )
    (repo / "README.fr").write_text("longer text")
    (repo / "README.en").write_text("text")

    cache = tmp_path / "cache"
    cache.mkdir()
    for date, archived in [("2025-01-01", False), ("2025-01-02", True)]:
        path = cache / f"audit-report-fixture-{date}.json"
        path.write_text(
            json.dumps(
                {
                    "audits": [
                        {
                            "metadata": {
                                "name": "sample",
                                "full_name": "fixture/sample",
                                "archived": archived,
                            }
                        }
                    ]
                }
            )
        )
        os.utime(path, (1700000000, 1700000000))

    original_iterdir, original_glob = Path.iterdir, Path.glob

    def generate(reverse: bool) -> tuple[bytes, bytes]:
        monkeypatch.setattr(
            Path,
            "iterdir",
            lambda p: iter(
                sorted(
                    original_iterdir(p), reverse=reverse and variation == "readme-order"
                )
            ),
        )
        monkeypatch.setattr(
            Path,
            "glob",
            lambda p, *a, **kw: iter(
                sorted(
                    original_glob(p, *a, **kw),
                    reverse=reverse and variation == "report-order",
                )
            ),
        )
        clock = datetime(2025, 1, 3, tzinfo=timezone.utc)
        if reverse and variation == "clock-zone":
            clock = clock.astimezone(timezone(timedelta(hours=-8)))
        metadata = None
        if variation == "metadata-order":
            metadata = {
                "source_id": "github-security-coverage-receipt",
                "schema_version": "GitHubSecurityCoverageReceiptV1",
                "produced_at": clock.isoformat(),
                "state": "fresh",
                "age_hours": 0.0,
                "producer_commit": "a" * 40,
                "cohort_policy": "portfolio-default-attention-v1",
                "cohort_repository_count": 0,
                "path": "fixture-receipt.json",
            }
            if reverse:
                metadata = dict(reversed(metadata.items()))
        generation = publish_portfolio_truth(
            workspace_root=workspace,
            output_dir=tmp_path / ("second" if reverse else "first"),
            registry_output=workspace / "registry.md",
            portfolio_report_output=workspace / "report.md",
            catalog_path=tmp_path / "missing.yaml",
            include_notion=False,
            now=clock,
            security_coverage_metadata=metadata,
            repo_status_by_name=load_repo_status_from_audit_by_name(
                output_dir=cache, username="fixture"
            ),
        )
        return (
            generation.latest_path.read_bytes(),
            generation.portfolio_report_output.read_bytes(),
        )

    first_json, first_report = generate(False)
    second_json, second_report = generate(True)
    assert first_report == second_report
    assert first_json == second_json
    assert json.loads(first_json)["projects"][0]["derived"]["archived"] is True


def test_case_only_checkout_ties_have_stable_order() -> None:
    def checkout(name: str, head: str, common_dir: str) -> dict:
        return {
            "name": name,
            "repo_full_name": "fixture/repo",
            "path": name,
            "project_path": Path("/workspace") / name,
            "_checkout_observation": {
                "state": "observed",
                "head": head,
                "branch": "main",
                "dirty": False,
                "dirty_path_count": 0,
                "git_common_dir": common_dir,
                "bare": False,
                "declared_paths": [],
            },
        }

    upper = checkout("Repo", "1" * 40, "/git/upper/.git")
    lower = checkout("repo", "2" * 40, "/git/lower/.git")

    def collision(discovered: list[dict]) -> dict:
        collisions: list[dict] = []
        _dedupe_checkouts_by_origin(discovered, checkout_collisions=collisions)
        return collisions[0]

    assert collision([upper, lower]) == collision([lower, upper])


def test_case_only_project_and_notion_rows_have_stable_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def project(name: str, portfolio_call: str) -> PortfolioTruthProject:
        return PortfolioTruthProject(
            identity=IdentityFields(
                project_key=name,
                display_name=name,
                path=name,
                top_level_dir=name,
                group_key="standalone",
                group_label="Standalone Projects",
                section_marker="Standalone Projects",
                section_label="Standalone Projects",
                has_git=False,
            ),
            declared=DeclaredFields(),
            derived=DerivedFields(),
            advisory=AdvisoryFields(notion_portfolio_call=portfolio_call),
        )

    upper = project("Widget", "upper Notion row")
    lower = project("widget", "lower Notion row")

    def ordered_rows(
        projects: list[PortfolioTruthProject],
    ) -> list[tuple[str, str]]:
        monkeypatch.setattr(
            MaterializationContext,
            "materialize_projects",
            lambda *a, **kw: projects.copy(),
        )
        result = build_portfolio_truth_snapshot(
            workspace_root=tmp_path,
            catalog_path=tmp_path / "absent.yaml",
            include_notion=False,
        )
        assert [row.identity.path for row in result.snapshot.projects] == [
            "Widget",
            "widget",
        ]
        members = _group_projects(projects)["Standalone Projects"]
        return [
            (item.identity.display_name, item.advisory.notion_portfolio_call)
            for item in members
        ]

    assert ordered_rows([upper, lower]) == ordered_rows([lower, upper])
