"""Deterministic initiative-management commands."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from src.cli_output import print_info, print_warning
from src.portfolio_truth_types import TRUTH_LATEST_FILENAME, truth_latest_path


def run_set_initiative_mode(args) -> None:
    """Validate and persist a tier-upgrade initiative for a repo."""
    from src.initiatives import Initiative, initiatives_path, operator_identity, upsert_initiative
    from src.maturity_tiers import TIER_DEFINITIONS, compute_tier

    repo_name: str = args.set_initiative
    target_tier: int | None = getattr(args, "target_tier", None)
    deadline_str: str | None = getattr(args, "deadline", None)
    output_dir = Path(args.output_dir)
    if target_tier is None:
        print_warning("--target-tier is required with --set-initiative (choices: 2, 3, 4)")
        sys.exit(2)
    if deadline_str is None:
        print_warning("--deadline YYYY-MM-DD is required with --set-initiative")
        sys.exit(2)
    try:
        deadline_date = date.fromisoformat(deadline_str)
    except ValueError:
        print_warning(f"--deadline must be YYYY-MM-DD, got: {deadline_str!r}")
        sys.exit(2)
    if deadline_date < date.today():
        print_warning(f"--deadline {deadline_str} is in the past. Provide a future date.")
        sys.exit(2)
    pt_candidates = sorted(output_dir.glob(TRUTH_LATEST_FILENAME))
    if not pt_candidates:
        pt_candidates = sorted(output_dir.glob("portfolio-truth-*.json"))
    if not pt_candidates:
        print_warning(f"Portfolio truth not found in {output_dir}. Run `audit report --portfolio-truth` first.")
        sys.exit(2)
    pt_path = truth_latest_path(output_dir)
    if not pt_path.exists():
        pt_path = pt_candidates[-1]
    try:
        pt_data = json.loads(pt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print_warning(f"Could not read portfolio truth: {exc}")
        sys.exit(2)
    repo_dict = next(
        (project for project in pt_data.get("projects", [])
         if project.get("identity", {}).get("display_name", "").lower() == repo_name.lower()),
        None,
    )
    if repo_dict is None:
        print_warning(f"Repo {repo_name!r} not found in portfolio truth. Run `audit report --portfolio-truth` first.")
        sys.exit(2)
    current_tier = compute_tier(repo_dict)
    if target_tier <= current_tier:
        target_name = TIER_DEFINITIONS[target_tier].name
        current_name = TIER_DEFINITIONS[current_tier].name if current_tier > 0 else "Untracked"
        print_warning(f"Target tier {target_tier} ({target_name}) is not greater than current tier {current_tier} ({current_name}) for {repo_name!r}.")
        sys.exit(2)
    initiative = Initiative(repo_name=repo_name, target_tier=target_tier, deadline=deadline_str,
                            set_at=datetime.now(tz=timezone.utc).isoformat(), set_by=operator_identity())
    upsert_initiative(initiatives_path(output_dir), initiative)
    print_info(f"Initiative set: {repo_name} → Tier {target_tier} ({TIER_DEFINITIONS[target_tier].name}) by {deadline_str}")


def run_list_initiatives_mode(args) -> None:
    """Print a status table for all initiatives."""
    from src.initiatives import derive_status, initiatives_path, load_initiatives
    from src.maturity_tiers import TIER_DEFINITIONS, compute_tier, tier_name

    output_dir = Path(args.output_dir)
    initiatives = load_initiatives(initiatives_path(output_dir))
    projects_by_name: dict[str, dict] = {}
    pt_path = truth_latest_path(output_dir)
    if pt_path.exists():
        try:
            for project in json.loads(pt_path.read_text(encoding="utf-8")).get("projects", []):
                name = project.get("identity", {}).get("display_name", "")
                if name:
                    projects_by_name[name.lower()] = project
        except (OSError, ValueError) as exc:
            print_warning(f"Unable to read/parse {pt_path}: {exc}")
    open_initiatives = [item for item in initiatives if item.closed_at is None]
    closed_initiatives = [item for item in initiatives if item.closed_at is not None]
    print_info("Initiative Tracker")
    print_info("══════════════════")
    if not open_initiatives:
        print_info("No open initiatives.")
    else:
        header = f"{'REPO':<30} {'TARGET':<12} {'CURRENT':<12} {'DEADLINE':<12} {'STATUS'}"
        print_info(header)
        print_info("-" * len(header))
        for initiative in open_initiatives:
            repo_dict = projects_by_name.get(initiative.repo_name.lower(), {})
            current = compute_tier(repo_dict) if repo_dict else 0
            status = derive_status(initiative, repo_dict)
            target_label = f"{TIER_DEFINITIONS[initiative.target_tier].name}({initiative.target_tier})" if initiative.target_tier in TIER_DEFINITIONS else str(initiative.target_tier)
            current_label = f"{tier_name(current)}({current})" if current > 0 else "Untracked"
            status_detail = status
            if status == "at-risk":
                try:
                    status_detail = f"at-risk (deadline ≤ {(date.fromisoformat(initiative.deadline) - date.today()).days}d)"
                except ValueError:
                    print_warning(
                        f"Invalid initiative deadline for {initiative.repo_name!r}: {initiative.deadline!r}"
                    )
            elif status == "on-track":
                status_detail = "on-track"
            print_info(f"{initiative.repo_name:<30} {target_label:<12} {current_label:<12} {initiative.deadline:<12} {status_detail}")
    if closed_initiatives:
        print_info(f"\nClosed: {len(closed_initiatives)}")


def run_close_initiative_mode(args) -> None:
    """Close the open initiative for a repo."""
    from src.initiatives import close_initiative, initiatives_path

    repo_name: str = args.close_initiative
    closed = close_initiative(initiatives_path(Path(args.output_dir)), repo_name, reason="met")
    if closed is None:
        print_warning(f"No open initiative found for {repo_name!r}.")
        sys.exit(2)
    print_info(f"Initiative closed: {repo_name} → Tier {closed.target_tier} (reason: {closed.closed_reason}, closed_at: {closed.closed_at})")
