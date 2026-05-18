# src/catalog_validator.py
"""Catalog completeness validator for portfolio-catalog.yaml entries (Arc H A3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS: tuple[str, ...] = (
    "owner",
    "lifecycle_state",
    "review_cadence",
    "intended_disposition",
)


def score_catalog_entry(entry: dict[str, Any] | None) -> float:
    """Return completeness score (0.0-1.0) for a single catalog repo entry."""
    if not entry:
        return 0.0
    present = sum(1 for f in REQUIRED_FIELDS if entry.get(f))
    return present / len(REQUIRED_FIELDS)


def validate_catalog(catalog_path: Path, repo_names: list[str]) -> dict[str, float]:
    """Return a completeness score for each repo name.

    Repos not present in the catalog score 0.0.
    """
    repos: dict[str, Any] = {}
    if catalog_path.is_file():
        data = yaml.safe_load(catalog_path.read_text()) or {}
        repos = data.get("repos", {}) if isinstance(data, dict) else {}

    return {name: score_catalog_entry(repos.get(name)) for name in repo_names}
