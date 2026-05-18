# src/context_quality.py
"""Composite context_quality_score computation (Arc H H.4)."""
from __future__ import annotations

# Weights must sum to 1.0.
_WEIGHTS = {
    "description_confidence": 0.30,
    "readme_freshness": 0.25,      # inverted from readme_stale_by_age
    "catalog_completeness": 0.25,
    "completeness_score": 0.20,
}


def compute_context_quality_score(
    description_confidence: float | None,
    readme_stale_by_age: bool | None,
    catalog_completeness: float | None,
    completeness_score: float | None,
) -> float:
    """Return a composite context quality score in [0.0, 1.0]."""
    desc = max(0.0, min(1.0, description_confidence or 0.0))
    readme_fresh = 0.0 if readme_stale_by_age is True else 1.0
    catalog = max(0.0, min(1.0, catalog_completeness or 0.0))
    complete = max(0.0, min(1.0, completeness_score or 0.0))

    score = (
        _WEIGHTS["description_confidence"] * desc
        + _WEIGHTS["readme_freshness"] * readme_fresh
        + _WEIGHTS["catalog_completeness"] * catalog
        + _WEIGHTS["completeness_score"] * complete
    )
    return round(max(0.0, min(1.0, score)), 4)
