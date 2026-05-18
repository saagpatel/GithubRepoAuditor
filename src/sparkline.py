"""Unicode sparkline rendering for score history visualization."""
from __future__ import annotations

BARS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """Render a list of floats as a unicode sparkline string.

    Returns empty string for fewer than 2 values.
    """
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    if mn == mx:
        return BARS[4] * len(values)
    return "".join(BARS[int((v - mn) / (mx - mn) * 7)] for v in values)
