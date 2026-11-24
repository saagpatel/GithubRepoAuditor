from datetime import datetime, timedelta, timezone

import pytest

from github_repo_auditor import portfolio_truth_publish as publish
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot


def test_snapshot_clock_is_normalized_before_publication(tmp_path):
    clock = datetime(2025, 2, 1, 4, 15, tzinfo=timezone(timedelta(hours=4)))
    snapshot = build_portfolio_truth_snapshot(
        workspace_root=tmp_path,
        catalog_path=tmp_path / "missing.yaml",
        legacy_registry_path=tmp_path / "missing.md",
        include_notion=False,
        now=clock,
    ).snapshot
    assert snapshot.to_dict()["generated_at"] == "2025-02-01T00:15:00+00:00"


def test_snapshot_clock_requires_an_offset_before_loading_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_reconcile.load_portfolio_catalog",
        lambda _: pytest.fail("loaded catalog before validating report clock"),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_portfolio_truth_snapshot(
            workspace_root=tmp_path, now=datetime(2025, 2, 1)
        )


def test_publication_rejects_naive_clock_before_touching_sources(tmp_path, monkeypatch):
    def unexpected_target_read(**kwargs):
        pytest.fail("publication reached target validation before clock validation")

    monkeypatch.setattr(publish, "validate_publish_targets", unexpected_target_read)
    with pytest.raises(ValueError, match="timezone-aware"):
        publish.publish_portfolio_truth(
            workspace_root=tmp_path / "workspace",
            output_dir=tmp_path / "output",
            registry_output=tmp_path / "workspace" / "registry.md",
            portfolio_report_output=tmp_path / "workspace" / "report.md",
            now=datetime(2025, 2, 1),
        )
