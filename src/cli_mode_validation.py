from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliModeState:
    portfolio_truth_mode: bool
    portfolio_context_recovery_mode: bool
    standalone_portfolio_modes: bool


def validate_cli_mode_args(args, error) -> CliModeState:
    if args.registry and args.notion_registry:
        error("--registry and --notion-registry cannot be used together")
    if args.sync_registry:
        error(
            "--sync-registry has been retired. Use --portfolio-truth to regenerate project-registry.md from the canonical truth snapshot."
        )

    portfolio_truth_mode = bool(getattr(args, "portfolio_truth", False))
    portfolio_context_recovery_mode = bool(getattr(args, "portfolio_context_recovery", False))
    apply_context_recovery = bool(getattr(args, "apply_context_recovery", False))
    context_recovery_limit = getattr(args, "context_recovery_limit", None)

    if portfolio_truth_mode and portfolio_context_recovery_mode:
        error(
            "--portfolio-truth and --portfolio-context-recovery are separate standalone modes; run one at a time."
        )

    standalone_portfolio_modes = portfolio_truth_mode or portfolio_context_recovery_mode
    if apply_context_recovery and not portfolio_context_recovery_mode:
        error("--apply-context-recovery requires --portfolio-context-recovery.")
    if context_recovery_limit is not None and context_recovery_limit <= 0:
        error("--context-recovery-limit must be a positive integer.")
    if standalone_portfolio_modes and (
        args.control_center
        or args.approval_center
        or args.campaign
        or args.writeback_apply
        or args.writeback_target
        or args.github_projects
        or args.doctor
    ):
        error(
            "Portfolio truth and context recovery are standalone workspace modes and cannot be combined with control-center, doctor, or Action Sync flags."
        )

    if args.upload_badges:
        args.badges = True
    if args.notion_sync:
        args.notion = True
    if args.writeback_apply and not args.writeback_target:
        error("--writeback-apply requires --writeback-target")
    if args.writeback_target and not args.campaign:
        error(
            "--writeback-target belongs to Action Sync mode. Add --campaign <name> before choosing a writeback target."
        )
    if args.github_projects and not args.campaign:
        error(
            "--github-projects belongs to Action Sync mode. Add --campaign <name> before enabling GitHub Projects mirroring."
        )
    if args.github_projects and args.writeback_target not in {"github", "all"}:
        error("--github-projects only runs inside Action Sync with --writeback-target github or all.")
    if args.approve_packet and not args.campaign:
        error("--approve-packet requires --campaign")
    if args.review_packet and not args.campaign:
        error("--review-packet requires --campaign")
    if args.approve_packet and args.writeback_apply:
        error(
            "--approve-packet captures local approval only. Remove --writeback-apply and run apply separately."
        )
    if args.review_packet and args.writeback_apply:
        error(
            "--review-packet captures a local follow-up review only. Remove --writeback-apply and run apply separately."
        )
    if args.approve_governance and args.approval_center:
        error(
            "--approve-governance captures a local approval. Remove --approval-center for read-only mode."
        )
    if args.review_governance and args.approval_center:
        error(
            "--review-governance captures a local follow-up review. Remove --approval-center for read-only mode."
        )
    if args.approval_center and args.control_center:
        error("--approval-center and --control-center are separate read-only views; run one at a time.")
    if args.approve_governance and args.review_governance:
        error("--approve-governance and --review-governance are separate local actions; run one at a time.")
    if args.approve_packet and args.review_packet:
        error("--approve-packet and --review-packet are separate local actions; run one at a time.")
    if args.approval_center and (
        args.campaign
        or args.writeback_target
        or args.writeback_apply
        or args.github_projects
        or args.approve_governance
        or args.approve_packet
        or args.review_governance
        or args.review_packet
    ):
        error(
            "--approval-center is the read-only approval view. Remove campaign, writeback, or approval-capture flags."
        )
    if args.control_center and (
        args.campaign or args.writeback_target or args.writeback_apply or args.github_projects
    ):
        error(
            "--control-center is the read-only Weekly Review entrypoint. Remove campaign/writeback flags or run a normal audit for Action Sync."
        )
    if getattr(args, "auto_apply_approved", False) and (
        args.writeback_apply or args.approve_packet or args.campaign
    ):
        error(
            "--auto-apply-approved runs its own bounded apply loop. Remove --writeback-apply, --approve-packet, or --campaign."
        )

    return CliModeState(
        portfolio_truth_mode=portfolio_truth_mode,
        portfolio_context_recovery_mode=portfolio_context_recovery_mode,
        standalone_portfolio_modes=standalone_portfolio_modes,
    )
