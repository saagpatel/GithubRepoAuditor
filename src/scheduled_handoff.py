from __future__ import annotations

import argparse
import json
from pathlib import Path


ISSUE_LABEL = "scheduled-audit-handoff"


def _latest_artifact(output_dir: Path, pattern: str) -> Path | None:
    matches = sorted(output_dir.glob(pattern))
    return matches[-1] if matches else None


def _load_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text())


def _queue_counts(summary: dict) -> str:
    counts = summary.get("counts", {})
    return (
        f"{counts.get('blocked', 0)} blocked, "
        f"{counts.get('urgent', 0)} urgent, "
        f"{counts.get('ready', 0)} ready, "
        f"{counts.get('deferred', 0)} deferred"
    )


def _has_regressions(diff_data: dict) -> bool:
    regressions = diff_data.get("score_regressions", []) or []
    tier_changes = diff_data.get("tier_changes", []) or []
    downgrades = [
        item
        for item in tier_changes
        if item.get("old_tier") in {"shipped", "functional"}
        and item.get("new_tier") in {"wip", "skeleton", "abandoned"}
    ]
    return bool(regressions or downgrades)


def _issue_candidate(
    summary: dict,
    diff_data: dict,
    username: str,
    body_path: Path,
    *,
    issue_state: str = "absent",
    issue_number: str = "",
    issue_url: str = "",
) -> dict:
    urgency = summary.get("urgency", "quiet")
    regressions_detected = _has_regressions(diff_data)
    noisy = urgency in {"blocked", "urgent"} or regressions_detected
    reason = summary.get("escalation_reason", "quiet")
    if regressions_detected:
        reason = "regressions-detected"
    action = "quiet"
    reopen_existing = False
    close_reason = ""
    if noisy:
        if issue_state == "open":
            action = "update"
        elif issue_state == "closed":
            action = "update"
            reopen_existing = True
        else:
            action = "open"
    elif issue_state == "open":
        action = "close"
        close_reason = "quiet-recovery"
    return {
        "should_open": noisy,
        "reason": reason,
        "severity": urgency,
        "action": action,
        "reopen_existing": reopen_existing,
        "close_reason": close_reason,
        "label": ISSUE_LABEL,
        "title": f"Scheduled Audit Handoff: {username}",
        "marker": f"scheduled-audit-handoff:{username}",
        "issue_state": issue_state,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "body_path": str(body_path),
    }


