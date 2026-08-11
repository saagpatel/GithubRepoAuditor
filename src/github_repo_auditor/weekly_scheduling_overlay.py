from __future__ import annotations

from typing import Any, Mapping

DEFAULT_WEEKLY_WORKFLOW_STEP = "Open the standard workbook first, then use --control-center for read-only triage."

APPROVAL_OVERRIDE_CANDIDATES = (
    ("top_needs_reapproval_approvals", "needs-reapproval", "Needs Re-Approval"),
    ("top_overdue_approval_followups", "overdue-follow-up", "Overdue Follow-Up"),
    ("top_ready_for_review_approvals", "ready-for-review", "Ready For Review"),
    ("top_due_soon_approval_followups", "due-soon-follow-up", "Due Soon Follow-Up"),
)


def _text(value: Any, fallback: str = "") -> str:
    return str(value or fallback).strip()


def _counts(operator_summary: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(operator_summary, Mapping):
        return {}
    counts = operator_summary.get("counts")
    return counts if isinstance(counts, Mapping) else {}


def _int_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _approval_command_hint(item: Mapping[str, Any]) -> str | None:
    for key in ("follow_up_command", "approval_command", "manual_apply_command"):
        text = _text(item.get(key))
        if text:
            return text
    return None


def _approval_safe_posture(command_hint: str | None) -> str:
    text = _text(command_hint)
    if not text:
        return "approval-review"
    if "--writeback-apply" in text:
        return "manual-mutation"
    if "--review-governance" in text or "--review-packet" in text:
        return "local-follow-up-review"
    if "--approve-" in text:
        return "local-approval-capture"
    return "bounded-command"


def _build_priority_evidence_items(items: list[dict[str, Any]], *, label_prefix: str) -> list[dict[str, Any]]:
    evidence_items: list[dict[str, Any]] = []
    for item in items[:3]:
        label = _text(item.get("label") or item.get("subject_key") or "Approval")
        command_hint = _approval_command_hint(item)
        evidence_item = {
            "label": f"{label_prefix}: {label}",
            "summary": _text(item.get("summary"), "No approval summary is recorded yet."),
            "kind": "approval-workflow",
            "safe_posture": _approval_safe_posture(command_hint),
        }
        if command_hint:
            evidence_item["command_hint"] = command_hint
        evidence_items.append(evidence_item)
    return evidence_items


def _approval_override_candidate(weekly_pack: Mapping[str, Any]) -> dict[str, Any] | None:
    for key, state, label_prefix in APPROVAL_OVERRIDE_CANDIDATES:
        items = list(weekly_pack.get(key) or [])
        if items:
            return {
                "key": key,
                "state": state,
                "label_prefix": label_prefix,
                "items": items,
            }
    return None


def _should_suppress_override(operator_summary: Mapping[str, Any] | None) -> bool:
    counts = _counts(operator_summary)
    return _int_count(counts.get("blocked")) > 0 or _int_count(counts.get("urgent")) > 0


def _approval_workflow_step(decision: str) -> str:
    decision = _text(decision)
    if not decision:
        return DEFAULT_WEEKLY_WORKFLOW_STEP
    if decision.endswith("."):
        decision = decision[:-1]
    if decision.lower().startswith(("open ", "use ", "stay ", "continue ")):
        return f"{decision}."
    return f"Open the standard workbook first, then {decision[0].lower()}{decision[1:]}."


def apply_weekly_scheduling_overlay(
    weekly_pack: Mapping[str, Any],
    operator_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    updated = dict(weekly_pack)
    if _should_suppress_override(operator_summary):
        return updated

    candidate = _approval_override_candidate(updated)
    if candidate is None:
        return updated

    approval_summary = _text(updated.get("approval_workflow_summary"))
    decision = _text(updated.get("next_approval_review"))
    if not approval_summary or not decision:
        return updated

    updated["what_to_do_this_week"] = decision
    updated["queue_pressure_summary"] = approval_summary
    updated["next_best_workflow_step"] = _approval_workflow_step(decision)
    updated["top_recommendation_summary"] = decision
    updated["weekly_priority_headline"] = approval_summary
    updated["weekly_priority_next_step"] = decision
    updated["weekly_priority_reason_codes"] = [
        "approval-aware-scheduling",
        "approval-workflow",
        candidate["state"],
    ]
    updated["weekly_priority_evidence_items"] = _build_priority_evidence_items(
        list(candidate["items"]),
        label_prefix=str(candidate["label_prefix"]),
    )
    updated["weekly_priority_override_state"] = str(candidate["state"])
    updated["weekly_priority_override_bucket"] = str(candidate["key"])
    return updated


def resolve_weekly_story_value(weekly_pack: Mapping[str, Any], key: str, *fallbacks: Any) -> str:
    story = weekly_pack.get("weekly_story_v1")
    if isinstance(story, Mapping):
        value = _text(story.get(key))
        if value:
            return value
    for fallback in fallbacks:
        value = _text(fallback)
        if value:
            return value
    return ""
