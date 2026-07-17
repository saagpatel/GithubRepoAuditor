from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.portfolio_security_gate import (
    build_security_gate_report,
    render_security_gate_markdown,
)
from src.portfolio_truth_types import TRUTH_LATEST_FILENAME
from src.security_burndown import build_security_burndown, render_burndown_markdown


def run_security_burndown_mode(args: Any) -> None:
    """Dispatch for `audit security-burndown <username>`."""
    output_dir = Path(args.output_dir)
    username = args.username
    ghas_files = sorted(
        output_dir.glob(f"ghas-alerts-{username}-*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not ghas_files:
        print_info(
            f"No ghas-alerts-{username}-*.json found in {output_dir}. "
            "Run `audit report <username> --ghas-alerts` first."
        )
        raise SystemExit(1)
    ghas_path = ghas_files[-1]
    try:
        with ghas_path.open() as fh:
            ghas_data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print_info(f"Could not read {ghas_path}: {exc}")
        raise SystemExit(1)
    if not isinstance(ghas_data, dict):
        print_info(f"{ghas_path} is not a name-keyed object — cannot build burndown.")
        raise SystemExit(1)
    has_details = any(
        isinstance(entry.get("dependabot_details"), list)
        for entry in ghas_data.values()
        if isinstance(entry, dict)
    )
    if not has_details:
        print_info(
            f"Warning: {ghas_path.name} contains counts only — no per-alert detail.\n"
            "Re-run `audit report <username> --ghas-alerts` to capture detail, "
            "then retry security-burndown."
        )
        raise SystemExit(0)
    report = build_security_burndown(ghas_data)
    markdown = render_burndown_markdown(report)
    print(markdown)
    today = datetime.date.today().isoformat()
    out_path = output_dir / f"security-burndown-{username}-{today}.md"
    out_path.write_text(markdown, encoding="utf-8")
    print_info(f"Burndown written to {out_path}")
    json_path = output_dir / f"security-burndown-{username}-{today}.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print_info(f"Burndown JSON written to {json_path}")


def run_security_gate_mode(args: Any) -> None:
    """Dispatch for `audit security-gate`."""
    truth_path = Path(args.output_dir) / TRUTH_LATEST_FILENAME
    if not truth_path.exists():
        print_info(
            f"{TRUTH_LATEST_FILENAME} not found in {truth_path.parent}. "
            "Run `audit report <username> --portfolio-truth --portfolio-truth-include-security` first."
        )
        raise SystemExit(1)
    try:
        with truth_path.open(encoding="utf-8") as fh:
            portfolio_truth = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print_info(f"Could not read {truth_path}: {exc}")
        raise SystemExit(1)
    if not isinstance(portfolio_truth, dict):
        print_info(f"{truth_path} is not a portfolio-truth object.")
        raise SystemExit(1)
    report = build_security_gate_report(
        portfolio_truth,
        max_age_hours=getattr(args, "max_age_hours", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))  # codeql[py/clear-text-logging-sensitive-data] count-only alert summary
    else:
        print(render_security_gate_markdown(report))  # codeql[py/clear-text-logging-sensitive-data] count-only alert summary
    if not report.passed:
        raise SystemExit(1)
