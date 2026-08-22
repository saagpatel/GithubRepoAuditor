from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from github_repo_auditor.cli_output import print_info
from github_repo_auditor.portfolio_security_gate import build_security_gate_report
from github_repo_auditor.portfolio_truth_types import TRUTH_LATEST_FILENAME
from github_repo_auditor.security_burndown import build_security_burndown, render_burndown_markdown


_SECURITY_GATE_OUTPUT_CONTRACT = "security_gate_cli_v2"
_REDACTED = "<redacted>"
_SAFE_GATE_MARKDOWN = {
    "pass": """# Portfolio Security Gate

Status: PASS
Source freshness: current

All required-cohort repos are clear of open high-severity GitHub security alerts.

Output policy: allowlisted aggregate summary; repo identities and reason codes redacted.
""",
    "fail": """# Portfolio Security Gate

Status: FAIL
Source freshness: current

Open high/critical findings are present. Consult the local canonical report for repo-level detail.

Output policy: allowlisted aggregate summary; repo identities and reason codes redacted.
""",
    "stale": """# Portfolio Security Gate

Status: STALE
Source freshness: stale

Portfolio truth freshness could not be verified. Refresh the local source before acting on this gate.

Output policy: allowlisted aggregate summary; repo identities and reason codes redacted.
""",
    "unknown": """# Portfolio Security Gate

Status: UNKNOWN
Source freshness: unavailable

Required-cohort security coverage is missing or incomplete. Do not treat the cohort as clear; consult the local canonical report.

Output policy: allowlisted aggregate summary; repo identities and reason codes redacted.
""",
}


def _safe_status(report: Any) -> str:
    """Return a fixed status token rather than provider-authored text."""
    status = getattr(report, "status", "")
    if status == "pass":
        return "pass"
    if status == "fail":
        return "fail"
    if status == "stale":
        return "stale"
    return "unknown"


def _safe_count(value: Any) -> int:
    """Keep aggregate counts numeric and non-negative at the CLI boundary."""
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return count if count >= 0 else 0


def _safe_freshness(report: Any) -> str:
    """Return a fixed freshness token without logging source timestamps/errors."""
    if getattr(report, "freshness_error", None):
        return "unavailable"
    if getattr(report, "is_stale", False):
        return "stale"
    return "current"


def _safe_security_gate_summary(report: Any) -> dict[str, Any]:
    """Build the privacy-safe CLI envelope.

    The full report remains available to local callers and tests. CLI output is
    intentionally limited to fixed status tokens and aggregate counts; repo
    identities, reason codes, timestamps, and provider-authored text never cross
    the terminal logging boundary.
    """
    return {
        "contract_version": _SECURITY_GATE_OUTPUT_CONTRACT,
        "status": _safe_status(report),
        "passed": _safe_status(report) == "pass",
        "scanned_count": _safe_count(getattr(report, "scanned_count", 0)),
        "required_cohort_count": _safe_count(
            getattr(report, "required_cohort_count", 0)
        ),
        "complete_count": _safe_count(getattr(report, "complete_count", 0)),
        "partial_count": _safe_count(getattr(report, "partial_count", 0)),
        "stale_count": _safe_count(getattr(report, "stale_count", 0)),
        "unknown_count": _safe_count(getattr(report, "unknown_count", 0)),
        "repos_with_open_high_critical": _safe_count(
            getattr(report, "repos_with_open_high_critical", 0)
        ),
        "total_open_critical": _safe_count(
            getattr(report, "total_open_critical", 0)
        ),
        "total_open_high": _safe_count(getattr(report, "total_open_high", 0)),
        "total_open_secrets": _safe_count(
            getattr(report, "total_open_secrets", 0)
        ),
        "source_freshness": _safe_freshness(report),
        "generated_at": _REDACTED,
        "freshness_error": None,
        "flagged_repos": [],
        "unadmitted_repos": [],
        "redaction_policy": "allowlisted-aggregate-only",
    }


def _render_safe_security_gate_markdown(status: str) -> str:
    """Return a fixed human-readable envelope selected by finite status."""
    if status == "pass":
        return _SAFE_GATE_MARKDOWN["pass"]
    if status == "fail":
        return _SAFE_GATE_MARKDOWN["fail"]
    if status == "stale":
        return _SAFE_GATE_MARKDOWN["stale"]
    return _SAFE_GATE_MARKDOWN["unknown"]


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
    summary = _safe_security_gate_summary(report)
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(_render_safe_security_gate_markdown(summary["status"]))
    if not report.passed:
        raise SystemExit(1)
