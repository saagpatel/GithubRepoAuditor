"""Standalone report-only application flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.repo_improver import generate_manifest, write_manifest
from src.report_state import load_latest_report


def run_generate_manifest_mode(args: Any, parser: Any) -> None:
    output_dir = Path(args.output_dir)
    _report_path, report_data = load_latest_report(output_dir)
    if not report_data:
        parser.error("No existing audit report found in output directory")
    manifest = generate_manifest(report_data)
    manifest_path = write_manifest(manifest, output_dir)
    print_info(f"Improvement manifest: {manifest_path} ({len(manifest)} repos)")
