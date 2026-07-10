"""Optional LLM initiative-suggestion and dismissal commands.

Local imports inside each flow preserve mode-specific dependency loading and
the established error behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.cli_output import print_info, print_warning
from src.portfolio_truth_types import truth_latest_path


def _run_suggest_initiatives_mode(args) -> None:
    """LLM-rank repos closest to qualifying for their next maturity tier (Arc G S8.4)."""
    from pathlib import Path as _Path

    from src.llm_cost import BudgetExceededError
    from src.maturity_tiers import tier_name
    from src.suggest_initiatives import generate_suggestions

    truth_path = truth_latest_path(_Path(args.output_dir))
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. "
            "Run `audit triage USERNAME --portfolio-truth` first."
        )
        return

    truth = json.loads(truth_path.read_text())
    projects = truth.get("projects", [])

    # 0 is the const sentinel meaning "use per-repo next tier"
    target = args.suggest_initiatives if args.suggest_initiatives else None
    budget = args.llm_budget if args.llm_budget is not None else 0.10

    try:
        suggestions, cost = generate_suggestions(projects, target_tier=target, budget_usd=budget)
    except BudgetExceededError as exc:
        print(f"\nERROR: LLM budget exceeded: {exc}", file=sys.stderr)
        return

    if not suggestions:
        print_info("No suggestions: no repos are close to qualifying for the next tier.")
        return

    print_info(f"Suggested Initiatives ({len(suggestions)} candidates, ${cost:.4f} spent)")
    print()
    for s in suggestions:
        print(
            f"  {s.repo_name:<30} {tier_name(s.current_tier)} → {tier_name(s.target_tier):<10} "
            f"[{s.estimated_effort}]"
        )
        print(f"    Missing: {', '.join(s.missing_requirements)}")
        print(f"    Rationale: {s.rationale}")
        print()

def _run_accept_suggestion_mode(args) -> None:
    """Accept a suggestion: convert it into a tier-upgrade initiative (Arc G S9.1)."""
    import sys

    from src.suggest_initiatives import accept_suggestion

    output_dir = Path(args.output_dir)
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first."
        )
        return

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print_warning(f"Failed to read portfolio-truth: {exc}")
        return

    projects = truth.get("projects", [])

    try:
        initiative = accept_suggestion(
            repo_name=args.accept_suggestion,
            projects=projects,
            output_dir=output_dir,
            deadline=getattr(args, "deadline", None),
            target_tier=getattr(args, "target_tier", None),
        )
    except ValueError as exc:
        print_warning(str(exc))
        sys.exit(2)

    print_info(
        f"Initiative accepted: {initiative.repo_name} → "
        f"Tier {initiative.target_tier} by {initiative.deadline}"
    )

def _run_dismiss_suggestion_mode(args) -> None:
    """Dismiss a repo from future LLM-suggested initiatives (Arc G S11.4)."""
    import sys
    from pathlib import Path

    from src.suggest_initiatives import dismiss_suggestion_record, dismissed_path

    output_dir = Path(args.output_dir)
    try:
        entry = dismiss_suggestion_record(
            dismissed_path(output_dir),
            repo_name=args.dismiss_suggestion,
            reason=getattr(args, "reason", "") or "",
            expires_days=getattr(args, "dismiss_expires_days", None),
        )
    except ValueError as exc:
        print_warning(str(exc))
        sys.exit(2)
    expiry_note = f" (expires {entry.expires_at})" if entry.expires_at else ""
    print_info(
        f"✗ Dismissed: {entry.repo_name}"
        + (f" — {entry.reason}" if entry.reason else "")
        + expiry_note
    )

def _run_undo_dismiss_mode(args) -> None:
    """Restore a dismissed repo to the suggestion pool (Arc G S11.4)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, undo_dismiss

    output_dir = Path(args.output_dir)
    removed = undo_dismiss(dismissed_path(output_dir), args.undo_dismiss)
    if removed:
        print_info(f"✓ Restored: {args.undo_dismiss}")
    else:
        print_warning(f"{args.undo_dismiss} was not dismissed; nothing to undo")

def _run_list_dismissed_mode(args) -> None:
    """List all currently dismissed suggestion repos (Arc G S11.4)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, load_dismissed

    output_dir = Path(args.output_dir)
    items = load_dismissed(dismissed_path(output_dir))
    if not items:
        print_info("No dismissed suggestions.")
        return
    print_info(f"Dismissed Suggestions ({len(items)})")
    for d in items:
        reason = f" — {d.reason}" if d.reason else ""
        print(f"  {d.repo_name:<30} dismissed {d.dismissed_at[:10]} by {d.dismissed_by}{reason}")

def _run_expire_dismissals_mode(args) -> None:
    """Remove dismissals whose expiry date has passed (Arc G S12.1)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, expire_dismissals

    output_dir = Path(args.output_dir)
    expired = expire_dismissals(dismissed_path(output_dir))
    if not expired:
        print_info("No dismissals to expire.")
        return
    print_info(f"Expired {len(expired)} dismissal(s):")
    for d in expired:
        print(f"  {d.repo_name:<30} (was set to expire {d.expires_at})")

def _run_dismissal_history_mode(args) -> None:
    """Show audit trail of dismissal events (Arc G S12.1)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, load_dismissal_events

    output_dir = Path(args.output_dir)
    events = load_dismissal_events(dismissed_path(output_dir))
    if not events:
        print_info("No dismissal history.")
        return
    print_info(f"Dismissal History ({len(events)} event(s))")
    for e in events:
        reason = f" — {e.reason}" if e.reason else ""
        print(f"  {e.occurred_at[:19]} {e.event_type:<10} {e.repo_name:<30} by {e.actor}{reason}")
