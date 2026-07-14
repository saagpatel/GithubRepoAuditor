from __future__ import annotations

UNSCORED_DIMENSIONS = frozenset({"description"})


def display_dimension(dimension: str) -> str:
    """Return the operator-facing label for a scored or advisory dimension."""
    return f"{dimension} (unscored)" if dimension in UNSCORED_DIMENSIONS else dimension
