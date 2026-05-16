# tests/test_tier_recalibration.py
"""Tests for the tier distribution report (Arc H A4)."""
from src.tier_recalibration import tier_distribution_report


def _make_repo(tier: int) -> dict:
    return {"_mock_tier": tier}


def test_report_counts_tiers_correctly(monkeypatch):
    from src import tier_recalibration

    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = (
        [_make_repo(1)] * 10
        + [_make_repo(2)] * 5
        + [_make_repo(3)] * 3
        + [_make_repo(4)] * 2
    )
    report = tier_distribution_report(repos)

    assert report["counts"]["Bronze"] == 10
    assert report["counts"]["Silver"] == 5
    assert report["counts"]["Gold"] == 3
    assert report["counts"]["Platinum"] == 2
    assert report["total"] == 20


def test_report_computes_percentages(monkeypatch):
    from src import tier_recalibration

    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(1)] * 3 + [_make_repo(2)] * 1
    report = tier_distribution_report(repos)

    assert report["percentages"]["Bronze"] == 75.0
    assert report["percentages"]["Silver"] == 25.0


def test_report_empty_repos():
    report = tier_distribution_report([])
    assert report["total"] == 0
    assert report["counts"]["Bronze"] == 0


def test_report_flags_bunching_when_bronze_over_60_percent(monkeypatch):
    from src import tier_recalibration

    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(1)] * 7 + [_make_repo(2)] * 3
    report = tier_distribution_report(repos)
    assert report["bunching_detected"] is True


def test_report_no_bunching_when_distributed(monkeypatch):
    from src import tier_recalibration

    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(t) for t in [1, 2, 3, 4]] * 5
    report = tier_distribution_report(repos)
    assert report["bunching_detected"] is False
