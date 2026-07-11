"""Bounded-automation proposal queue flow.

Mode-specific imports stay local to preserve the command's existing dependency
loading and its approval/execution safety boundaries.
"""

from __future__ import annotations

from pathlib import Path

from src.cli_output import print_info, print_warning
from src.control_center_report_state import refresh_latest_report_state

DEFAULT_PORTFOLIO_WORKSPACE = Path.home() / "Projects"


def run_automation_proposals_mode(args) -> None:
    """Triage the durable bounded-automation proposal queue (Arc D phase 3b)."""
    from datetime import datetime, timezone

    from src.automation_proposals import (
        ACTION_CATALOG_SEED,
        ACTION_CONTEXT_PR,
        ProposalApprovalError,
        ProposalNotFoundError,
        approve_proposal,
        build_automation_proposals,
        load_proposals,
        reject_proposal,
        save_proposals,
    )
    from src.portfolio_automation import select_automation_candidates

    output_dir = Path(args.output_dir)
    proposals_path = output_dir / "pending-proposals.json"
    now = datetime.now(timezone.utc).isoformat()

    if getattr(args, "approve_proposal", None) or getattr(args, "reject_proposal", None):
        try:
            proposals = load_proposals(proposals_path)
            if getattr(args, "approve_proposal", None):
                updated = approve_proposal(
                    proposals,
                    args.approve_proposal,
                    approved_by="local-operator",
                    approved_at=now,
                )
                label = f"Approved proposal {args.approve_proposal!r}."
            else:
                updated = reject_proposal(proposals, args.reject_proposal, rejected_at=now)
                label = f"Rejected proposal {args.reject_proposal!r}."
        except (ProposalNotFoundError, ProposalApprovalError, ValueError) as exc:
            print_warning(str(exc))
            return
        save_proposals(proposals_path, updated)
        print_info(label)
        return

    if getattr(args, "list_proposals", False):
        proposals = load_proposals(proposals_path)
        if not proposals:
            print_info("No bounded-automation proposals in the queue.")
            return
        print_info(f"Bounded-automation proposal queue ({len(proposals)} total):")
        for proposal in proposals:
            print_info(f"  {proposal.status}: {proposal.proposal_id} — {proposal.description}")
        return

    if getattr(args, "propose_automation", False):
        from src.weekly_command_center import load_latest_portfolio_truth

        _truth_path, truth = load_latest_portfolio_truth(output_dir)
        if not truth:
            print_warning("No portfolio truth snapshot found. Run --portfolio-truth first.")
            return
        try:
            _report_path, _diff, report = refresh_latest_report_state(output_dir, args)
            decision_quality_status = (
                (report.operator_summary or {})
                .get("decision_quality_v1", {})
                .get("decision_quality_status", "")
            )
        except FileNotFoundError:
            decision_quality_status = ""
        candidates = select_automation_candidates(
            truth, decision_quality_status=decision_quality_status
        )
        existing = load_proposals(proposals_path)
        merged = build_automation_proposals(
            candidates, action_type=ACTION_CONTEXT_PR, created_at=now, existing=existing
        )
        merged = build_automation_proposals(
            candidates, action_type=ACTION_CATALOG_SEED, created_at=now, existing=merged
        )
        save_proposals(proposals_path, merged)
        print_info(
            f"Proposal queue: {len(merged)} total ({len(merged) - len(existing)} new) "
            f"from {len(candidates)} eligible candidate(s)."
        )
        return

    if getattr(args, "execute_proposals", False):
        from src.automation_proposals import executable_proposals
        from src.automation_workflow import execute_approved_proposals
        from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot

        if not executable_proposals(load_proposals(proposals_path)):
            print_info("No approved bounded-automation proposals to execute.")
            return

        workspace_root = Path(getattr(args, "workspace_root", None) or DEFAULT_PORTFOLIO_WORKSPACE)
        catalog_path = (
            Path(args.catalog)
            if getattr(args, "catalog", None)
            else Path("config/portfolio-catalog.yaml")
        )
        registry_output = (
            Path(args.registry_output)
            if getattr(args, "registry_output", None)
            else workspace_root / "project-registry.md"
        )
        legacy_registry_path = (
            Path(args.registry) if getattr(args, "registry", None) else registry_output
        )
        build_result = build_portfolio_truth_snapshot(
            workspace_root=workspace_root,
            catalog_path=catalog_path if catalog_path.exists() else None,
            legacy_registry_path=legacy_registry_path,
            include_notion=True,
        )
        apply = bool(getattr(args, "apply", False))
        results = execute_approved_proposals(
            proposals_path=proposals_path,
            snapshot=build_result.snapshot,
            workspace_root=workspace_root,
            catalog_path=catalog_path,
            executed_at=now,
            dry_run=not apply,
        )
        if not results:
            print_info("No approved bounded-automation proposals to execute.")
            return
        for result in results:
            print_info(f"  {result.outcome}: {result.proposal_id} — {result.detail}")
        mode = "apply" if apply else "dry-run"
        print_info(f"Execute proposals ({mode}): {len(results)} approved proposal(s) processed.")
