from __future__ import annotations


def recommendation_drift_status(
    primary_target_flip_count: int,
    policy_flip_hotspots: list[dict],
) -> str:
    repeated_hotspots = sum(
        1 for hotspot in policy_flip_hotspots if hotspot.get("flip_count", 0) >= 2
    )
    if primary_target_flip_count >= 2 or repeated_hotspots >= 2:
        return "drifting"
    if primary_target_flip_count == 1 or repeated_hotspots == 1:
        return "watch"
    return "stable"


def recommendation_drift_summary(
    label: str,
    flip_count: int,
    recent_policy_path: str,
    policy_flip_hotspots: list[dict],
) -> str:
    if flip_count >= 2 and recent_policy_path:
        return f"{label} has flipped trust policy {flip_count} time(s) in the recent window: {recent_policy_path}."
    if flip_count == 1 and recent_policy_path:
        return f"{label} has started to wobble between trust policies in the recent window: {recent_policy_path}."
    if policy_flip_hotspots:
        hotspot = policy_flip_hotspots[0]
        return (
            f"Trust-policy drift is currently led by {hotspot.get('label', 'recent hotspots')} "
            f"with {hotspot.get('flip_count', 0)} flip(s) across {hotspot.get('recent_policy_path', '')}."
        )
    return "Recent trust-policy behavior is stable enough that no meaningful recommendation drift is recorded."
