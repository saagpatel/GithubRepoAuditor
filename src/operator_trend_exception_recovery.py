from __future__ import annotations

from typing import Any, Callable


def trust_recovery_for_target(
    target: dict[str, Any],
    history_meta: dict[str, Any],
    confidence_calibration: dict[str, Any],
    *,
    trust_policy: str,
    trust_policy_reason: str,
    trust_recovery_window_runs: int,
) -> tuple[str, str, str, str]:
    if target.get("trust_exception_status") in {None, "", "none"} or trust_policy != "verify-first":
        return "none", "", trust_policy, trust_policy_reason

    if confidence_calibration.get("confidence_validation_status") != "healthy":
        return (
            "blocked",
            "Trust recovery is blocked because confidence calibration has not stayed healthy enough yet.",
            trust_policy,
            trust_policy_reason,
        )
    if history_meta.get("recent_reopened"):
        return (
            "blocked",
            "Trust recovery is blocked because this target reopened again inside the recent recovery window.",
            trust_policy,
            trust_policy_reason,
        )
    if history_meta.get("recent_policy_flip_count", 0) > 0:
        return (
            "blocked",
            "Trust recovery is blocked because the target is still flipping trust policy inside the recent recovery window.",
            trust_policy,
            trust_policy_reason,
        )
    if not history_meta.get("same_or_lower_pressure_path", True):
        return (
            "blocked",
            "Trust recovery is blocked because the target has not stayed on the same or lower-pressure path yet.",
            trust_policy,
            trust_policy_reason,
        )
    if history_meta.get("stable_policy_run_count", 0) >= trust_recovery_window_runs:
        recovered_policy = "act-with-review"
        recovered_reason = (
            "Recent stability has earned this target back from verify-first to act-with-review."
        )
        if target.get("lane") == "blocked" and target.get("kind") == "setup":
            recovered_reason = "Recent stability has earned this blocked setup target back to act-with-review, but setup blockers still should not skip review."
        return "earned", recovered_reason, recovered_policy, recovered_reason
    return (
        "candidate",
        "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
        trust_policy,
        trust_policy_reason,
    )


def recovery_pattern_reason(recovery_status: str, recovery_reason: str) -> str:
    if recovery_status == "earned":
        return recovery_reason or "Recent stability has earned stronger trust again."
    if recovery_status == "candidate":
        return recovery_reason or "This target is stabilizing, but it has not yet earned stronger trust."
    return recovery_reason or "Trust recovery is still being evaluated."


def exception_pattern_summary(
    primary_target: dict[str, Any],
    false_positive_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    pattern_status = primary_target.get("exception_pattern_status", "none")
    recovery_status = primary_target.get("trust_recovery_status", "none")
    label = target_label(primary_target) or "The current target"
    if recovery_status == "earned":
        return f"{label} has stayed stable long enough to earn trust back from verify-first to act-with-review."
    if recovery_status == "candidate":
        return f"{label} is stabilizing, but it has not yet earned stronger trust."
    if recovery_status == "blocked":
        return primary_target.get(
            "trust_recovery_reason",
            f"{label} still has fresh reopen, flip, or calibration noise blocking trust recovery.",
        )
    if pattern_status == "useful-caution":
        return f"Recent soft caution for {label} has been justified and still looks appropriate."
    if pattern_status == "overcautious":
        return f"Recent soft caution for {label} may now be more cautious than the evidence supports."
    if false_positive_hotspots:
        hotspot = false_positive_hotspots[0]
        return (
            f"Recent soft exceptions have been most overcautious around {hotspot.get('label', 'recent hotspots')}, "
            f"so verify-first guidance should not linger there longer than the evidence supports."
        )
    if pattern_status == "insufficient-data":
        return "Exception learning is still too lightly exercised to say whether recent soft caution is helping."
    return "Recent exception behavior does not yet show a strong overcautious or recovery pattern."
