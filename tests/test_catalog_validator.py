# tests/test_catalog_validator.py
"""Tests for the catalog completeness validator (Arc H A3)."""
import pytest
import yaml

from src.catalog_validator import REQUIRED_FIELDS, score_catalog_entry, validate_catalog


def test_full_entry_scores_one():
    entry = {
        "owner": "d",
        "lifecycle_state": "active",
        "review_cadence": "weekly",
        "intended_disposition": "maintain",
    }
    assert score_catalog_entry(entry) == 1.0


def test_empty_entry_scores_zero():
    assert score_catalog_entry({}) == 0.0


def test_partial_entry_scores_proportionally():
    entry = {"owner": "d", "lifecycle_state": "active"}
    assert score_catalog_entry(entry) == pytest.approx(0.5)


def test_none_entry_scores_zero():
    assert score_catalog_entry(None) == 0.0


def test_validate_catalog_scores_repos(tmp_path):
    catalog = {
        "repos": {
            "RepoA": {
                "owner": "d",
                "lifecycle_state": "active",
                "review_cadence": "weekly",
                "intended_disposition": "maintain",
            },
            "RepoB": {"owner": "d"},
            "RepoC": {},
        }
    }
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(catalog))

    results = validate_catalog(catalog_path, repo_names=["RepoA", "RepoB", "RepoC", "RepoD"])
    assert results["RepoA"] == pytest.approx(1.0)
    assert results["RepoB"] == pytest.approx(0.25)
    assert results["RepoC"] == pytest.approx(0.0)
    assert results["RepoD"] == pytest.approx(0.0)  # not in catalog at all


def test_validate_catalog_missing_file_returns_zeros(tmp_path):
    results = validate_catalog(tmp_path / "missing.yaml", repo_names=["RepoA"])
    assert results["RepoA"] == 0.0


def test_required_fields_constant_has_four_entries():
    assert len(REQUIRED_FIELDS) == 4