def render_scheduled_handoff_markdown(payload: dict) -> str:
    summary = payload.get("operator_summary", {})
    queue = payload.get("operator_queue", []) or []
    recent_changes = payload.get("operator_recent_changes", []) or []
    issue_candidate = payload.get("issue_candidate", {})
    primary_target = summary.get("primary_target") or {}
    primary_target_label = (
        f"{primary_target.get('repo')}: {primary_target.get('title')}"
        if primary_target.get("repo")
        else primary_target.get("title", "")
    )
    resolved_count = summary.get("resolved_attention_count", 0)
    persisting_count = summary.get("persisting_attention_count", 0)
    longest_persisting = summary.get("longest_persisting_item") or {}
    longest_label = (
        f"{longest_persisting.get('repo')}: {longest_persisting.get('title')}"
        if longest_persisting.get("repo")
        else longest_persisting.get("title", "")
    )
    lines = [
        f"# Scheduled Audit Handoff: {payload.get('username', 'unknown')}",
        "",
        f"<!-- {issue_candidate.get('marker', '')} -->",
        "",
        f"- Generated: `{payload.get('generated_at', '')}`",
        f"- Headline: {summary.get('headline', 'No operator triage items are currently surfaced.')}",
        f"- What changed: {summary.get('what_changed', 'No operator change summary is recorded.')}",
        f"- Why it matters: {summary.get('why_it_matters', 'No additional operator impact is recorded.')}",
        f"- What to do next: {summary.get('what_to_do_next', 'Continue the normal operator loop.')}",
        f"- Trend: `{summary.get('trend_status', 'stable')}` — {summary.get('trend_summary', 'No trend summary is recorded yet.')}",
        f"- Aging status: `{summary.get('aging_status', 'fresh')}`",
        f"- Attention counts: new={summary.get('new_attention_count', 0)}, resolved={resolved_count}, persisting={persisting_count}, reopened={summary.get('reopened_attention_count', 0)}",
        f"- Primary target: {primary_target_label or 'No active target'}",
        f"- Accountability: {summary.get('accountability_summary', 'No accountability summary is recorded yet.')}",
        f"- Next recommended run: `{summary.get('next_recommended_run_mode', 'n/a')}`",
        f"- Watch strategy: `{summary.get('watch_strategy', 'manual')}`",
        f"- Watch decision: {summary.get('watch_decision_summary', 'No watch guidance is recorded.')}",
        f"- Queue counts: {_queue_counts(summary)}",
        f"- Issue automation: `{issue_candidate.get('action', 'quiet')}` ({issue_candidate.get('reason', 'quiet')})",
        *( [f"- Existing issue: #{issue_candidate.get('issue_number')}"] if issue_candidate.get("issue_number") else [] ),
        "",
    ]
    lines.append("## What Got Better")
    lines.append("")
    if resolved_count:
        lines.append(f"- {resolved_count} attention item(s) cleared since the last run.")
    elif summary.get("trend_status") == "quiet":
        lines.append(
            f"- The queue is quiet and has held for {summary.get('quiet_streak_runs', 0)} consecutive run(s)."
        )
    else:
        lines.append("- No meaningful recovery signal is recorded in this handoff.")
    lines.append("")
    lines.append("## What Needs Attention Now")
    lines.append("")
    if primary_target_label:
        lines.append(f"- Primary target: {primary_target_label}")
        if primary_target.get("recommended_action"):
            lines.append(f"- Next step: {primary_target.get('recommended_action')}")
    else:
        lines.append("- No blocked or urgent target is currently active.")
    if queue:
        for item in queue[:3]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            lines.append(
                f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')} -> {item.get('recommended_action', 'Review the latest state.')}"
            )
    lines.append("")
    lines.append("## What Is Still Stuck")
    lines.append("")
    if persisting_count:
        lines.append(f"- {persisting_count} attention item(s) are still open from the previous run.")
    if summary.get("follow_through_summary"):
        lines.append(f"- {summary.get('follow_through_summary')}")
    if not persisting_count and not summary.get("follow_through_summary"):
        lines.append("- Nothing currently looks sticky across the recent run window.")
    lines.append("")
    lines.append("## Why This Is Still Open")
    lines.append("")
    if summary.get("primary_target_reason"):
        lines.append(f"- {summary.get('primary_target_reason')}")
    else:
        lines.append("- No active top-target rationale is recorded.")
    lines.append("")
    lines.append("## What Counts As Done")
    lines.append("")
    if summary.get("primary_target_done_criteria"):
        lines.append(f"- {summary.get('primary_target_done_criteria')}")
    if summary.get("closure_guidance"):
        lines.append(f"- {summary.get('closure_guidance')}")
    if not summary.get("primary_target_done_criteria") and not summary.get("closure_guidance"):
        lines.append("- No active done-state guidance is recorded.")
    lines.append("")
    lines.append("## Aging Pressure")
    lines.append("")
    lines.append(
        f"- Chronic items: {summary.get('chronic_item_count', 0)} | Newly stale items: {summary.get('newly_stale_count', 0)}"
    )
    lines.append(
        f"- Attention age bands: {summary.get('attention_age_bands', {}) or {'0-1 days': 0, '2-7 days': 0, '8-21 days': 0, '22+ days': 0}}"
    )
    if longest_label:
        lines.append(
            f"- Longest persisting item: {longest_label} ({longest_persisting.get('age_days', 0)} day(s), {longest_persisting.get('aging_status', 'fresh')})"
        )
    else:
        lines.append("- No persisting item is currently recorded.")
    lines.append("")
    if queue:
        lines.append("## Top Queue Items")
        lines.append("")
        for item in queue[:5]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            lines.append(f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')}")
            lines.append(f"  - Why: {item.get('summary', 'No summary available.')}")
            lines.append(f"  - Next: {item.get('recommended_action', 'Review the latest state.')}")
        lines.append("")
    if recent_changes:
        lines.append("## Recent Changes")
        lines.append("")
        for change in recent_changes[:5]:
            subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
            lines.append(f"- {change.get('generated_at', '')[:10]} {subject}: {change.get('summary', change.get('kind', 'change'))}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_scheduled_handoff(
    output_dir: Path,
    *,
    issue_state: str = "absent",
    issue_number: str = "",
    issue_url: str = "",
) -> dict:
    control_center_path = _latest_artifact(output_dir, "operator-control-center-*.json")
    control_center = _load_json(control_center_path)
    if not control_center:
        raise FileNotFoundError("No operator control-center artifact was found in the output directory.")

    diff_data = _load_json(_latest_artifact(output_dir, "audit-diff-*.json"))
    summary = control_center.get("operator_summary", {})
    username = control_center.get("username", "unknown")
    generated_at = control_center.get("generated_at", "")
    stamp = (generated_at or "unknown").split("T", 1)[0]
    markdown_path = output_dir / f"scheduled-handoff-{username}-{stamp}.md"
    json_path = output_dir / f"scheduled-handoff-{username}-{stamp}.json"
    issue_candidate = _issue_candidate(
        summary,
        diff_data,
        username,
        markdown_path,
        issue_state=issue_state,
        issue_number=issue_number,
        issue_url=issue_url,
    )
    payload = {
        "status": "ok",
        "username": username,
        "generated_at": generated_at,
        "control_center_reference": str(control_center_path),
        "report_reference": control_center.get("report_reference", ""),
        "operator_summary": summary,
        "operator_queue": control_center.get("operator_queue", []),
        "operator_recent_changes": control_center.get("operator_recent_changes", []),
        "issue_candidate": issue_candidate,
    }
    markdown_path.write_text(render_scheduled_handoff_markdown(payload))
    payload["markdown_path"] = str(markdown_path)
    json_path.write_text(json.dumps(payload, indent=2))
    payload["json_path"] = str(json_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scheduled-handoff",
        description="Build scheduled operator handoff artifacts from the latest control-center output.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory that contains the latest audit/control-center artifacts.",
    )
    parser.add_argument(
        "--issue-state",
        choices=["absent", "open", "closed"],
        default="absent",
        help="Current state of the canonical scheduled handoff issue, if one already exists.",
    )
    parser.add_argument(
        "--issue-number",
        default="",
        help="Existing canonical issue number when one is already present.",
    )
    parser.add_argument(
        "--issue-url",
        default="",
        help="Existing canonical issue URL when one is already present.",
    )
    args = parser.parse_args()
    payload = build_scheduled_handoff(
        Path(args.output_dir),
        issue_state=args.issue_state,
        issue_number=args.issue_number,
        issue_url=args.issue_url,
    )
    issue = payload.get("issue_candidate", {})
    print(f"Scheduled handoff: {payload.get('markdown_path', '')}")
    print(f"Issue automation: {issue.get('action', 'quiet')} ({issue.get('reason', 'quiet')})")


if __name__ == "__main__":
    main()
