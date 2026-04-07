from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analyst_views import build_analyst_context
from src.baseline_context import (
    build_filter_signature_from_args,
    build_requested_baseline_context,
    compare_baseline_context,
    extract_baseline_context,
)
from src.warehouse import (
    load_latest_audit_runs,
    load_review_history,
    load_watch_checkpoint,
)

FULL_REFRESH_DAYS = 7

MATERIALITY_THRESHOLDS = {
    "low": {"score": 0.03, "lens": 0.05, "security": 0.03, "hotspot": 0.5},
    "standard": {"score": 0.05, "lens": 0.07, "security": 0.05, "hotspot": 0.6},
    "high": {"score": 0.08, "lens": 0.1, "security": 0.08, "hotspot": 0.75},
}


@dataclass
class WatchPlan:
    mode: str
    reason: str
    filter_signature: str
    scoring_profile: str
    full_refresh_due: bool = False
    latest_trusted_baseline: dict = field(default_factory=dict)


def _latest_baseline_reference(run: dict | None) -> dict:
    if not run:
        return {}
    baseline_context = extract_baseline_context(run)
    return {
        "run_id": run.get("run_id", ""),
        "generated_at": run.get("generated_at", ""),
        "report_path": run.get("report_path", ""),
        "baseline_signature": baseline_context.get("baseline_signature") or run.get("baseline_signature", ""),
    }


def choose_watch_plan(output_dir: Path, args, *, scoring_profile: str) -> WatchPlan:
    strategy = getattr(args, "watch_strategy", "adaptive")
    signature = build_filter_signature_from_args(args, scoring_profile=scoring_profile)
    requested_context = build_requested_baseline_context(args, scoring_profile=scoring_profile)
    checkpoint = load_watch_checkpoint(output_dir, getattr(args, "username", ""))
    runs = load_latest_audit_runs(output_dir, getattr(args, "username", ""), limit=20)
    latest = runs[0] if runs else None
    latest_full = next((run for run in runs if run.get("run_mode") == "full"), None)
    latest_full_context = extract_baseline_context(latest_full)
    latest_baseline_reference = _latest_baseline_reference(latest_full)
    latest_full_mismatches = compare_baseline_context(
        requested_context,
        latest_full_context,
        include_size=False,
    ) if latest_full_context else []

    if strategy == "full":
        return WatchPlan(
            "full",
            "explicit-full-strategy",
            signature,
            scoring_profile,
            latest_trusted_baseline=latest_baseline_reference,
        )

    if strategy == "incremental":
        if latest_full and latest_full_context and not latest_full_mismatches:
            return WatchPlan(
                "incremental",
                "explicit-incremental-strategy",
                signature,
                scoring_profile,
                latest_trusted_baseline=latest_baseline_reference,
            )
        fallback_reason = "filter-or-profile-changed" if latest_full and latest_full_mismatches else "incremental-needs-baseline"
        return WatchPlan(
            "full",
            fallback_reason,
            signature,
            scoring_profile,
            latest_trusted_baseline=latest_baseline_reference,
        )

    if not latest or not latest_full or not latest_full_context:
        return WatchPlan(
            "full",
            "missing-trustworthy-baseline",
            signature,
            scoring_profile,
            latest_trusted_baseline=latest_baseline_reference,
        )

    if latest_full_mismatches:
        return WatchPlan(
            "full",
            "filter-or-profile-changed",
            signature,
            scoring_profile,
            latest_trusted_baseline=latest_baseline_reference,
        )

    checkpoint_signature = (checkpoint or {}).get("filter_signature") or (checkpoint or {}).get("baseline_signature")
    if checkpoint_signature and checkpoint_signature != signature:
        return WatchPlan(
            "full",
            "filter-or-profile-changed",
            signature,
            scoring_profile,
            latest_trusted_baseline=latest_baseline_reference,
        )

    last_full_at = _parse_ts(latest_full.get("generated_at"))
    full_refresh_due = (
        last_full_at is None
        or datetime.now(timezone.utc) - last_full_at >= timedelta(days=FULL_REFRESH_DAYS)
    )
    if full_refresh_due:
        return WatchPlan(
            "full",
            "full-refresh-due",
            signature,
            scoring_profile,
            full_refresh_due=True,
            latest_trusted_baseline=latest_baseline_reference,
        )

    return WatchPlan(
        "incremental",
        "adaptive-incremental",
        signature,
        scoring_profile,
        latest_trusted_baseline=latest_baseline_reference,
    )


