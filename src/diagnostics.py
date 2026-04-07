from __future__ import annotations

import json
import os
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.config import ConfigInspection, inspect_config, validate_config_data
from src.excel_template import DEFAULT_TEMPLATE_PATH, TEMPLATE_INFO_SHEET, TEMPLATE_SHEETS
from src.portfolio_intelligence import DEFAULT_PROFILES


NOTION_CONFIG_PATH = Path("config") / "notion-config.json"
FINGERPRINT_FILENAME = ".audit-fingerprints.json"


@dataclass(frozen=True)
class DiagnosticCheck:
    key: str
    category: str
    severity: str
    status: str
    summary: str
    details: str = ""
    recommended_fix: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "category": self.category,
            "severity": self.severity,
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
            "recommended_fix": self.recommended_fix,
        }


@dataclass(frozen=True)
class DiagnosticsResult:
    status: str
    checks: list[DiagnosticCheck]
    requested_features: list[str]
    blocking_errors: int
    warnings: int

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "requested_features": self.requested_features,
            "blocking_errors": self.blocking_errors,
            "warnings": self.warnings,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_preflight_summary(self) -> dict:
        problems = [check.to_dict() for check in self.checks if check.status != "ok"]
        return {
            "status": self.status,
            "blocking_errors": self.blocking_errors,
            "warnings": self.warnings,
            "requested_features": self.requested_features,
            "checks": problems,
        }


def infer_requested_features(args) -> list[str]:
    features: list[str] = []
    if getattr(args, "repos", None):
        features.append("targeted-audit")
    elif getattr(args, "incremental", False):
        features.append("incremental-audit")
    else:
        features.append("full-audit")

    if getattr(args, "doctor", False):
        features.append("doctor")
    if getattr(args, "notion", False):
        features.append("notion-export")
    if getattr(args, "notion_sync", False):
        features.append("notion-sync")
    if getattr(args, "notion_registry", False):
        features.append("notion-registry")
    if getattr(args, "excel_mode", "template") == "template":
        features.append("excel-template")
    if getattr(args, "scorecard", False):
        features.append("scorecard")
    if getattr(args, "security_offline", False):
        features.append("security-offline")
    if getattr(args, "campaign", None):
        features.append(f"campaign:{args.campaign}")
    if getattr(args, "writeback_apply", False):
        features.append("writeback-apply")
    if getattr(args, "writeback_target", None):
        features.append(f"writeback-target:{args.writeback_target}")
    if getattr(args, "create_issues", False):
        features.append("github-issues")
    if getattr(args, "apply_metadata", False):
        features.append("apply-metadata")
    if getattr(args, "apply_readmes", False):
        features.append("apply-readmes")
    if getattr(args, "generate_manifest", False):
        features.append("generate-manifest")
    return features


def run_diagnostics(
    args,
    *,
    config_inspection: ConfigInspection | None = None,
    full: bool = False,
) -> DiagnosticsResult:
    config_inspection = config_inspection or inspect_config(Path(getattr(args, "config", None)) if getattr(args, "config", None) else None)
    requested_features = infer_requested_features(args)
    checks: list[DiagnosticCheck] = []
    output_dir = Path(getattr(args, "output_dir", "output"))

    _add_github_auth_checks(checks, args)
    _add_config_checks(checks, args, config_inspection, full=full)
    _add_notion_checks(checks, args, full=full)
    _add_excel_checks(checks, args)
    _add_filesystem_checks(checks, args, output_dir)
    _add_security_checks(checks, args)
    _add_writeback_checks(checks, args)
    _add_governance_checks(checks, args, output_dir)

    blocking_errors = sum(1 for check in checks if check.status == "error")
    warnings = sum(1 for check in checks if check.status == "warning")
    status = "error" if blocking_errors else ("warning" if warnings else "ok")
    return DiagnosticsResult(
        status=status,
        checks=checks,
        requested_features=requested_features,
        blocking_errors=blocking_errors,
        warnings=warnings,
    )


def should_block_run(result: DiagnosticsResult, preflight_mode: str) -> bool:
    if preflight_mode == "off":
        return False
    if result.blocking_errors:
        return True
    return preflight_mode == "strict" and result.warnings > 0


