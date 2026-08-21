from __future__ import annotations


def transition_closure_confidence_summary(
    label: str,
    primary_target: dict,
    pending_debt_hotspots: list[dict],
) -> str:
    likely_outcome = primary_target.get("transition_closure_likely_outcome", "none")
    score = primary_target.get("transition_closure_confidence_score", 0.05)
    if likely_outcome == "confirm-soon":
        return f"{label} still has a pending class signal that looks strong enough to confirm soon if the next run stays aligned ({score:.2f})."
    if likely_outcome == "hold":
        return f"{label} still has a viable pending class signal, but it is not strong enough to trust fully yet ({score:.2f})."
    if likely_outcome == "clear-risk":
        return f"{label} has a pending class signal that is fading and may clear before it confirms ({score:.2f})."
    if likely_outcome == "expire-risk":
        return f"{label} has a pending class signal that has lingered long enough to risk aging out ({score:.2f})."
    if likely_outcome == "blocked":
        reasons = primary_target.get("transition_closure_confidence_reasons") or []
        return reasons[0] if reasons else f"{label} still has local target instability blocking positive class strengthening."
    if likely_outcome == "insufficient-data":
        return f"{label} still has too little pending-transition history to judge whether the class signal is likely to confirm."
    if pending_debt_hotspots:
        hotspot = pending_debt_hotspots[0]
        return (
            f"Pending class signals are accumulating unresolved debt most around {hotspot.get('label', 'recent hotspots')}, "
            "so new pending states there should be treated more cautiously."
        )
    return "No active pending class transition needs closure-confidence scoring right now."


def class_pending_debt_summary(
    label: str,
    primary_target: dict,
    pending_debt_hotspots: list[dict],
    healthy_pending_resolution_hotspots: list[dict],
) -> str:
    status = primary_target.get("class_pending_debt_status", "none")
    if status == "active-debt":
        return f"{label} belongs to a class that keeps accumulating unresolved pending transitions, so fresh pending signals there should be treated more cautiously."
    if status == "clearing":
        return f"{label} belongs to a class that is resolving pending transitions more cleanly again, so pending debt is easing."
    if status == "watch":
        return f"{label} belongs to a class with mixed pending-transition outcomes, so watch whether new pending signals confirm or start to linger."
    if pending_debt_hotspots:
        hotspot = pending_debt_hotspots[0]
        return (
            f"Pending-transition debt is accumulating most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should not let weak pending states linger."
        )
    if healthy_pending_resolution_hotspots:
        hotspot = healthy_pending_resolution_hotspots[0]
        return (
            f"Pending transitions are resolving most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are showing healthier follow-through."
        )
    return "No class pending-debt pattern is strong enough to change how pending signals are interpreted yet."


def class_pending_resolution_summary(
    label: str,
    primary_target: dict,
    healthy_pending_resolution_hotspots: list[dict],
    pending_debt_hotspots: list[dict],
) -> str:
    status = primary_target.get("class_pending_debt_status", "none")
    if status == "clearing":
        return f"{label} belongs to a class that is resolving pending transitions more cleanly than it is stalling them."
    if status == "active-debt":
        return f"{label} belongs to a class where pending transitions are still stalling, expiring, or blocking more often than they resolve cleanly."
    if healthy_pending_resolution_hotspots:
        hotspot = healthy_pending_resolution_hotspots[0]
        return (
            f"Healthy pending-transition resolution is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are proving whether pending signals can clear or confirm cleanly."
        )
    if pending_debt_hotspots:
        hotspot = pending_debt_hotspots[0]
        return (
            f"Unresolved pending-transition debt is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should clear weak pending signals earlier."
        )
    return "No class-level pending-resolution pattern is strong enough to call out yet."


