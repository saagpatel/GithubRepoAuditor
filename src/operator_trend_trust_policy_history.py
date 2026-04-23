from __future__ import annotations

from typing import Any, Callable


def build_trust_exception_events(
    history: list[dict[str, Any]],
    *,
    current_primary_target: dict[str, Any],
    current_generated_at: str,
    queue_identity: Callable[[dict[str, Any]], str],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    history_window_runs: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": queue_identity(current_primary_target),
                "class_key": target_class_key(current_primary_target),
                "label": target_label(current_primary_target),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "trust_exception_status": current_primary_target.get(
                    "trust_exception_status", "none"
                ),
                "generated_at": current_generated_at or "",
                "lane": current_primary_target.get("lane", ""),
                "kind": current_primary_target.get("kind", ""),
                "decision_memory_status": current_primary_target.get(
                    "decision_memory_status", ""
                ),
                "last_outcome": current_primary_target.get("last_outcome", ""),
                "confidence_validation_status": current_primary_target.get(
                    "confidence_validation_status", ""
                ),
            }
        )
    for entry in history[: history_window_runs - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        trust_policy = summary.get("primary_target_trust_policy", "")
        if not primary_target or not trust_policy:
            continue
        events.append(
            {
                "key": queue_identity(primary_target),
                "class_key": target_class_key(primary_target),
                "label": target_label(primary_target),
                "trust_policy": trust_policy,
                "trust_exception_status": summary.get("primary_target_exception_status", "none"),
                "generated_at": entry.get("generated_at", ""),
                "lane": primary_target.get("lane", ""),
                "kind": primary_target.get("kind", ""),
                "decision_memory_status": summary.get("decision_memory_status", ""),
                "last_outcome": summary.get("primary_target_last_outcome", ""),
                "confidence_validation_status": summary.get("confidence_validation_status", ""),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def historical_exception_cases(
    history: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    run_target_match: Callable[[dict[str, Any], str], dict[str, Any] | None],
    attention_lanes: set[str],
    history_window_runs: int,
    trust_recovery_window_runs: int,
) -> list[dict[str, Any]]:
    ordered_runs = sorted(
        [
            {
                "generated_at": entry.get("generated_at", ""),
                "operator_summary": entry.get("operator_summary") or {},
                "operator_queue": entry.get("operator_queue") or [],
            }
            for entry in history[: history_window_runs - 1]
        ],
        key=lambda item: item.get("generated_at", ""),
    )
    cases: list[dict[str, Any]] = []
    for index, run in enumerate(ordered_runs):
        summary = run.get("operator_summary") or {}
        target = summary.get("primary_target") or {}
        exception_status = summary.get("primary_target_exception_status", "none")
        if not target or exception_status in {None, "", "none"}:
            continue
        future_runs = ordered_runs[index + 1 : index + 1 + trust_recovery_window_runs]
        cases.append(
            {
                "key": queue_identity(target),
                "class_key": target_class_key(target),
                "label": target_label(target),
                "generated_at": run.get("generated_at", ""),
                "lane": target.get("lane", ""),
                "kind": target.get("kind", ""),
                "trust_exception_status": exception_status,
                "case_outcome": exception_case_outcome(
                    run,
                    future_runs,
                    queue_identity=queue_identity,
                    run_target_match=run_target_match,
                    attention_lanes=attention_lanes,
                    trust_recovery_window_runs=trust_recovery_window_runs,
                ),
            }
        )
    return sorted(cases, key=lambda item: item.get("generated_at", ""), reverse=True)


def exception_case_outcome(
    run: dict[str, Any],
    future_runs: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
    run_target_match: Callable[[dict[str, Any], str], dict[str, Any] | None],
    attention_lanes: set[str],
    trust_recovery_window_runs: int,
) -> str:
    if len(future_runs) < trust_recovery_window_runs:
        return "insufficient-data"
    summary = run.get("operator_summary") or {}
    target = summary.get("primary_target") or {}
    target_key = queue_identity(target)
    future_matches = [run_target_match(candidate, target_key) for candidate in future_runs]
    future_lanes = [match.get("lane") if match else None for match in future_matches]
    reopened = any(
        (
            (candidate.get("operator_summary") or {}).get("decision_memory_status") == "reopened"
            or (candidate.get("operator_summary") or {}).get("primary_target_last_outcome")
            == "reopened"
        )
        and queue_identity((candidate.get("operator_summary") or {}).get("primary_target") or {})
        == target_key
        for candidate in future_runs
    )
    if reopened or any(lane in attention_lanes for lane in future_lanes):
        return "useful-caution"
    return "overcautious"


def target_exception_history(
    target: dict[str, Any],
    exception_events: list[dict[str, Any]],
    historical_cases: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
    target_class_key: Callable[[dict[str, Any]], str],
    policy_flip_count: Callable[[list[str]], int],
    stable_policy_run_count: Callable[[list[str]], int],
    same_or_lower_pressure_path: Callable[[list[str]], bool],
    latest_case_outcome: Callable[[list[dict[str, Any]], list[dict[str, Any]]], str | None],
    trust_recovery_window_runs: int,
) -> dict[str, Any]:
    key = queue_identity(target)
    class_key = target_class_key(target)
    target_events = [event for event in exception_events if event.get("key") == key]
    class_events = [event for event in exception_events if event.get("class_key") == class_key]
    target_exception_events = [
        event
        for event in target_events
        if event.get("trust_exception_status") not in {None, "", "none"}
    ]
    class_exception_events = [
        event
        for event in class_events
        if event.get("trust_exception_status") not in {None, "", "none"}
    ]
    target_cases = [case for case in historical_cases if case.get("key") == key]
    class_cases = [case for case in historical_cases if case.get("class_key") == class_key]
    target_policies = [
        event.get("trust_policy", "monitor") for event in target_events[:trust_recovery_window_runs]
    ]
    target_lanes = [event.get("lane", "") for event in target_events[:trust_recovery_window_runs]]
    recent_exception_path = " -> ".join(
        event.get("trust_exception_status", "none") for event in target_exception_events[:4]
    ) or " -> ".join(
        event.get("trust_exception_status", "none") for event in class_exception_events[:4]
    )
    return {
        "stable_policy_run_count": stable_policy_run_count(target_policies),
        "recent_exception_path": recent_exception_path,
        "recent_policy_flip_count": policy_flip_count(target_policies),
        "same_or_lower_pressure_path": same_or_lower_pressure_path(target_lanes),
        "recent_reopened": any(
            event.get("decision_memory_status") == "reopened"
            or event.get("last_outcome") == "reopened"
            for event in target_events[:trust_recovery_window_runs]
        ),
        "latest_case_outcome": latest_case_outcome(target_cases, class_cases),
        "total_exception_count": len(target_cases) or len(class_cases),
        "overcautious_count": sum(
            1 for case in target_cases if case.get("case_outcome") == "overcautious"
        ),
        "target_cases": target_cases,
        "class_cases": class_cases,
    }


def exception_pattern_for_target(
    target: dict[str, Any],
    history_meta: dict[str, Any],
) -> tuple[str, str]:
    latest_case_outcome = history_meta.get("latest_case_outcome")
    if latest_case_outcome == "useful-caution":
        return (
            "useful-caution",
            "Recent soft caution was followed by renewed instability or unresolved pressure, so the softer posture still looks justified.",
        )
    if latest_case_outcome == "overcautious":
        return (
            "overcautious",
            "Recent soft caution was followed by stable recovery without renewed pressure, so the softer posture may now be more cautious than the evidence supports.",
        )
    if target.get("trust_exception_status") not in {None, "", "none"}:
        return (
            "insufficient-data",
            "There is not enough target-specific exception history yet to say whether recent soft caution is helping.",
        )
    return "none", ""


def false_positive_exception_hotspots(
    historical_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_groups = group_exception_hotspots(
        historical_cases, key_name="key", label_name="label", scope="target"
    )
    class_groups = group_exception_hotspots(
        historical_cases, key_name="class_key", label_name="class_key", scope="class"
    )
    hotspots = target_groups + class_groups
    hotspots.sort(
        key=lambda item: (
            -item.get("overcautious_count", 0),
            -item.get("exception_count", 0),
            item.get("label", ""),
        )
    )
    return [item for item in hotspots if item.get("overcautious_count", 0) > 0][:5]


def group_exception_hotspots(
    historical_cases: list[dict[str, Any]],
    *,
    key_name: str,
    label_name: str,
    scope: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in historical_cases:
        key = case.get(key_name, "")
        if not key:
            continue
        grouped.setdefault(key, []).append(case)

    hotspots: list[dict[str, Any]] = []
    for cases in grouped.values():
        overcautious_count = sum(1 for case in cases if case.get("case_outcome") == "overcautious")
        if overcautious_count <= 0:
            continue
        hotspots.append(
            {
                "scope": scope,
                "label": cases[0].get(label_name, ""),
                "overcautious_count": overcautious_count,
                "exception_count": len(cases),
                "recent_exception_path": " -> ".join(
                    case.get("trust_exception_status", "none") for case in cases[:4]
                ),
            }
        )
    return hotspots


def build_trust_policy_events(
    history: list[dict[str, Any]],
    *,
    current_primary_target: dict[str, Any],
    current_generated_at: str,
    queue_identity: Callable[[dict[str, Any]], str],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    history_window_runs: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": queue_identity(current_primary_target),
                "class_key": target_class_key(current_primary_target),
                "label": target_label(current_primary_target),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "generated_at": current_generated_at or "",
                "decision_memory_status": current_primary_target.get(
                    "decision_memory_status", ""
                ),
                "last_outcome": current_primary_target.get("last_outcome", ""),
            }
        )
    for entry in history[: history_window_runs - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        trust_policy = summary.get("primary_target_trust_policy", "")
        if not primary_target or not trust_policy:
            continue
        events.append(
            {
                "key": queue_identity(primary_target),
                "class_key": target_class_key(primary_target),
                "label": target_label(primary_target),
                "trust_policy": trust_policy,
                "generated_at": entry.get("generated_at", ""),
                "decision_memory_status": summary.get("decision_memory_status", ""),
                "last_outcome": summary.get("primary_target_last_outcome", ""),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def target_policy_history(
    target: dict[str, Any],
    policy_events: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
    target_class_key: Callable[[dict[str, Any]], str],
    policy_flip_count: Callable[[list[str]], int],
    strong_policy_failure_count: Callable[[dict[str, Any], list[dict[str, Any]]], int],
) -> dict[str, Any]:
    key = queue_identity(target)
    class_key = target_class_key(target)
    target_events = [event for event in policy_events if event.get("key") == key]
    class_events = [event for event in policy_events if event.get("class_key") == class_key]
    target_policies = [event.get("trust_policy", "monitor") for event in target_events]
    class_policies = [event.get("trust_policy", "monitor") for event in class_events]
    recent_policy_path = " -> ".join(target_policies[:4]) if target_policies else ""
    class_policy_path = " -> ".join(class_policies[:4]) if class_policies else ""
    return {
        "policy_flip_count": policy_flip_count(target_policies),
        "recent_policy_path": recent_policy_path or class_policy_path,
        "class_policy_flip_count": policy_flip_count(class_policies),
        "class_policy_path": class_policy_path,
        "strong_policy_failure_count": strong_policy_failure_count(target, policy_events),
    }


def policy_flip_hotspots(policy_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_hotspots = group_policy_hotspots(
        policy_events, key_name="key", label_name="label", scope="target"
    )
    class_hotspots = group_policy_hotspots(
        policy_events, key_name="class_key", label_name="class_key", scope="class"
    )
    hotspots = target_hotspots + [item for item in class_hotspots if item.get("flip_count", 0) >= 2]
    hotspots.sort(
        key=lambda item: (-item.get("flip_count", 0), item.get("label", ""), item.get("scope", ""))
    )
    return hotspots[:5]


def group_policy_hotspots(
    policy_events: list[dict[str, Any]],
    *,
    key_name: str,
    label_name: str,
    scope: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in policy_events:
        key = event.get(key_name, "")
        if not key:
            continue
        grouped.setdefault(key, []).append(event)

    hotspots: list[dict[str, Any]] = []
    for events in grouped.values():
        policies = [event.get("trust_policy", "monitor") for event in events]
        flip_count = policy_flip_count(policies)
        if flip_count <= 0:
            continue
        hotspots.append(
            {
                "scope": scope,
                "label": events[0].get(label_name, ""),
                "flip_count": flip_count,
                "recent_policy_path": " -> ".join(policies[:4]),
            }
        )
    return hotspots


def policy_flip_count(policies: list[str]) -> int:
    if len(policies) < 2:
        return 0
    flips = 0
    for previous, current in zip(policies, policies[1:]):
        if previous != current:
            flips += 1
    return flips


def strong_policy_failure_count(
    target: dict[str, Any],
    policy_events: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
) -> int:
    strong_policies = {"act-now", "act-with-review"}
    key = queue_identity(target)
    statuses = {"reopened", "persisting", "attempted"}
    count = 0
    for event in policy_events:
        if event.get("key") != key or event.get("trust_policy") not in strong_policies:
            continue
        history_status = event.get("decision_memory_status", "")
        last_outcome = event.get("last_outcome", "")
        if history_status in statuses or last_outcome in {"reopened", "no-change"}:
            count += 1
    return count


def trust_policy_exception_for_target(
    target: dict[str, Any],
    history_meta: dict[str, Any],
    confidence_calibration: dict[str, Any],
    *,
    current_bucket: int,
    recommendation_bucket: Callable[[dict[str, Any]], int],
) -> tuple[str, str, str, str]:
    status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    policy = target.get("trust_policy", "monitor")
    floor = (
        "act-with-review"
        if target.get("lane") == "blocked" and target.get("kind") == "setup"
        else "verify-first"
    )

    if (
        status == "noisy"
        and target.get("decision_memory_status") == "reopened"
        and current_bucket == recommendation_bucket(target)
    ):
        softened = soften_trust_policy(policy, floor=floor)
        if softened == policy:
            return (
                "none",
                "",
                policy,
                target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
            )
        return (
            "softened-for-noise",
            "Recent trust noise plus a reopened target warrants a softer verification-first posture.",
            softened,
            "Recent trust noise warrants verifying the latest state before treating this recommendation as fully stable.",
        )

    if history_meta.get("strong_policy_failure_count", 0) >= 2 and current_bucket == recommendation_bucket(target):
        softened = soften_trust_policy(policy, floor=floor)
        if softened == policy:
            return (
                "none",
                "",
                policy,
                target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
            )
        return (
            "softened-for-reopen-risk",
            "Repeated reopen or unresolved behavior after earlier strong recommendations warrants a softer trust posture.",
            softened,
            "Recent reopen or unresolved behavior means closure evidence should be re-verified before overcommitting.",
        )

    if max(
        history_meta.get("policy_flip_count", 0), history_meta.get("class_policy_flip_count", 0)
    ) >= 2 and current_bucket == recommendation_bucket(target):
        softened = soften_trust_policy(policy, floor=floor)
        if softened == policy:
            return (
                "none",
                "",
                policy,
                target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
            )
        return (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            softened,
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        )

    return (
        "none",
        "",
        policy,
        target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
    )


def soften_trust_policy(policy: str, *, floor: str) -> str:
    order = ["act-now", "act-with-review", "verify-first", "monitor"]
    if floor not in order:
        floor = "verify-first"
    if policy not in order:
        return floor
    softened_index = min(order.index(policy) + 1, len(order) - 1)
    floor_index = order.index(floor)
    if softened_index > floor_index:
        softened_index = floor_index
    return order[softened_index]