def build_review_bundle(
    report_data: dict,
    *,
    output_dir: Path,
    diff_data: dict | None,
    materiality: str = "standard",
    portfolio_profile: str = "default",
    collection_name: str | None = None,
    watch_state: dict | None = None,
    emit_when_quiet: bool = False,
) -> dict:
    thresholds = MATERIALITY_THRESHOLDS.get(materiality, MATERIALITY_THRESHOLDS["standard"])
    context = build_analyst_context(
        report_data,
        profile_name=portfolio_profile,
        collection_name=collection_name,
    )
    material_changes = evaluate_material_changes(
        report_data,
        diff_data=diff_data,
        thresholds=thresholds,
    )
    material_fingerprint = _fingerprint(material_changes)
    review_targets = _build_review_targets(report_data, material_changes, context)
    decisions = _build_review_decisions(report_data, material_changes)
    emitted = bool(material_changes) or emit_when_quiet
    summary = {
        "review_id": f"{report_data.get('username', 'unknown')}:{datetime.now(timezone.utc).isoformat()}:review",
        "source_run_id": f"{report_data.get('username', 'unknown')}:{report_data.get('generated_at', '')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "materiality": materiality,
        "emitted": emitted,
        "safe_to_defer": not material_changes,
        "material_change_count": len(material_changes),
        "top_change_types": sorted({change["change_type"] for change in material_changes}),
        "profile_name": context["profile_name"],
        "collection_name": context["collection_name"],
        "material_fingerprint": material_fingerprint,
        "review_sync": watch_state.get("review_sync", "local") if watch_state else "local",
        "decisions": decisions,
    }
    alerts = [
        {
            "title": change["title"],
            "summary": change["summary"],
            "severity": change["severity"],
            "recommended_next_step": change["recommended_next_step"],
        }
        for change in material_changes[:10]
    ]
    history = load_review_history(output_dir, report_data.get("username", ""), limit=10)
    return {
        "review_summary": summary,
        "review_alerts": alerts,
        "material_changes": material_changes,
        "review_targets": review_targets,
        "review_history": history,
        "watch_state": watch_state or {},
    }


