from __future__ import annotations

from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.diagnostics import (
    format_diagnostics_report,
    run_diagnostics,
    write_diagnostics_report,
)


def doctor_next_step_hint(username: str) -> str:
    return (
        f"Next step: run `audit {username} --html` for the standard workbook, then "
        f"`audit {username} --control-center` for read-only weekly triage."
    )


def run_doctor_mode(args: Any, config_inspection: Any) -> None:
    result = run_diagnostics(args, config_inspection=config_inspection, full=True)
    output_dir = Path(args.output_dir)
    artifact_path = write_diagnostics_report(result, output_dir, args.username)
    print(format_diagnostics_report(result))
    print_info(f"Diagnostics artifact: {artifact_path}")
    print_info(doctor_next_step_hint(args.username))
    if result.blocking_errors:
        raise SystemExit(1)
