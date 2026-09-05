"""Shared lenient timestamp parsing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal


def parse_utc_timestamp(
    value: object,
    *,
    naive: Literal["reject", "assume_utc"] = "reject",
    coerce: bool = False,
) -> datetime | None:
    """Parse a timestamp and normalize timezone-aware results to UTC."""
    if coerce:
        text = str(value or "").strip()
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        if naive == "reject":
            return None
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
