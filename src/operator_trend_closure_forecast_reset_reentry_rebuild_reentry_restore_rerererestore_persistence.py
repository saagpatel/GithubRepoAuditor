from __future__ import annotations

from typing import Any, Callable


def _rerererestore_text(text: str) -> str:
    transformed = text or ""
    protected = (
        ("re-re-restored", "__RRR_RESTORED__"),
        ("Re-re-restored", "__RRR_RESTORED_CAP__"),
        ("re-re-restoring", "__RRR_RESTORING__"),
        ("Re-re-restoring", "__RRR_RESTORING_CAP__"),
        ("rererestored", "__RERERERESTORED__"),
        ("Rererestored", "__RERERERESTORED_CAP__"),
        ("rererestoring", "__RERERERESTORING__"),
        ("Rererestoring", "__RERERERESTORING_CAP__"),
    )
    for old, marker in protected:
        transformed = transformed.replace(old, marker)
    transformed = transformed.replace("rererestore", "rerererestore")
    transformed = transformed.replace("Rererestore", "Rerererestore")
    transformed = transformed.replace("re-re-restore", "re-re-re-restore")
    transformed = transformed.replace("Re-re-restore", "Re-re-re-restore")
    finalized = (
        ("__RRR_RESTORED__", "re-re-re-restored"),
        ("__RRR_RESTORED_CAP__", "Re-re-re-restored"),
        ("__RRR_RESTORING__", "re-re-re-restoring"),
        ("__RRR_RESTORING_CAP__", "Re-re-re-restoring"),
        ("__RERERERESTORED__", "rerererestored"),
        ("__RERERERESTORED_CAP__", "Rerererestored"),
        ("__RERERERESTORING__", "rerererestoring"),
        ("__RERERERESTORING_CAP__", "Rerererestoring"),
    )
    for marker, new in finalized:
        transformed = transformed.replace(marker, new)
    return transformed


def _status_to_rererestore_status(status: str) -> str:
    return {
        "pending-confirmation-rebuild-reentry-rerererestore": (
            "pending-confirmation-rebuild-reentry-rererestore"
        ),
        "pending-clearance-rebuild-reentry-rerererestore": (
            "pending-clearance-rebuild-reentry-rererestore"
        ),
        "rerererestored-confirmation-rebuild-reentry": (
            "rererestored-confirmation-rebuild-reentry"
        ),
        "rerererestored-clearance-rebuild-reentry": (
            "rererestored-clearance-rebuild-reentry"
        ),
        "blocked": "blocked",
        "none": "none",
    }.get(status, "none")


def _persistence_status_to_rererestore_status(status: str) -> str:
    return {
        "just-rerererestored": "just-rererestored",
        "holding-confirmation-rebuild-reentry-rerererestore": (
            "holding-confirmation-rebuild-reentry-rererestore"
        ),
        "holding-clearance-rebuild-reentry-rerererestore": (
            "holding-clearance-rebuild-reentry-rererestore"
        ),
        "sustained-confirmation-rebuild-reentry-rerererestore": (
            "sustained-confirmation-rebuild-reentry-rererestore"
        ),
        "sustained-clearance-rebuild-reentry-rerererestore": (
            "sustained-clearance-rebuild-reentry-rererestore"
        ),
        "reversing": "reversing",
        "insufficient-data": "insufficient-data",
        "none": "none",
    }.get(status, "none")


def _refresh_status_to_rererestore_refresh_status(status: str) -> str:
    return {
        "recovering-confirmation-rebuild-reentry-rererestore-reset": (
            "recovering-confirmation-rebuild-reentry-rerestore-reset"
        ),
        "recovering-clearance-rebuild-reentry-rererestore-reset": (
            "recovering-clearance-rebuild-reentry-rerestore-reset"
        ),
        "rerererestoring-confirmation-rebuild-reentry": (
            "rererestoring-confirmation-rebuild-reentry"
        ),
        "rerererestoring-clearance-rebuild-reentry": (
            "rererestoring-clearance-rebuild-reentry"
        ),
        "reversing": "reversing",
        "blocked": "blocked",
        "none": "none",
    }.get(status, "none")