def evaluate_material_changes(
    report_data: dict,
    *,
    diff_data: dict | None,
    thresholds: dict[str, float],
) -> list[dict]:
    changes: list[dict] = []
    repo_index = {
        audit.get("metadata", {}).get("name", ""): audit
        for audit in report_data.get("audits", [])
    }

    if diff_data:
        for item in diff_data.get("tier_changes", []):
            changes.append(
                _change(
                    "tier-change",
                    item.get("name", ""),
                    0.9,
                    f"{item.get('name', 'Repo')} changed tier",
                    f"{item.get('old_tier', 'unknown')} -> {item.get('new_tier', 'unknown')}",
                    "Inspect the repo change and update its operating priority.",
                    details=item,
                )
            )

        for item in diff_data.get("repo_changes", []):
            repo_name = item.get("name", "")
            delta = abs(item.get("delta", 0.0))
            if delta >= thresholds["score"]:
                changes.append(
                    _change(
                        "score-delta",
                        repo_name,
                        min(1.0, delta * 10),
                        f"{repo_name} moved materially",
                        f"Overall score changed by {item.get('delta', 0):+.3f}.",
                        "Review whether this change should affect priority or tier.",
                        details=item,
                    )
                )

            for lens_name, lens_delta in (item.get("lens_deltas") or {}).items():
                if abs(lens_delta) >= thresholds["lens"]:
                    changes.append(
                        _change(
                            "lens-delta",
                            repo_name,
                            min(1.0, abs(lens_delta) * 8),
                            f"{repo_name} shifted on {lens_name.replace('_', ' ')}",
                            f"{lens_name} changed by {lens_delta:+.3f}.",
                            "Review this lens change before reprioritizing actions.",
                            details={"lens": lens_name, "delta": lens_delta, **item},
                        )
                    )

            security_change = item.get("security_change", {})
            if (
                security_change.get("old_label") != security_change.get("new_label")
                or abs(security_change.get("delta", 0.0)) >= thresholds["security"]
            ):
                changes.append(
                    _change(
                        "security-change",
                        repo_name,
                        min(1.0, abs(security_change.get("delta", 0.0)) * 10 + 0.3),
                        f"{repo_name} security posture changed",
                        f"{security_change.get('old_label', 'unknown')} -> {security_change.get('new_label', 'unknown')}",
                        "Inspect the repo security state before approving new actions.",
                        details=security_change,
                    )
                )

            hotspot_change = item.get("hotspot_change", {})
            current_hotspots = repo_index.get(repo_name, {}).get("hotspots", [])
            current_severity = max((entry.get("severity", 0.0) for entry in current_hotspots), default=0.0)
            if (
                hotspot_change.get("new_count", 0) > hotspot_change.get("old_count", 0)
                or hotspot_change.get("old_primary") != hotspot_change.get("new_primary")
            ) and current_severity >= thresholds["hotspot"]:
                changes.append(
                    _change(
                        "hotspot-change",
                        repo_name,
                        current_severity,
                        f"{repo_name} has a new or worsened hotspot",
                        hotspot_change.get("new_primary", "Hotspot changed"),
                        "Inspect the hotspot and decide whether it belongs in the next campaign.",
                        details={**hotspot_change, "severity": current_severity},
                    )
                )

    for drift in report_data.get("managed_state_drift", []):
        changes.append(
            _change(
                "campaign-drift",
                drift.get("repo", drift.get("repo_full_name", "")),
                _severity_value(drift.get("severity", "medium")),
                f"{drift.get('repo', drift.get('repo_full_name', 'Repo'))} has campaign drift",
                drift.get("drift_type", "Managed state drift detected"),
                "Review drift before applying or closing campaign actions.",
                details=drift,
            )
        )

    for drift in report_data.get("governance_drift", []):
        changes.append(
            _change(
                "governance-drift",
                drift.get("repo_full_name", ""),
                _severity_value(drift.get("severity", "medium")),
                f"{drift.get('repo_full_name', 'Repo')} has governance drift",
                drift.get("drift_type", "Governance drift detected"),
                "Review governance drift before applying governed controls.",
                details=drift,
            )
        )

    governance_preview = report_data.get("governance_preview", {})
    applyable_count = governance_preview.get("applyable_count", 0)
    if applyable_count:
        changes.append(
            _change(
                "governance-ready",
                "",
                min(1.0, 0.4 + applyable_count * 0.1),
                "Governed controls are ready to approve",
                f"{applyable_count} governed security controls are applyable.",
                "Review and approve governed controls if the repos are ready.",
                details=governance_preview,
            )
        )

    if report_data.get("rollback_preview", {}).get("available"):
        changes.append(
            _change(
                "rollback-exposure",
                "",
                0.45,
                "Rollbackable managed state exists",
                f"{report_data.get('rollback_preview', {}).get('item_count', 0)} rollback items are available.",
                "Check whether recent managed changes still look correct.",
                details=report_data.get("rollback_preview", {}),
            )
        )

    changes.sort(key=lambda item: (item["severity"], item.get("repo_name", "")), reverse=True)
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for change in changes:
        key = (change["change_type"], change.get("repo_name", ""), change["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(change)
    return deduped


def _build_review_targets(report_data: dict, material_changes: list[dict], context: dict) -> list[dict]:
    targets: list[dict] = []
    ranked = {entry["name"]: entry for entry in context["ranked_audits"]}
    seen: set[str] = set()
    for change in material_changes:
        repo_name = change.get("repo_name", "")
        if not repo_name or repo_name in seen:
            continue
        ranked_entry = ranked.get(repo_name, {})
        targets.append(
            {
                "repo": repo_name,
                "reason": change["summary"],
                "severity": change["severity"],
                "recommended_next_step": change["recommended_next_step"],
                "tier": ranked_entry.get("tier", ""),
                "security_label": ranked_entry.get("security_label", "unknown"),
                "profile_score": ranked_entry.get("profile_score", 0.0),
            }
        )
        seen.add(repo_name)
        if len(targets) >= 8:
            break
    if not targets:
        for entry in context["ranked_audits"][:5]:
            targets.append(
                {
                    "repo": entry["name"],
                    "reason": "No material changes crossed the current threshold.",
                    "severity": 0.2,
                    "recommended_next_step": "Safe to defer.",
                    "tier": entry["tier"],
                    "security_label": entry["security_label"],
                    "profile_score": entry["profile_score"],
                }
            )
    return targets


def _build_review_decisions(report_data: dict, material_changes: list[dict]) -> list[dict]:
    if not material_changes:
        return [{"decision": "safe-to-defer", "reason": "No material changes crossed the current threshold."}]

    decisions: list[dict] = []
    if report_data.get("managed_state_drift"):
        decisions.append({"decision": "review-campaign-drift", "reason": "Campaign drift exists and should be reviewed before more apply work."})
    if report_data.get("governance_drift"):
        decisions.append({"decision": "review-governance-drift", "reason": "Governance drift exists and should be resolved before governed apply."})
    if report_data.get("governance_preview", {}).get("applyable_count", 0) and not report_data.get("governance_approval"):
        decisions.append({"decision": "approve-governance", "reason": "Governed controls are ready and not yet approved."})
    if report_data.get("campaign_summary", {}).get("action_count", 0) and not report_data.get("writeback_results", {}).get("mode") == "apply":
        decisions.append({"decision": "preview-campaign", "reason": "A campaign queue exists and should be reviewed before any writeback."})
    if not decisions:
        decisions.append({"decision": "inspect-top-targets", "reason": "Material changes exist but no explicit campaign or governance action is pending."})
    return decisions


def _change(
    change_type: str,
    repo_name: str,
    severity: float,
    title: str,
    summary: str,
    recommended_next_step: str,
    *,
    details: dict,
) -> dict:
    return {
        "change_key": _fingerprint([change_type, repo_name, title]),
        "change_type": change_type,
        "repo_name": repo_name,
        "severity": round(severity, 3),
        "title": title,
        "summary": summary,
        "recommended_next_step": recommended_next_step,
        "details": details,
    }


def _severity_value(severity: str) -> float:
    return {"low": 0.35, "medium": 0.6, "high": 0.85}.get(severity, 0.6)


def _fingerprint(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
