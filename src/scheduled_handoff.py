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
        f"- Next recommended run: `{summary.get('next_recommended_run_mode', 'n/a')}`",
        f"- Watch strategy: `{summary.get('watch_strategy', 'manual')}`",
        f"- Watch decision: {summary.get('watch_decision_summary', 'No watch guidance is recorded.')}",
        f"- Queue counts: {_queue_counts(summary)}",
        f"- Issue automation: `{issue_candidate.get('action', 'quiet')}` ({issue_candidate.get('reason', 'quiet')})",
        *( [f"- Existing issue: #{issue_candidate.get('issue_number')}"] if issue_candidate.get("issue_number") else [] ),
        "",
    ]
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