def pending_debt_freshness_summary(
    label: str,
    primary_target: dict,
    stale_pending_debt_hotspots: list[dict],
    fresh_pending_resolution_hotspots: list[dict],
) -> str:
    freshness_status = primary_target.get("pending_debt_freshness_status", "insufficient-data")
    if freshness_status == "fresh":
        return f"{label} still has fresh pending-transition memory, so recent class evidence should carry most of the closure forecast."
    if freshness_status == "mixed-age":
        return f"{label} still has useful pending-transition memory, but some of that signal is aging and should be weighted more cautiously."
    if freshness_status == "stale":
        return f"{label} is leaning on older pending-debt patterns more than fresh runs, so those class signals should not dominate the closure forecast."
    if fresh_pending_resolution_hotspots:
        hotspot = fresh_pending_resolution_hotspots[0]
        return (
            f"Fresh pending-resolution evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes deserve more trust than older pending-debt carry-forward."
        )
    if stale_pending_debt_hotspots:
        hotspot = stale_pending_debt_hotspots[0]
        return (
            f"Older pending-debt memory is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should not let stale debt dominate new pending forecasts."
        )
    return "Pending-transition memory is still too lightly exercised to say whether fresh or stale class debt should lead the forecast."


def pending_debt_decay_summary(
    label: str,
    primary_target: dict,
    fresh_pending_resolution_hotspots: list[dict],
    stale_pending_debt_hotspots: list[dict],
) -> str:
    freshness_status = primary_target.get("pending_debt_freshness_status", "insufficient-data")
    resolution_rate = primary_target.get("decayed_pending_resolution_rate", 0.0)
    debt_rate = primary_target.get("decayed_pending_debt_rate", 0.0)
    if freshness_status == "fresh" and resolution_rate >= debt_rate:
        return f"Fresh pending-transition evidence for {label} is resolving more cleanly than it is stalling, so the closure forecast can lean more on recent healthy outcomes."
    if freshness_status == "fresh":
        return f"Fresh pending-transition debt for {label} is still clustering, so unresolved pending states should be treated more cautiously than older clean outcomes suggest."
    if freshness_status == "stale":
        return f"Older pending-debt patterns are being down-weighted for {label}, so stale class drag should not control the live closure forecast."
    if fresh_pending_resolution_hotspots:
        hotspot = fresh_pending_resolution_hotspots[0]
        return (
            f"Fresh pending-resolution behavior is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are earning cleaner closure forecasts."
        )
    if stale_pending_debt_hotspots:
        hotspot = stale_pending_debt_hotspots[0]
        return (
            f"Stale pending-debt memory is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those older caution patterns should keep decaying instead of carrying forward indefinitely."
        )
    return "No strong pending-debt freshness trend is dominating the closure forecast yet."


def closure_forecast_reweighting_summary(
    label: str,
    primary_target: dict,
    supporting_pending_resolution_hotspots: list[dict],
    caution_pending_debt_hotspots: list[dict],
) -> str:
    direction = primary_target.get("closure_forecast_reweight_direction", "neutral")
    effect = primary_target.get("closure_forecast_reweight_effect", "none")
    score = primary_target.get("closure_forecast_reweight_score", 0.0)
    if effect == "confirm-support-strengthened":
        return f"{label} still needs persistence before confirmation, but fresh class resolution behavior is strengthening the pending forecast ({score:.2f})."
    if effect == "confirm-support-softened":
        return f"{label} still has a pending class signal, but older pending-transition evidence is softening how much confidence that forecast deserves ({score:.2f})."
    if effect == "clear-risk-strengthened":
        return f"{label} is seeing fresher unresolved pending debt, so the live pending forecast is leaning more strongly toward clearance or expiry risk ({score:.2f})."
    if effect == "clear-risk-softened":
        return f"{label} still carries some pending-debt caution, but older debt patterns are fading instead of fully driving the forecast ({score:.2f})."
    if direction == "supporting-confirmation":
        return f"Recent class resolution behavior around {label} is clean enough to strengthen the pending forecast, but not enough to confirm it yet ({score:.2f})."
    if direction == "supporting-clearance":
        return f"Recent class pending debt around {label} is still fresh enough to push the pending forecast toward clearance or expiry risk ({score:.2f})."
    if supporting_pending_resolution_hotspots:
        hotspot = supporting_pending_resolution_hotspots[0]
        return (
            f"Fresh closure support is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to cleaner pending confirmation paths."
        )
    if caution_pending_debt_hotspots:
        hotspot = caution_pending_debt_hotspots[0]
        return (
            f"Fresh pending-debt caution is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep weak pending states from lingering."
        )
    return "Class evidence is informative, but it is not strong enough to move the closure forecast by itself yet."
