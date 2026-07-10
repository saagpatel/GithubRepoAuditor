"""Approved-campaign auto-apply flow.

Imports remain local to the flow so optional operator dependencies keep their
existing mode-specific loading behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.cli_output import print_info
from src.control_center_report_state import refresh_latest_report_state
from src.portfolio_truth_types import truth_latest_path


def run_auto_apply_approved_mode(args, output_dir: Path) -> None:
    """Apply approved campaign packets for repos that pass the automation trust bar."""
    from src.approval_ledger import load_approval_ledger_bundle
    from src.auto_apply import (
        build_trust_bar_index,
        filter_safe_actions,
        filter_trusted_repo_actions,
        get_approved_manual_campaigns,
        summarize_trust_bar,
    )
    from src.github_client import GitHubClient
    from src.ops_writeback import (
        apply_github_writeback,
        build_campaign_bundle,
        summarize_writeback_results,
    )
    from src.warehouse import load_latest_campaign_state

    cache = None if getattr(args, "no_cache", False) else None
    client: GitHubClient | None = (
        GitHubClient(token=args.token, cache=cache) if getattr(args, "token", None) else None
    )

    try:
        _report_path, _diff_dict, report = refresh_latest_report_state(output_dir, args)
    except FileNotFoundError:
        print_info("No existing audit report found in output directory. Run a normal audit first.")
        return

    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_info("No portfolio truth snapshot found. Run --portfolio-truth first.")
        return

    truth_snapshot = json.loads(truth_path.read_text())
    decision_quality_status = (
        (report.operator_summary or {})
        .get("decision_quality_v1", {})
        .get("decision_quality_status", "")
    )
    trust_bar_index = build_trust_bar_index(truth_snapshot, decision_quality_status)
    trust_bar_summary = summarize_trust_bar(truth_snapshot, decision_quality_status)
    print_info(
        "Automation trust bar: "
        f"{trust_bar_summary['automation_eligible_count']} opted-in repos; "
        f"{trust_bar_summary['baseline_eligible_count']} baseline opted-in repos; "
        f"{trust_bar_summary['trusted_repo_count']} repos pass the full trust bar "
        f"(decision quality: {trust_bar_summary['decision_quality_status']})."
    )
    if trust_bar_summary["automation_eligible_repos"]:
        print_info(
            "Automation-eligible repos: "
            + ", ".join(trust_bar_summary["automation_eligible_repos"])
        )

    bundle = load_approval_ledger_bundle(
        output_dir,
        report.to_dict(),
        list(report.operator_queue or []),
        approval_view="all",
    )
    approved_campaigns = get_approved_manual_campaigns(bundle)

    if not approved_campaigns:
        print_info("No approved-manual campaign packets found.")
        return

    total_applied = 0
    total_skipped = 0
    for record in approved_campaigns:
        campaign_type = str(record.get("subject_key") or "")
        if not campaign_type:
            continue
        _campaign_summary, actions = build_campaign_bundle(
            report.to_dict(),
            campaign_type=campaign_type,
            portfolio_profile=getattr(args, "portfolio_profile", None),
            collection_name=getattr(args, "collection", None),
            max_actions=None,
            writeback_target="github",
        )
        safe_actions = filter_safe_actions(actions)
        trusted_actions = filter_trusted_repo_actions(safe_actions, trust_bar_index)

        if not trusted_actions:
            skipped_repos = {str(a.get("repo") or "") for a in actions} - {
                str(a.get("repo") or "") for a in trusted_actions
            }
            print_info(
                f"Campaign {campaign_type!r}: 0 eligible actions "
                f"(skipped repos: {', '.join(sorted(skipped_repos)) or 'none'})"
            )
            total_skipped += len(actions)
            continue

        if getattr(args, "dry_run", False):
            print_info(
                f"Campaign {campaign_type!r}: {len(trusted_actions)} eligible actions "
                "but dry-run mode is enabled; no GitHub writes were attempted."
            )
            continue

        if client is None:
            print_info(
                f"Campaign {campaign_type!r}: {len(trusted_actions)} eligible actions "
                "but no GitHub client available (dry run)."
            )
            continue

        previous_state = load_latest_campaign_state(output_dir, campaign_type)
        github_results, _refs, _drift, _closure = apply_github_writeback(
            client,
            trusted_actions,
            previous_state=previous_state,
            sync_mode=str(record.get("sync_mode") or "reconcile"),
            campaign_summary=_campaign_summary,
            github_projects_config=None,
            operator_context={},
        )
        summary = summarize_writeback_results(github_results, "github", apply=True)
        applied_count = int(summary.get("applied_count", 0))
        total_applied += applied_count
        print_info(
            f"Campaign {campaign_type!r}: applied {applied_count} / {len(trusted_actions)} actions."
        )

    print_info(f"Auto-apply complete: {total_applied} applied, {total_skipped} skipped.")