def _persistence_status_from_rererestore_status(status: str) -> str:
    return {
        "just-rererestored": "just-rerererestored",
        "holding-confirmation-rebuild-reentry-rererestore": (
            "holding-confirmation-rebuild-reentry-rerererestore"
        ),
        "holding-clearance-rebuild-reentry-rererestore": (
            "holding-clearance-rebuild-reentry-rerererestore"
        ),
        "sustained-confirmation-rebuild-reentry-rererestore": (
            "sustained-confirmation-rebuild-reentry-rerererestore"
        ),
        "sustained-clearance-rebuild-reentry-rererestore": (
            "sustained-clearance-rebuild-reentry-rerererestore"
        ),
        "reversing": "reversing",
        "insufficient-data": "insufficient-data",
        "none": "none",
    }.get(status, "none")


def _translate_target_for_persistence(target: dict[str, Any]) -> dict[str, Any]:
    return {
        **target,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            _status_to_rererestore_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
            _persistence_status_to_rererestore_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": (
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                    "none",
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": (
            _refresh_status_to_rererestore_refresh_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": (
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
                    "insufficient-data",
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": (
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
                    "none",
                )
            )
        ),
    }


def _translate_event_for_persistence(event: dict[str, Any]) -> dict[str, Any]:
    translated = _translate_target_for_persistence(event)
    translated["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"] = (
        _status_to_rererestore_status(
            str(
                event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
                    "none",
                )
            )
        )
    )
    translated[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
    ] = _persistence_status_to_rererestore_status(
        str(
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                "none",
            )
        )
    )
    translated[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
    ] = str(
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "none",
        )
    )
    return translated


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_text(
    text: str,
) -> str:
    return _rerererestore_text(text)


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
) -> dict[str, Any]:
    translated_target = _translate_target_for_persistence(target)
    translated_events = [
        _translate_event_for_persistence(event) for event in closure_forecast_events
    ]
    persistence_meta = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
            translated_target,
            translated_events,
            transition_history_meta,
        )
    )
    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": (
            persistence_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                0,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": (
            persistence_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                0.0,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": (
            _persistence_status_from_rererestore_status(
                str(
                    persistence_meta.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": (
            _rerererestore_text(
                str(
                    persistence_meta.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
                        "",
                    )
                )
            )
        ),
        "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path": (
            _rerererestore_text(
                str(
                    persistence_meta.get(
                        "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path",
                        "",
                    )
                )
            )
        ),
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
) -> dict[str, Any]:
    translated_target = _translate_target_for_persistence(target)
    translated_events = [
        _translate_event_for_persistence(event) for event in closure_forecast_events
    ]
    churn_meta = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target(
            translated_target,
            translated_events,
            transition_history_meta,
        )
    )
    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": churn_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
            0.0,
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": churn_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": _rerererestore_text(
            str(
                churn_meta.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
                    "",
                )
            )
        ),
        "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path": _rerererestore_text(
            str(
                churn_meta.get(
                    "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path",
                    "",
                )
            )
        ),
    }


def apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control(
    target: dict[str, Any],
    *,
    persistence_meta: dict[str, Any],
    churn_meta: dict[str, Any],
    transition_history_meta: dict[str, Any],
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reentry_status: str,
    reentry_reason: str,
    restore_status: str,
    restore_reason: str,
    rerestore_status: str,
    rerestore_reason: str,
    rererestore_status: str,
    rererestore_reason: str,
    apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control: Callable[
        ...,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    translated_target = _translate_target_for_persistence(target)
    translated_persistence_meta = {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
            _persistence_status_to_rererestore_status(
                str(
                    persistence_meta.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": (
            persistence_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason",
                "",
            )
        ),
    }
    translated_churn_meta = {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": (
            churn_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                "none",
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": (
            churn_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
                "",
            )
        ),
    }
    return (
        apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control(
            translated_target,
            persistence_meta=translated_persistence_meta,
            churn_meta=translated_churn_meta,
            transition_history_meta=transition_history_meta,
            closure_likely_outcome=closure_likely_outcome,
            closure_hysteresis_status=closure_hysteresis_status,
            closure_hysteresis_reason=closure_hysteresis_reason,
            transition_status=transition_status,
            transition_reason=transition_reason,
            resolution_status=resolution_status,
            resolution_reason=resolution_reason,
            reentry_status=reentry_status,
            reentry_reason=reentry_reason,
            restore_status=restore_status,
            restore_reason=restore_reason,
            rerestore_status=rerestore_status,
            rerestore_reason=rerestore_reason,
            rererestore_status=rererestore_status,
            rererestore_reason=rererestore_reason,
        )
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
    resolution_targets: list[dict[str, Any]],
    *,
    mode: str,
    target_class_key: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for target in resolution_targets:
        class_key = target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                "none",
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path",
                "",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
            ]
        ) > abs(
            existing[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
            ]
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-rerererestored":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
            )
            == "just-rerererestored"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                    0,
                ),
                -abs(
                    item.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
                        0.0,
                    )
                ),
                item.get("label", ""),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
            )
            in {
                "holding-confirmation-rebuild-reentry-rerererestore",
                "holding-clearance-rebuild-reentry-rerererestore",
                "sustained-confirmation-rebuild-reentry-rerererestore",
                "sustained-clearance-rebuild-reentry-rerererestore",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                    0,
                ),
                -abs(
                    item.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
                        0.0,
                    )
                ),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
            )
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
                    0.0,
                ),
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                    0,
                ),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary(
    primary_target: dict[str, Any],
    just_rerererestored_rebuild_reentry_hotspots: list[dict[str, Any]],
    holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
            "none",
        )
    )
    age_runs = int(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
            0,
        )
    )
    score = float(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
            0.0,
        )
    )
    if status == "just-rerererestored":
        return (
            f"{label} has only just re-re-re-restored stronger re-re-restored posture, "
            f"so it is still fragile ({score:.2f}; {age_runs} run)."
        )
    if status == "holding-confirmation-rebuild-reentry-rerererestore":
        return (
            f"Confirmation-side re-re-re-restored posture for {label} has held long "
            f"enough to keep the stronger re-re-restored forecast in place "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "holding-clearance-rebuild-reentry-rerererestore":
        return (
            f"Clearance-side re-re-re-restored posture for {label} has held long "
            f"enough to keep the stronger re-re-restored caution in place "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-confirmation-rebuild-reentry-rerererestore":
        return (
            f"Confirmation-side re-re-re-restored posture for {label} is now holding "
            f"with enough follow-through to trust the stronger re-re-restored forecast "
            f"more ({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-clearance-rebuild-reentry-rerererestore":
        return (
            f"Clearance-side re-re-re-restored posture for {label} is now holding with "
            f"enough follow-through to trust the stronger re-re-restored caution more "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "reversing":
        return (
            f"The re-re-re-restored rebuilt re-entry posture for {label} is already "
            f"weakening, so it is being softened again ({score:.2f})."
        )
    if status == "insufficient-data":
        return (
            f"Re-re-re-restored rebuilt re-entry for {label} is still too lightly "
            "exercised to say whether the stronger posture can hold."
        )
    if just_rerererestored_rebuild_reentry_hotspots:
        hotspot = just_rerererestored_rebuild_reentry_hotspots[0]
        return (
            "Newly re-re-re-restored posture is most fragile around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes still need "
            "follow-through before the stronger re-re-restored posture can be trusted."
        )
    if holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots:
        hotspot = holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots[0]
        return (
            "Re-re-re-restored posture is holding most cleanly around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes are closest "
            "to keeping the stronger re-re-restored posture safely."
        )
    return (
        "No re-re-re-restored rebuilt re-entry posture is active enough yet to judge "
        "whether it can hold."
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary(
    primary_target: dict[str, Any],
    reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "none",
        )
    )
    score = float(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
            0.0,
        )
    )
    if status == "watch":
        return (
            f"Re-re-re-restored rebuilt re-entry for {label} is wobbling enough that "
            f"stronger re-re-restored posture may soften soon ({score:.2f})."
        )
    if status == "churn":
        return (
            f"Re-re-re-restored rebuilt re-entry for {label} is flipping enough that "
            f"stronger re-re-restored posture should be softened quickly ({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
                "Local target instability is preventing positive confirmation-side "
                f"re-re-re-restored hold for {label}.",
            )
        )
    if reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots:
        hotspot = reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots[0]
        return (
            "Re-re-re-restored rebuilt re-entry churn is highest around "
            f"{hotspot.get('label', 'recent hotspots')}, so stronger re-re-restored "
            "posture there should soften quickly if the wobble continues."
        )
    return "No meaningful re-re-re-restored rebuilt re-entry churn is active right now."


def apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], Any],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[
        [dict[str, Any], list[dict[str, Any]]], dict[str, Any]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control: Callable[
        ...,
        dict[str, Any],
    ],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    class_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs: int,
) -> dict[str, Any]:
    del confidence_calibration
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": 0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": "No reset re-entry rebuild re-entry restore re-re-re-restore persistence is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": class_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs,
            "just_rerererestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": "No reset re-entry rebuild re-entry restore re-re-re-restore churn is recorded because there is no active target.",
            "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        persistence_age_runs = 0
        persistence_score = 0.0
        persistence_status = "none"
        persistence_reason = ""
        persistence_path = ""
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
        churn_path = ""
        closure_likely_outcome = str(
            target.get("transition_closure_likely_outcome", "none")
        )
        closure_hysteresis_status = str(
            target.get("closure_forecast_hysteresis_status", "none")
        )
        closure_hysteresis_reason = str(
            target.get("closure_forecast_hysteresis_reason", "")
        )
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(target.get("class_transition_resolution_status", "none"))
        resolution_reason = str(target.get("class_transition_resolution_reason", ""))
        reentry_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        )
        reentry_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_reason", "")
        )
        restore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none"
            )
        )
        restore_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reason", "")
        )
        rerestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
                "none",
            )
        )
        rerestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason",
                "",
            )
        )
        rererestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                "none",
            )
        )
        rererestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason",
                "",
            )
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(
                target,
                transition_events,
            )
            persistence_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            churn_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            persistence_age_runs = int(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs"
                ]
            )
            persistence_score = float(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
                ]
            )
            persistence_status = str(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
                ]
            )
            persistence_reason = str(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason"
                ]
            )
            persistence_path = str(
                persistence_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path"
                ]
            )
            churn_score = float(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score"
                ]
            )
            churn_status = str(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
                ]
            )
            churn_reason = str(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason"
                ]
            )
            churn_path = str(
                churn_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path"
                ]
            )
            control_updates = (
                apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control(
                    target,
                    persistence_meta=persistence_meta,
                    churn_meta=churn_meta,
                    transition_history_meta=transition_history_meta,
                    closure_likely_outcome=closure_likely_outcome,
                    closure_hysteresis_status=closure_hysteresis_status,
                    closure_hysteresis_reason=closure_hysteresis_reason,
                    transition_status=transition_status,
                    transition_reason=transition_reason,
                    resolution_status=resolution_status,
                    resolution_reason=resolution_reason,
                    reentry_status=reentry_status,
                    reentry_reason=reentry_reason,
                    restore_status=restore_status,
                    restore_reason=restore_reason,
                    rerestore_status=rerestore_status,
                    rerestore_reason=rerestore_reason,
                    rererestore_status=rererestore_status,
                    rererestore_reason=rererestore_reason,
                )
            )
            closure_likely_outcome = str(control_updates["transition_closure_likely_outcome"])
            closure_hysteresis_status = str(
                control_updates["closure_forecast_hysteresis_status"]
            )
            closure_hysteresis_reason = str(
                control_updates["closure_forecast_hysteresis_reason"]
            )
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            reentry_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_status"]
            )
            reentry_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_reason"]
            )
            restore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_status"
                ]
            )
            restore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
                ]
            )
            rerestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
                ]
            )
            rerestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
                ]
            )
            rererestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
                ]
            )
            rererestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
                ]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": persistence_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path": persistence_path,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": churn_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": churn_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": churn_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path": churn_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    just_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            resolution_targets,
            mode="just-rerererestored",
            target_class_key=target_class_key,
        )
    )
    holding_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            resolution_targets,
            mode="holding",
            target_class_key=target_class_key,
        )
    )
    churn_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            resolution_targets,
            mode="churn",
            target_class_key=target_class_key,
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
            0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary(
                primary_target,
                just_hotspots,
                holding_hotspots,
                target_label=target_label,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": class_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs,
        "just_rerererestored_rebuild_reentry_hotspots": just_hotspots,
        "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": holding_hotspots,
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary(
                primary_target,
                churn_hotspots,
                target_label=target_label,
            )
        ),
        "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": churn_hotspots,
    }
