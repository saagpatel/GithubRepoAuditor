"""Acknowledgment-capture application flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.diff import diff_reports
from src.history import find_previous
from src.operator_acknowledgments import (
    build_acknowledgment_record,
    find_matching_change,
    find_sibling_changes,
    load_acknowledgments,
    save_acknowledgment,
)
from src.recurring_review import MATERIALITY_THRESHOLDS, evaluate_material_changes
from src.report_state import load_latest_report


def run_acknowledgment_capture_mode(args: Any, parser: Any) -> None:
    if not args.acknowledge_target:
        parser.error("--acknowledge-target is required for acknowledgment capture")
    if not args.acknowledge_kind:
        parser.error("--acknowledge-kind is required for acknowledgment capture")
    if not (args.acknowledge_note or "").strip():
        parser.error("--acknowledge-note is required and must explain the acknowledgment")
    output_dir = Path(args.output_dir)
    report_path, report_data = load_latest_report(output_dir)
    if not report_path or not report_data:
        parser.error("No existing audit report found in output directory")
    diff_dict = None
    previous_path = find_previous(report_path.name)
    if previous_path:
        diff_dict = diff_reports(
            previous_path, report_path, portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        ).to_dict()
    material_changes = evaluate_material_changes(
        report_data, diff_data=diff_dict, thresholds=MATERIALITY_THRESHOLDS["standard"]
    )
    acknowledgments = load_acknowledgments(output_dir, args.username)
    matched = find_matching_change(
        repo_name=args.acknowledge_target, change_kind=args.acknowledge_kind,
        material_changes=material_changes, acknowledgments=acknowledgments,
    )
    if not matched:
        parser.error(f"No open '{args.acknowledge_kind}' change found for '{args.acknowledge_target}' in the latest report")
    reviewer = args.acknowledge_reviewer or args.approval_reviewer
    record = build_acknowledgment_record(matched, reviewer=reviewer, note=args.acknowledge_note)
    saved_path = save_acknowledgment(output_dir, args.username, record)
    print_info(f"Acknowledged {args.acknowledge_kind} for {args.acknowledge_target} (change_key={record['change_key'][:12]}…, reviewer={reviewer})")
    for sibling in find_sibling_changes(matched, material_changes):
        sibling_record = build_acknowledgment_record(sibling, reviewer=reviewer, note=args.acknowledge_note)
        save_acknowledgment(output_dir, args.username, sibling_record)
        print_info(f"Acknowledged sibling {sibling.get('change_type')} for {sibling.get('repo_name')} (change_key={sibling_record['change_key'][:12]}…)")
    print_info(f"Acknowledgment store: {saved_path}")
    print_info("Run --control-center to confirm the item is filtered from the queue.")
