from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.cache import ResponseCache
from src.cli_output import print_info
from src.portfolio_context_recovery import (
    apply_context_recovery_plan,
    build_context_recovery_plan,
    write_context_recovery_plan_artifacts,
)
from src.portfolio_truth_publish import PortfolioTruthPublishError, publish_portfolio_truth
from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from src.portfolio_truth_status import (
    load_live_repo_status_by_name,
    load_release_count_by_name,
    load_repo_status_from_audit_by_name,
    load_security_coverage_by_full_name,
)
from src.producer_preflight import load_producer_evidence


def run_portfolio_truth_mode(args: Any) -> None:
    output_dir = Path(args.output_dir)
    workspace_root = Path(args.workspace_root)
    registry_output = (
        Path(args.registry_output)
        if args.registry_output
        else workspace_root / "project-registry.md"
    )
    portfolio_report_output = (
        Path(args.portfolio_report_output)
        if args.portfolio_report_output
        else workspace_root / "PORTFOLIO-AUDIT-REPORT.md"
    )
    legacy_registry_path = Path(args.registry) if args.registry else registry_output
    producer_evidence_path = os.environ.get("GHRA_PRODUCER_EVIDENCE")
    producer_evidence = (
        load_producer_evidence(Path(producer_evidence_path))
        if producer_evidence_path
        else None
    )
    producer_repo_root_value = os.environ.get("GHRA_PRODUCER_REPO_ROOT")
    producer_repo_root = (
        Path(producer_repo_root_value) if producer_repo_root_value else None
    )
    release_count_by_name: dict[str, int] | None = None
    if getattr(args, "portfolio_truth_include_release_count", False):
        release_count_by_name = load_release_count_by_name(
            output_dir=output_dir,
            username=args.username,
        )
    security_alerts_by_name: dict[str, dict] | None = None
    security_coverage_metadata: dict[str, object] | None = None
    if getattr(args, "portfolio_truth_include_security", False):
        receipt_path_value = getattr(args, "portfolio_truth_security_receipt", None)
        loaded_security = load_security_coverage_by_full_name(
            output_dir=output_dir,
            receipt_path=Path(receipt_path_value) if receipt_path_value else None,
            max_age_hours=getattr(
                args, "portfolio_truth_security_max_age_hours", 24
            ),
        )
        if loaded_security is not None:
            security_alerts_by_name = loaded_security.entries_by_full_name
            security_coverage_metadata = {
                "source_id": "github-security-coverage-receipt",
                "schema_version": loaded_security.schema_version,
                "produced_at": loaded_security.produced_at,
                "state": loaded_security.receipt_state,
                "age_hours": loaded_security.age_hours,
                "cohort_policy": loaded_security.cohort_policy,
                "cohort_repository_count": len(
                    loaded_security.cohort_repositories
                ),
                "path": loaded_security.source_path,
            }
    repo_status_by_name = load_live_repo_status_by_name(
        username=args.username,
        token=getattr(args, "token", None),
        cache=None if getattr(args, "no_cache", False) else ResponseCache(),
    )
    if repo_status_by_name is None:
        repo_status_by_name = load_repo_status_from_audit_by_name(
            output_dir=output_dir,
            username=args.username,
        )
    try:
        result = publish_portfolio_truth(
            workspace_root=workspace_root,
            output_dir=output_dir,
            registry_output=registry_output,
            portfolio_report_output=portfolio_report_output,
            catalog_path=Path(args.catalog) if args.catalog else None,
            legacy_registry_path=legacy_registry_path,
            include_notion=True,
            allow_empty_notion=getattr(args, "portfolio_truth_allow_empty_notion", False),
            release_count_by_name=release_count_by_name,
            security_alerts_by_name=security_alerts_by_name,
            security_coverage_metadata=security_coverage_metadata,
            repo_status_by_name=repo_status_by_name,
            producer_evidence=producer_evidence,
            producer_repo_root=producer_repo_root,
            require_producer_evidence=bool(
                os.environ.get("GHRA_REQUIRE_PRODUCER_EVIDENCE", "1") == "1"
            ),
        )
    except (PortfolioTruthPublishError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print_info(f"Portfolio truth snapshot: {result.latest_path}")
    print_info(f"Portfolio truth history snapshot: {result.snapshot_path}")
    print_info(f"Project registry compatibility output: {result.registry_output}")
    print_info(f"Portfolio audit compatibility output: {result.portfolio_report_output}")
    print_info(
        f"Portfolio truth generated for {result.project_count} projects "
        f"(registry {'updated' if result.registry_changed else 'unchanged'}, "
        f"report {'updated' if result.report_changed else 'unchanged'})"
    )


def run_portfolio_context_recovery_mode(args: Any) -> None:
    output_dir = Path(args.output_dir)
    workspace_root = Path(args.workspace_root)
    registry_output = (
        Path(args.registry_output)
        if args.registry_output
        else workspace_root / "project-registry.md"
    )
    portfolio_report_output = (
        Path(args.portfolio_report_output)
        if args.portfolio_report_output
        else workspace_root / "PORTFOLIO-AUDIT-REPORT.md"
    )
    legacy_registry_path = Path(args.registry) if args.registry else registry_output
    catalog_path = Path(args.catalog) if args.catalog else None
    build_result = build_portfolio_truth_snapshot(
        workspace_root=workspace_root,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=True,
    )
    plan = build_context_recovery_plan(
        build_result.snapshot,
        workspace_root=workspace_root,
        allow_dirty=bool(getattr(args, "allow_dirty_worktree", False)),
    )
    plan_json, plan_markdown = write_context_recovery_plan_artifacts(plan, output_dir=output_dir)
    print_info(f"Context recovery plan JSON: {plan_json}")
    print_info(f"Context recovery plan Markdown: {plan_markdown}")
    eligible_count = sum(project.status == "eligible" for project in plan.projects)
    skipped_count = sum(project.status == "skipped" for project in plan.projects)
    excluded_count = sum(project.status == "excluded" for project in plan.projects)
    print_info(
        f"Frozen context-recovery cohort: {plan.target_project_count} targets "
        f"({eligible_count} eligible, {skipped_count} skipped, {excluded_count} excluded)"
    )
    if not args.apply_context_recovery:
        return
    apply_result = apply_context_recovery_plan(
        build_result.snapshot,
        plan,
        workspace_root=workspace_root,
        catalog_path=catalog_path,
        limit=args.context_recovery_limit,
    )
    if apply_result.failed_projects:
        raise SystemExit("Context recovery failed for: " + ", ".join(apply_result.failed_projects))
    truth_result = publish_portfolio_truth(
        workspace_root=workspace_root,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=True,
    )
    print_info(
        f"Applied context recovery to {len(apply_result.updated_projects)} projects "
        f"(skipped/excluded {len(apply_result.skipped_projects)})."
    )
    print_info(f"Portfolio truth snapshot: {truth_result.latest_path}")
    print_info(f"Project registry compatibility output: {truth_result.registry_output}")
    print_info(f"Portfolio audit compatibility output: {truth_result.portfolio_report_output}")
