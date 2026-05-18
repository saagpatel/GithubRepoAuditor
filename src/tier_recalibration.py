# src/tier_recalibration.py
"""Tier distribution report for maturity recalibration (Arc H A4)."""
from __future__ import annotations

from typing import Any

from src.maturity_tiers import compute_tier

_TIER_NAMES = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Platinum"}
_BUNCHING_THRESHOLD = 0.60  # flag if any single tier holds > 60% of repos


def tier_distribution_report(repos: list[dict[str, Any]]) -> dict[str, Any]:
    """Return tier distribution counts, percentages, and a bunching flag."""
    total = len(repos)
    counts: dict[str, int] = {name: 0 for name in _TIER_NAMES.values()}

    for repo in repos:
        tier = compute_tier(repo)
        name = _TIER_NAMES.get(tier)
        if name:
            counts[name] += 1

    percentages: dict[str, float] = {
        name: round(100.0 * count / total, 1) if total else 0.0
        for name, count in counts.items()
    }
    bunching = any(pct > _BUNCHING_THRESHOLD * 100 for pct in percentages.values())

    return {
        "total": total,
        "counts": counts,
        "percentages": percentages,
        "bunching_detected": bunching,
    }
