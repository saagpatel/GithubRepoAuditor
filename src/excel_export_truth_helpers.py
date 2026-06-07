"""Helpers for workbook export truth-data loading."""

from __future__ import annotations

import json
from pathlib import Path

from src.portfolio_truth_types import truth_latest_path


def load_risk_truth(truth_dir: Path | None) -> tuple[dict[str, str], dict[str, int]]:
    if not truth_dir:
        return {}, {}

    truth_path = truth_latest_path(truth_dir)
    if not truth_path.is_file():
        return {}, {}

    try:
        truth_data = json.loads(truth_path.read_text())
    except Exception:
        truth_data = {}

    risk_lookup: dict[str, str] = {}
    tier_counts: dict[str, int] = {}
    for project in truth_data.get("projects") or []:
        identity = project.get("identity") or {}
        display_name = str(identity.get("display_name") or "")
        risk_tier = str((project.get("risk") or {}).get("risk_tier") or "")
        if display_name:
            risk_lookup[display_name] = risk_tier
        # Also key by the GitHub repo name so workbook surfaces that look up by audit
        # metadata.name resolve risk when it differs from the local-dir display_name
        # (e.g. "Signal & Noise" vs "signal-noise"). tier_counts is incremented once
        # per project below, so the alias does not inflate the aggregate posture.
        slug = str(identity.get("repo_full_name") or "").rsplit("/", 1)[-1]
        if slug and slug not in risk_lookup:
            risk_lookup[slug] = risk_tier
        if risk_tier:
            tier_counts[risk_tier] = tier_counts.get(risk_tier, 0) + 1

    risk_posture = {
        "elevated": tier_counts.get("elevated", 0),
        "moderate": tier_counts.get("moderate", 0),
        "baseline": tier_counts.get("baseline", 0),
        "deferred": tier_counts.get("deferred", 0),
    }
    return risk_lookup, risk_posture
