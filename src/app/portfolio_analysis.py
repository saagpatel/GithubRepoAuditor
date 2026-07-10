"""Standalone portfolio-analysis reporting flows."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.cli_output import print_info, print_warning
from src.portfolio_truth_types import truth_latest_path


def _run_tier_gaps_export_mode(args) -> None:
    """Dump per-repo tier-gap data as JSON or markdown (Arc G S12.4)."""
    from datetime import datetime, timezone
    from pathlib import Path

    from src.maturity_tiers import compute_tier, tier_gap, tier_name

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
        sys.exit(2)

    projects = truth.get("projects", [])
    target_override = getattr(args, "tier_gaps_target", None)
    if target_override is not None and target_override not in (2, 3, 4):
        print_warning(f"Invalid --tier-gaps-target {target_override}; must be 2, 3, or 4.")
        sys.exit(2)

    gaps: list[dict] = []
    for project in projects:
        name = (project.get("identity") or {}).get("display_name") or ""
        if not name:
            continue
        current = compute_tier(project)
        if current == 0 or current == 4:
            continue  # no-git or already-Platinum: no next tier
        target = target_override if target_override is not None else (current + 1)
        if target <= current:
            continue  # operator's override is below or equal to current
        gap = tier_gap(project, target)
        gaps.append(
            {
                "repo_name": name,
                "current_tier": current,
                "current_tier_name": tier_name(current),
                "target_tier": target,
                "target_tier_name": tier_name(target),
                "missing_requirements": list(gap.missing_requirements),
                "requirement_sources": list(gap.requirement_sources),
            }
        )

    fmt = getattr(args, "format", "json")
    if fmt == "markdown":
        _print_tier_gaps_markdown(gaps)
    else:
        envelope = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "gaps": gaps,
        }
        print(json.dumps(envelope, indent=2))

def _print_tier_gaps_markdown(gaps: list[dict]) -> None:
    """Human-readable tier-gap table (Arc G S12.4)."""
    if not gaps:
        print_info("No tier gaps to report (all repos either at Platinum or no git).")
        return
    print_info(f"Tier Gaps ({len(gaps)} repo(s))")
    print()
    print("| REPO | CURRENT → TARGET | MISSING | SOURCE |")
    print("|------|------------------|---------|--------|")
    for g in gaps:
        missing = ", ".join(g["missing_requirements"]) if g["missing_requirements"] else "—"
        sources = ", ".join(g["requirement_sources"]) if g["requirement_sources"] else "—"
        print(
            f"| {g['repo_name']} | {g['current_tier_name']} → {g['target_tier_name']} | {missing} | {sources} |"
        )

def _run_tier_recalibration_report_mode(args) -> None:
    """Generate tier distribution report and flag bunching (Arc H A4)."""
    from datetime import date, datetime, timezone

    from src.tier_recalibration import tier_distribution_report

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
        sys.exit(2)

    projects = truth.get("projects", [])
    report = tier_distribution_report(projects)
    out_path = output_dir / f"tier-recalibration-{date.today()}.json"
    envelope = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }
    out_path.write_text(json.dumps(envelope, indent=2))
    print_info(f"Tier recalibration report written to {out_path}")
    if report["bunching_detected"]:
        print_warning(
            "Bunching detected: at least one tier holds >60% of repos. "
            "Consider adjusting tier thresholds."
        )
    else:
        print_info("No bunching detected — tier distribution looks healthy.")

def _run_context_triage_mode(args) -> None:
    """Run context quality triage across the portfolio (Arc H B1)."""
    from datetime import date, datetime, timezone

    from src.catalog_validator import validate_catalog
    from src.portfolio_context_triage import run_triage

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
        sys.exit(2)

    projects = truth.get("projects", [])
    catalog_path = (
        Path(args.catalog)
        if getattr(args, "catalog", None)
        else Path("config/portfolio-catalog.yaml")
    )
    repo_keys: list[str] = []
    for project in projects:
        identity = project.get("identity") or {}
        project_key = identity.get("project_key") or ""
        name = identity.get("display_name") or project.get("name", "")
        repo_keys.extend(key for key in (project_key, name) if key)
    catalog_scores = (
        validate_catalog(catalog_path, sorted(set(repo_keys))) if catalog_path.exists() else {}
    )

    enriched: list[dict] = []
    for project in projects:
        identity = project.get("identity") or {}
        name = identity.get("display_name") or project.get("name", "")
        project_key = identity.get("project_key") or name
        row = dict(project)
        row["catalog_completeness"] = max(
            catalog_scores.get(project_key, 0.0),
            catalog_scores.get(name, 0.0),
        )
        enriched.append(row)

    entries = run_triage(enriched)
    out = [e.to_dict() for e in entries]
    out_path = output_dir / f"context-triage-{date.today()}.json"
    envelope = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_flagged": len(out),
        "triage": out,
    }
    out_path.write_text(json.dumps(envelope, indent=2))
    print_info(f"Context triage written to {out_path} — {len(out)} repos flagged")