def format_preflight_summary(result: DiagnosticsResult) -> str:
    if result.status == "ok":
        return "Preflight: ok"
    return f"Preflight: {result.blocking_errors} errors, {result.warnings} warnings"


def format_diagnostics_report(result: DiagnosticsResult) -> str:
    lines = [
        f"Diagnostics status: {result.status}",
        f"Requested features: {', '.join(result.requested_features) or 'none'}",
        f"Blocking errors: {result.blocking_errors}",
        f"Warnings: {result.warnings}",
    ]
    grouped: dict[str, list[DiagnosticCheck]] = {}
    for check in result.checks:
        grouped.setdefault(check.category, []).append(check)
    for category in sorted(grouped):
        lines.append("")
        lines.append(f"[{category}]")
        for check in grouped[category]:
            lines.append(f"- {check.status.upper()}: {check.summary}")
            if check.details:
                lines.append(f"  {check.details}")
            if check.recommended_fix:
                lines.append(f"  Fix: {check.recommended_fix}")
    return "\n".join(lines)


def write_diagnostics_report(result: DiagnosticsResult, output_dir: Path, username: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = output_dir / f"diagnostics-{username}-{stamp}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2))
    return path


def _add_github_auth_checks(checks: list[DiagnosticCheck], args) -> None:
    token, source = _resolve_github_token(getattr(args, "token", None))
    details = f"Token source: {source}." if source else "No GitHub token was detected."
    hard_required = bool(
        getattr(args, "writeback_apply", False)
        or getattr(args, "create_issues", False)
        or getattr(args, "apply_metadata", False)
        or getattr(args, "apply_readmes", False)
    )
    if token:
        checks.append(
            DiagnosticCheck(
                key="github-token",
                category="github-auth",
                severity="info",
                status="ok",
                summary="GitHub authentication is available.",
                details=details,
            )
        )
        return
    checks.append(
        DiagnosticCheck(
            key="github-token",
            category="github-auth",
            severity="error" if hard_required else "warning",
            status="error" if hard_required else "warning",
            summary=(
                "GitHub authentication is required for the requested write/apply action."
                if hard_required
                else "GitHub authentication is not configured."
            ),
            details=details if hard_required else f"{details} The audit can still read public repos only.",
            recommended_fix="Set GITHUB_TOKEN or pass --token before running features that need private repo or write access.",
        )
    )


def _add_config_checks(
    checks: list[DiagnosticCheck],
    args,
    config_inspection: ConfigInspection,
    *,
    full: bool,
) -> None:
    if config_inspection.exists:
        if config_inspection.errors:
            for message in config_inspection.errors:
                checks.append(
                    DiagnosticCheck(
                        key="config-load",
                        category="config",
                        severity="error",
                        status="error",
                        summary="Audit config could not be loaded.",
                        details=message,
                        recommended_fix="Fix the YAML/JSON syntax or remove the broken config file path.",
                    )
                )
        else:
            checks.append(
                DiagnosticCheck(
                    key="config-load",
                    category="config",
                    severity="info",
                    status="ok",
                    summary="Audit config loaded successfully.",
                    details=f"Config path: {config_inspection.path}",
                )
            )
    elif full:
        checks.append(
            DiagnosticCheck(
                key="config-missing",
                category="config",
                severity="warning",
                status="warning",
                summary="No audit-config.yaml was found.",
                details=f"Checked {config_inspection.path}. CLI flags and built-in defaults will be used.",
                recommended_fix="Add audit-config.yaml if you want repeatable saved defaults.",
            )
        )

    if config_inspection.data:
        for issue in validate_config_data(config_inspection.data):
            checks.append(
                DiagnosticCheck(
                    key=f"config-{issue['key']}",
                    category="config",
                    severity=issue["severity"],
                    status=issue["severity"],
                    summary=issue["summary"],
                    details=issue.get("details", ""),
                    recommended_fix=issue.get("recommended_fix", ""),
                )
            )

    scoring_profile = getattr(args, "scoring_profile", None)
    if scoring_profile:
        profile_path = Path("config") / "scoring-profiles" / f"{scoring_profile}.json"
        if profile_path.is_file():
            checks.append(
                DiagnosticCheck(
                    key="config-scoring-profile",
                    category="config",
                    severity="info",
                    status="ok",
                    summary="Requested scoring profile exists.",
                    details=f"Profile path: {profile_path}",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    key="config-scoring-profile",
                    category="config",
                    severity="error",
                    status="error",
                    summary="Requested scoring profile was not found.",
                    details=f"Expected {profile_path}.",
                    recommended_fix="Choose an existing profile in config/scoring-profiles or remove --scoring-profile.",
                )
            )

    portfolio_profile = getattr(args, "portfolio_profile", "default")
    if portfolio_profile not in DEFAULT_PROFILES:
        checks.append(
            DiagnosticCheck(
                key="config-portfolio-profile",
                category="config",
                severity="error",
                status="error",
                summary="Requested portfolio profile is not defined.",
                details=f"Unknown profile: {portfolio_profile}.",
                recommended_fix=f"Use one of: {', '.join(sorted(DEFAULT_PROFILES))}.",
            )
        )


def _add_notion_checks(checks: list[DiagnosticCheck], args, *, full: bool) -> None:
    requested_sync = bool(getattr(args, "notion_sync", False))
    requested_registry = bool(getattr(args, "notion_registry", False))
    requested_writeback = bool(
        getattr(args, "writeback_apply", False)
        and getattr(args, "writeback_target", None) in {"notion", "all"}
    )
    if not any((requested_sync, requested_registry, requested_writeback, full)):
        return

    token = os.environ.get("NOTION_TOKEN", "").strip()
    config_state = _inspect_json_file(NOTION_CONFIG_PATH)

    if token:
        checks.append(
            DiagnosticCheck(
                key="notion-token",
                category="notion",
                severity="info",
                status="ok",
                summary="Notion authentication is available.",
            )
        )
    elif requested_sync or requested_registry or requested_writeback:
        checks.append(
            DiagnosticCheck(
                key="notion-token",
                category="notion",
                severity="error",
                status="error",
                summary="NOTION_TOKEN is required for the requested Notion action.",
                recommended_fix="Set NOTION_TOKEN before using Notion sync, registry, or Notion writeback.",
            )
        )
    elif full:
        checks.append(
            DiagnosticCheck(
                key="notion-token",
                category="notion",
                severity="warning",
                status="warning",
                summary="Notion token is not configured.",
                details="Notion features will be unavailable until NOTION_TOKEN is set.",
                recommended_fix="Set NOTION_TOKEN if you plan to use Notion sync or registry features.",
            )
        )

    if config_state["ok"]:
        checks.append(
            DiagnosticCheck(
                key="notion-config",
                category="notion",
                severity="info",
                status="ok",
                summary="Notion config file is readable.",
                details=f"Config path: {NOTION_CONFIG_PATH}",
            )
        )
        notion_config = config_state["data"]
    else:
        notion_config = {}
        level = "error" if (requested_sync or requested_registry or requested_writeback) else "warning"
        if config_state["exists"] or full or requested_sync or requested_registry or requested_writeback:
            checks.append(
                DiagnosticCheck(
                    key="notion-config",
                    category="notion",
                    severity=level,
                    status=level,
                    summary="Notion config file is missing or unreadable.",
                    details=config_state["message"] or f"Expected {NOTION_CONFIG_PATH}.",
                    recommended_fix="Create config/notion-config.json with the required database IDs for the Notion features you use.",
                )
            )

    if requested_sync and notion_config and not notion_config.get("events_database_id"):
        checks.append(
            DiagnosticCheck(
                key="notion-events-db",
                category="notion",
                severity="error",
                status="error",
                summary="Notion sync needs events_database_id.",
                details="config/notion-config.json is missing events_database_id.",
                recommended_fix="Add events_database_id to config/notion-config.json before using --notion-sync.",
            )
        )
    if requested_registry and notion_config and not notion_config.get("projects_data_source_id"):
        checks.append(
            DiagnosticCheck(
                key="notion-projects-source",
                category="notion",
                severity="error",
                status="error",
                summary="Notion registry needs projects_data_source_id.",
                details="config/notion-config.json is missing projects_data_source_id.",
                recommended_fix="Add projects_data_source_id before using --notion-registry.",
            )
        )
    if requested_writeback and notion_config:
        has_action_collection = bool(
            notion_config.get("action_requests_data_source_id") or notion_config.get("action_requests_db_id")
        )
        has_campaign_collection = bool(
            notion_config.get("campaign_runs_data_source_id")
            or notion_config.get("campaign_runs_db_id")
            or notion_config.get("recommendation_runs_data_source_id")
            or notion_config.get("recommendation_runs_db_id")
        )
        if not has_action_collection:
            checks.append(
                DiagnosticCheck(
                    key="notion-writeback-actions",
                    category="campaign-writeback",
                    severity="error",
                    status="error",
                    summary="Notion writeback needs an action request collection.",
                    details="Missing action_requests_data_source_id or action_requests_db_id.",
                    recommended_fix="Configure an Action Requests data source or database before using Notion writeback.",
                )
            )
        if not has_campaign_collection:
            checks.append(
                DiagnosticCheck(
                    key="notion-writeback-campaigns",
                    category="campaign-writeback",
                    severity="error",
                    status="error",
                    summary="Notion writeback needs a campaign run collection.",
                    details="Missing campaign_runs_* or recommendation_runs_* identifiers.",
                    recommended_fix="Configure campaign_runs or recommendation_runs IDs before using Notion writeback.",
                )
            )


def _add_excel_checks(checks: list[DiagnosticCheck], args) -> None:
    if getattr(args, "excel_mode", "template") != "template":
        return
    template_path = DEFAULT_TEMPLATE_PATH
    if not template_path.is_file():
        checks.append(
            DiagnosticCheck(
                key="excel-template-path",
                category="excel",
                severity="error",
                status="error",
                summary="Template workbook is missing.",
                details=f"Expected template at {template_path}.",
                recommended_fix="Restore assets/excel/analyst-template.xlsx or switch to --excel-mode standard.",
            )
        )
        return

    try:
        with zipfile.ZipFile(template_path) as archive:
            workbook_xml = archive.read("xl/workbook.xml")
            if TEMPLATE_INFO_SHEET.encode() not in workbook_xml:
                raise ValueError(f"Missing workbook marker sheet: {TEMPLATE_INFO_SHEET}")
            missing = [sheet for sheet in TEMPLATE_SHEETS if sheet.encode() not in workbook_xml]
            if missing:
                raise ValueError(f"Missing template sheets: {', '.join(missing)}")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        checks.append(
            DiagnosticCheck(
                key="excel-template-shell",
                category="excel",
                severity="error",
                status="error",
                summary="Template workbook exists but failed a lightweight integrity check.",
                details=str(exc),
                recommended_fix="Regenerate or restore the analyst workbook template before using --excel-mode template.",
            )
        )
        return

    checks.append(
        DiagnosticCheck(
            key="excel-template-shell",
            category="excel",
            severity="info",
            status="ok",
            summary="Template workbook is available.",
            details=f"Template path: {template_path}",
        )
    )


def _add_filesystem_checks(checks: list[DiagnosticCheck], args, output_dir: Path) -> None:
    writable_target = output_dir if output_dir.exists() else _nearest_existing_parent(output_dir)
    if writable_target and os.access(writable_target, os.W_OK):
        checks.append(
            DiagnosticCheck(
                key="output-dir",
                category="filesystem",
                severity="info",
                status="ok",
                summary="Output location is writable.",
                details=f"Resolved path: {output_dir}",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                key="output-dir",
                category="filesystem",
                severity="error",
                status="error",
                summary="Output location is not writable.",
                details=f"Cannot write under {output_dir}.",
                recommended_fix="Choose a writable --output-dir before running the audit.",
            )
        )

    requires_baseline = bool(getattr(args, "repos", None) or getattr(args, "incremental", False) or getattr(args, "generate_manifest", False))
    latest_report = _find_latest_report(output_dir)
    if requires_baseline and latest_report is None:
        checks.append(
            DiagnosticCheck(
                key="latest-report",
                category="history-warehouse",
                severity="error",
                status="error",
                summary="This run needs a previous audit report.",
                details=f"No audit-report-*.json files were found in {output_dir}.",
                recommended_fix="Run a full audit first so targeted, incremental, or regeneration paths have a baseline.",
            )
        )
    elif latest_report is not None:
        checks.append(
            DiagnosticCheck(
                key="latest-report",
                category="history-warehouse",
                severity="info",
                status="ok",
                summary="A previous audit report is available.",
                details=f"Latest report: {latest_report.name}",
            )
        )

    if getattr(args, "incremental", False):
        fingerprint_path = output_dir / FINGERPRINT_FILENAME
        if not fingerprint_path.is_file():
            checks.append(
                DiagnosticCheck(
                    key="fingerprints",
                    category="history-warehouse",
                    severity="error",
                    status="error",
                    summary="Incremental mode needs saved repo fingerprints.",
                    details=f"Missing {fingerprint_path}.",
                    recommended_fix="Run a full audit first to seed incremental fingerprints.",
                )
            )


def _add_security_checks(checks: list[DiagnosticCheck], args) -> None:
    if getattr(args, "scorecard", False) and getattr(args, "security_offline", False):
        checks.append(
            DiagnosticCheck(
                key="scorecard-offline",
                category="security-enrichment",
                severity="warning",
                status="warning",
                summary="Scorecard was requested, but security-offline will bypass it.",
                details="Offline mode disables live Scorecard enrichment.",
                recommended_fix="Remove --security-offline if you want live Scorecard data.",
            )
        )


def _add_writeback_checks(checks: list[DiagnosticCheck], args) -> None:
    if not getattr(args, "writeback_apply", False):
        return
    if getattr(args, "writeback_target", None) in {"github", "all"}:
        token, _ = _resolve_github_token(getattr(args, "token", None))
        if not token:
            checks.append(
                DiagnosticCheck(
                    key="github-writeback-auth",
                    category="campaign-writeback",
                    severity="error",
                    status="error",
                    summary="GitHub writeback needs authentication.",
                    recommended_fix="Set GITHUB_TOKEN or pass --token before using --writeback-apply with GitHub targets.",
                )
            )
    if not getattr(args, "campaign", None):
        checks.append(
            DiagnosticCheck(
                key="campaign-selection",
                category="campaign-writeback",
                severity="error",
                status="error",
                summary="Writeback apply needs a campaign selection.",
                recommended_fix="Pass --campaign before using --writeback-apply.",
            )
        )


def _add_governance_checks(checks: list[DiagnosticCheck], args, output_dir: Path) -> None:
    if getattr(args, "campaign", None) == "security-review" and _find_latest_report(output_dir) is None and getattr(args, "repos", None):
        checks.append(
            DiagnosticCheck(
                key="governance-baseline",
                category="governance",
                severity="error",
                status="error",
                summary="Security review targeted runs need a baseline report.",
                details=f"No prior report was found in {output_dir}.",
                recommended_fix="Run a full security review audit first before targeting a subset.",
            )
        )


def _inspect_json_file(path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "exists": False, "data": {}, "message": f"File not found: {path}"}
    try:
        return {"ok": True, "exists": True, "data": json.loads(path.read_text()), "message": ""}
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "exists": True, "data": {}, "message": str(exc)}


def _resolve_github_token(args_token: str | None) -> tuple[str, str]:
    if args_token:
        env_token = os.environ.get("GITHUB_TOKEN", "").strip()
        if env_token and env_token == args_token:
            return args_token, "GITHUB_TOKEN"
        return args_token, "configured token"
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token, "GITHUB_TOKEN"
    gh_token = _gh_auth_token()
    if gh_token:
        return gh_token, "gh auth token"
    return "", ""


def _gh_auth_token() -> str:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def _nearest_existing_parent(path: Path) -> Path | None:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current if current.exists() else None


def _find_latest_report(output_dir: Path) -> Path | None:
    reports = sorted(
        output_dir.glob("audit-report-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None
