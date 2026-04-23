def operator_follow_through_value(data: dict) -> str:
    summary = data.get("operator_summary") or {}
    return summary.get("follow_through_summary", "") or "No follow-through signal is recorded yet."


def operator_follow_through_details(data: dict) -> tuple[str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    follow_through = (
        summary.get("follow_through_summary", "") or "No follow-through signal is recorded yet."
    )
    checkpoint = (
        summary.get("follow_through_checkpoint_summary", "")
        or "Use the next run or linked artifact to confirm whether the recommendation moved."
    )
    escalation = (
        summary.get("follow_through_escalation_summary", "")
        or "No stronger follow-through escalation is currently surfaced."
    )
    top_stale = list(summary.get("top_stale_follow_through_items") or [])
    top_unattempted = list(summary.get("top_unattempted_items") or [])
    top_overdue = list(summary.get("top_overdue_follow_through_items") or [])
    top_escalation = list(summary.get("top_escalation_items") or [])
    top_item = (
        top_overdue[0]
        if top_overdue
        else (
            top_escalation[0]
            if top_escalation
            else (top_stale[0] if top_stale else (top_unattempted[0] if top_unattempted else {}))
        )
    )
    top_label = (
        f"{top_item.get('repo')}: {top_item.get('title')}"
        if top_item.get("repo")
        else top_item.get("title", "")
    ) or "No outstanding follow-through hotspot"
    return (
        follow_through,
        checkpoint,
        escalation,
        top_label,
        top_item.get("follow_through_escalation_summary", "")
        or top_item.get("follow_through_summary", "")
        or "No outstanding follow-through hotspot",
    )


def operator_follow_through_recovery_details(data: dict) -> tuple[str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    recovery = (
        summary.get("follow_through_recovery_summary", "")
        or "No follow-through recovery or escalation-retirement signal is currently surfaced."
    )
    persistence = (
        summary.get("follow_through_recovery_persistence_summary", "")
        or "No follow-through recovery persistence signal is currently surfaced."
    )
    churn = (
        summary.get("follow_through_relapse_churn_summary", "")
        or "No relapse churn is currently surfaced."
    )
    top_relapsing = list(summary.get("top_relapsing_follow_through_items") or [])
    top_retiring = list(summary.get("top_retiring_follow_through_items") or [])
    top_fragile = list(summary.get("top_fragile_recovery_items") or [])
    top_churn = list(summary.get("top_churn_follow_through_items") or [])
    top_item = (
        top_relapsing[0]
        if top_relapsing
        else (top_retiring[0] if top_retiring else (top_fragile[0] if top_fragile else {}))
    )
    top_label = (
        f"{top_item.get('repo')}: {top_item.get('title')}"
        if top_item.get("repo")
        else top_item.get("title", "")
    ) or "No active recovery or retirement hotspot"
    top_summary = (
        top_item.get("follow_through_recovery_summary", "")
        or top_item.get("follow_through_recovery_persistence_summary", "")
        or top_item.get("follow_through_escalation_summary", "")
        or "No active recovery or retirement hotspot"
    )
    churn_item = top_churn[0] if top_churn else {}
    churn_label = (
        f"{churn_item.get('repo')}: {churn_item.get('title')}"
        if churn_item.get("repo")
        else churn_item.get("title", "")
    ) or "No relapse-churn hotspot"
    return recovery, persistence, churn, top_label, top_summary or persistence, churn_label


def operator_follow_through_freshness_details(data: dict) -> tuple[str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    freshness = (
        summary.get("follow_through_recovery_freshness_summary", "")
        or "No follow-through recovery freshness signal is currently surfaced."
    )
    memory_reset = (
        summary.get("follow_through_recovery_memory_reset_summary", "")
        or "No follow-through recovery memory reset signal is currently surfaced."
    )
    top_stale = list(summary.get("top_stale_recovery_items") or [])
    top_reset = list(summary.get("top_reset_recovery_items") or [])
    top_rebuilding = list(summary.get("top_rebuilding_recovery_items") or [])
    top_item = top_stale[0] if top_stale else (top_reset[0] if top_reset else {})
    top_label = (
        f"{top_item.get('repo')}: {top_item.get('title')}"
        if top_item.get("repo")
        else top_item.get("title", "")
    ) or "No stale recovery-memory hotspot"
    top_summary = (
        top_item.get("follow_through_recovery_freshness_summary", "")
        or top_item.get("follow_through_recovery_memory_reset_summary", "")
        or freshness
    )
    rebuild_item = top_rebuilding[0] if top_rebuilding else {}
    rebuild_label = (
        f"{rebuild_item.get('repo')}: {rebuild_item.get('title')}"
        if rebuild_item.get("repo")
        else rebuild_item.get("title", "")
    ) or "No rebuilding recovery-memory hotspot"
    return freshness, memory_reset, top_label, top_summary, rebuild_label


def operator_follow_through_rebuild_details(
    data: dict,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    rebuild_strength = (
        summary.get("follow_through_recovery_rebuild_strength_summary", "")
        or "No follow-through recovery rebuild-strength signal is currently surfaced."
    )
    reacquisition = (
        summary.get("follow_through_recovery_reacquisition_summary", "")
        or "No follow-through recovery reacquisition signal is currently surfaced."
    )
    durability = (
        summary.get("follow_through_recovery_reacquisition_durability_summary", "")
        or "No follow-through reacquisition durability signal is currently surfaced."
    )
    confidence = (
        summary.get("follow_through_recovery_reacquisition_consolidation_summary", "")
        or "No follow-through reacquisition confidence-consolidation signal is currently surfaced."
    )
    top_rebuilding = list(summary.get("top_rebuilding_recovery_strength_items") or [])
    top_reacquiring = list(summary.get("top_reacquiring_recovery_items") or [])
    top_reacquired = list(summary.get("top_reacquired_recovery_items") or [])
    top_fragile = list(summary.get("top_fragile_reacquisition_items") or [])
    top_just = list(summary.get("top_just_reacquired_items") or [])
    top_holding = list(summary.get("top_holding_reacquired_items") or [])
    top_durable = list(summary.get("top_durable_reacquired_items") or [])
    top_softening = list(summary.get("top_softening_reacquired_items") or [])
    top_fragile_confidence = list(summary.get("top_fragile_reacquisition_confidence_items") or [])
    rebuilding_item = top_rebuilding[0] if top_rebuilding else {}
    rebuilding_label = (
        f"{rebuilding_item.get('repo')}: {rebuilding_item.get('title')}"
        if rebuilding_item.get("repo")
        else rebuilding_item.get("title", "")
    ) or "No rebuilding-after-reset hotspot"
    reacquiring_item = top_reacquiring[0] if top_reacquiring else {}
    reacquiring_label = (
        f"{reacquiring_item.get('repo')}: {reacquiring_item.get('title')}"
        if reacquiring_item.get("repo")
        else reacquiring_item.get("title", "")
    ) or "No near-reacquisition hotspot"
    reacquired_item = top_reacquired[0] if top_reacquired else {}
    reacquired_label = (
        f"{reacquired_item.get('repo')}: {reacquired_item.get('title')}"
        if reacquired_item.get("repo")
        else reacquired_item.get("title", "")
    ) or "No re-acquired hotspot"
    fragile_item = top_fragile[0] if top_fragile else {}
    fragile_label = (
        f"{fragile_item.get('repo')}: {fragile_item.get('title')}"
        if fragile_item.get("repo")
        else fragile_item.get("title", "")
    ) or "No fragile reacquisition hotspot"
    just_item = top_just[0] if top_just else {}
    just_label = (
        f"{just_item.get('repo')}: {just_item.get('title')}"
        if just_item.get("repo")
        else just_item.get("title", "")
    ) or "No newly re-acquired hotspot"
    holding_item = top_holding[0] if top_holding else {}
    holding_label = (
        f"{holding_item.get('repo')}: {holding_item.get('title')}"
        if holding_item.get("repo")
        else holding_item.get("title", "")
    ) or "No holding re-acquisition hotspot"
    durable_item = top_durable[0] if top_durable else {}
    durable_label = (
        f"{durable_item.get('repo')}: {durable_item.get('title')}"
        if durable_item.get("repo")
        else durable_item.get("title", "")
    ) or "No durable re-acquisition hotspot"
    softening_item = top_softening[0] if top_softening else {}
    softening_label = (
        f"{softening_item.get('repo')}: {softening_item.get('title')}"
        if softening_item.get("repo")
        else softening_item.get("title", "")
    ) or "No softening re-acquisition hotspot"
    fragile_confidence_item = top_fragile_confidence[0] if top_fragile_confidence else {}
    fragile_confidence_label = (
        f"{fragile_confidence_item.get('repo')}: {fragile_confidence_item.get('title')}"
        if fragile_confidence_item.get("repo")
        else fragile_confidence_item.get("title", "")
    ) or "No fragile re-acquisition confidence hotspot"
    return (
        rebuild_strength,
        reacquisition,
        durability,
        confidence,
        rebuilding_label,
        reacquiring_label,
        reacquired_label,
        fragile_label,
        just_label,
        holding_label,
        durable_label,
        softening_label,
        fragile_confidence_label,
    )


def operator_follow_through_reacquisition_retirement_details(
    data: dict,
) -> tuple[str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    softening_decay = (
        summary.get("follow_through_reacquisition_softening_decay_summary", "")
        or "No reacquisition softening-decay signal is currently surfaced."
    )
    confidence_retirement = (
        summary.get("follow_through_reacquisition_confidence_retirement_summary", "")
        or "No reacquisition confidence-retirement signal is currently surfaced."
    )
    top_softening = list(summary.get("top_softening_reacquisition_items") or [])
    top_revalidation = list(summary.get("top_revalidation_needed_reacquisition_items") or [])
    top_retired = list(summary.get("top_retired_reacquisition_confidence_items") or [])
    softening_item = top_softening[0] if top_softening else {}
    softening_label = (
        f"{softening_item.get('repo')}: {softening_item.get('title')}"
        if softening_item.get("repo")
        else softening_item.get("title", "")
    ) or "No reacquisition softening hotspot"
    revalidation_item = top_revalidation[0] if top_revalidation else {}
    revalidation_label = (
        f"{revalidation_item.get('repo')}: {revalidation_item.get('title')}"
        if revalidation_item.get("repo")
        else revalidation_item.get("title", "")
    ) or "No reacquisition revalidation hotspot"
    retired_item = top_retired[0] if top_retired else {}
    retired_label = (
        f"{retired_item.get('repo')}: {retired_item.get('title')}"
        if retired_item.get("repo")
        else retired_item.get("title", "")
    ) or "No retired re-acquisition confidence hotspot"
    return (
        softening_decay,
        confidence_retirement,
        softening_label,
        revalidation_label,
        retired_label,
    )


def operator_follow_through_revalidation_recovery_details(
    data: dict,
) -> tuple[str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    revalidation_recovery = summary.get(
        "follow_through_reacquisition_revalidation_recovery_summary", ""
    ) or ("No post-revalidation recovery or confidence re-earning signal is currently surfaced.")
    top_under_revalidation = list(summary.get("top_under_revalidation_recovery_items") or [])
    top_rebuilding = list(summary.get("top_rebuilding_restored_confidence_items") or [])
    top_reearning = list(summary.get("top_reearning_confidence_items") or [])
    top_just_reearned = list(summary.get("top_just_reearned_confidence_items") or [])
    top_holding_reearned = list(summary.get("top_holding_reearned_confidence_items") or [])

    def _label(item: dict, fallback: str) -> str:
        return (
            f"{item.get('repo')}: {item.get('title')}"
            if item.get("repo")
            else item.get("title", "")
        ) or fallback

    return (
        revalidation_recovery,
        _label(
            top_under_revalidation[0] if top_under_revalidation else {},
            "No under-revalidation recovery hotspot",
        ),
        _label(
            top_rebuilding[0] if top_rebuilding else {},
            "No rebuilding restored-confidence hotspot",
        ),
        _label(top_reearning[0] if top_reearning else {}, "No confidence re-earning hotspot"),
        _label(
            top_just_reearned[0] if top_just_reearned else {},
            "No just re-earned confidence hotspot",
        ),
        _label(
            top_holding_reearned[0] if top_holding_reearned else {},
            "No holding re-earned confidence hotspot",
        ),
    )
