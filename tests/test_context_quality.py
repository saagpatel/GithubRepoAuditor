# tests/test_context_quality.py
"""Tests for the composite context_quality_score (Arc H H.4)."""
import pytest

from src.context_quality import compute_context_quality_score
from src.models import AnalyzerResult, RepoAudit, RepoMetadata


def test_perfect_repo_scores_one():
    score = compute_context_quality_score(
        description_confidence=1.0,
        readme_stale_by_age=False,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert score == pytest.approx(1.0)


def test_missing_description_lowers_score():
    score = compute_context_quality_score(
        description_confidence=0.0,
        readme_stale_by_age=False,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert score < 1.0
    assert score < 0.8  # description_confidence weight is 0.30


def test_stale_readme_lowers_score():
    score = compute_context_quality_score(
        description_confidence=1.0,
        readme_stale_by_age=True,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert score < 1.0


def test_worst_case_repo_scores_near_zero():
    score = compute_context_quality_score(
        description_confidence=0.0,
        readme_stale_by_age=True,
        catalog_completeness=0.0,
        completeness_score=0.0,
    )
    assert score < 0.2


def test_none_values_treated_as_zero():
    score = compute_context_quality_score(
        description_confidence=None,
        readme_stale_by_age=None,
        catalog_completeness=None,
        completeness_score=None,
    )
    assert 0.0 <= score <= 1.0


def test_score_clamped_to_zero_one():
    score = compute_context_quality_score(
        description_confidence=2.0,  # out of range input
        readme_stale_by_age=False,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert 0.0 <= score <= 1.0


def test_repo_audit_context_quality_uses_portfolio_catalog(sample_metadata: RepoMetadata):
    audit = RepoAudit(
        metadata=sample_metadata,
        analyzer_results=[
            AnalyzerResult(
                "description",
                1.0,
                1.0,
                [],
                {"description_confidence": 1.0},
            ),
            AnalyzerResult("readme", 1.0, 1.0, [], {"readme_stale_by_age": False}),
            AnalyzerResult("completeness", 1.0, 1.0, []),
        ],
        overall_score=1.0,
        completeness_tier="shipped",
        portfolio_catalog={
            "owner": "d",
            "lifecycle_state": "active",
            "review_cadence": "weekly",
            "intended_disposition": "maintain",
        },
    )

    assert audit.to_dict()["context_quality_score"] == 1.0
