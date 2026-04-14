# GitHub Repo Auditor — CLI entry point
#
# Orchestrates the full audit pipeline:
#   1. Fetch repo metadata from GitHub REST API (or GraphQL bulk fetch)
#   2. Shallow-clone each repo to a temp workspace
#   3. Run all 12 analyzers (completeness, interest, security, cicd, …)
#   4. Score and tier each repo via the configured scoring profile
#   5. Write JSON / Markdown / Excel / HTML reports to the output directory
#
# Three run modes:
#   full        — re-analyze every repo for the given username
#   targeted    — re-analyze specific repos (--repos) and merge into latest report
#   incremental — re-analyze only repos with new pushes since last run
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from src.analyzers import run_all_analyzers
from src.baseline_context import (
    build_baseline_context_from_args,
    build_watch_state,
    compare_baseline_context,
    extract_baseline_context,
    format_mismatch_value,
    normalize_scoring_profile,
)
from src.cache import ResponseCache
from src.cli_output import create_progress, print_info, print_status, print_warning
from src.cloner import clone_workspace
from src.github_client import GitHubClient
from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.recurring_review import FULL_REFRESH_DAYS
from src.report_enrichment import build_run_change_counts, build_run_change_summary
from src.reporter import (
    write_json_report,
    write_markdown_report,
    write_pcc_export,
    write_raw_metadata,
)
from src.scorer import score_repo
from src.terminology import ACTION_SYNC_CANONICAL_LABELS

ANALYSIS_WORKERS = 4
DEFAULT_PORTFOLIO_WORKSPACE = Path.home() / "Projects"
CLI_MODE_GUIDE = """GitHub portfolio operating system with four product modes:
  First Run     setup, baseline creation, first workbook, first control-center read
  Weekly Review normal workbook-first operator loop
  Deep Dive     repo-level drilldown and investigation
  Action Sync   campaign, writeback, GitHub Projects, and Notion mirroring

Recommended defaults:
  - Start with --doctor before the first real run
  - Prefer --excel-mode standard for the stable workbook path
  - Use --control-center for read-only daily triage
  - Treat campaigns, writeback, catalog overrides, scorecards overrides, and GitHub Projects as advanced workflows"""

CLI_MODE_EXAMPLES = """Examples by mode:
  First Run:
    audit <github-username> --doctor
    audit <github-username> --html
    audit <github-username> --control-center

  Weekly Review:
    audit <github-username> --html
    audit <github-username> --control-center

  Deep Dive:
    audit <github-username> --repos <repo-name> --html

  Action Sync:
    audit <github-username> --campaign security-review --writeback-target github
    audit <github-username> --campaign security-review --writeback-target all --github-projects"""


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _gh_auth_token() -> str | None:
    """Fall back to `gh auth token` if GITHUB_TOKEN env var is unset."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# ── Argument parser ──────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-repo-auditor",
        description=CLI_MODE_GUIDE,
        epilog=CLI_MODE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "username",
        help="GitHub username to audit",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN") or _gh_auth_token(),
        help="GitHub personal access token (default: $GITHUB_TOKEN or `gh auth token`)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for output files (default: output/)",
    )
    parser.add_argument(
        "--portfolio-truth",
        action="store_true",
        help="Generate the canonical portfolio truth snapshot and compatibility portfolio artifacts",
    )
    parser.add_argument(
        "--portfolio-context-recovery",
        action="store_true",
        help="Build the active/recent weak-context recovery plan and optionally apply the safe context upgrades",
    )
    parser.add_argument(
        "--apply-context-recovery",
        action="store_true",
        help="Apply eligible context recovery updates after building the recovery plan",
    )
    parser.add_argument(
        "--context-recovery-limit",
        type=int,
        default=None,
        help="Optional cap on how many eligible recovery targets to apply in one run",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_PORTFOLIO_WORKSPACE,
        help="Workspace root to scan for portfolio truth generation (default: ~/Projects)",
    )
    parser.add_argument(
        "--registry-output",
        type=Path,
        default=None,
        help="Where to publish the generated project-registry.md compatibility artifact",
    )
    parser.add_argument(
        "--portfolio-report-output",
        type=Path,
        default=None,
        help="Where to publish the generated PORTFOLIO-AUDIT-REPORT.md compatibility artifact",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="Path to portfolio-catalog.yaml for local repo ownership and lifecycle contracts",
    )
    parser.add_argument(
        "--skip-forks",
        action="store_true",
        help="Exclude forked repos from the audit",
    )
    parser.add_argument(
        "--skip-archived",
        action="store_true",
        help="Exclude archived repos from the audit",
    )
    parser.add_argument(
        "--skip-clone",
        action="store_true",
        help="Skip the clone step (metadata only)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to project-registry.md for reconciliation",
    )
    parser.add_argument(
        "--sync-registry",
        action="store_true",
        help="Auto-add untracked GitHub repos to the registry (requires --registry)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass API response cache",
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        default=None,
        metavar="REPO",
        help="Audit only these specific repos (by name or URL). Merges into the most recent full report.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only re-audit repos that changed since last run (compares pushed_at timestamps)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed output",
    )
    parser.add_argument(
        "--graphql",
        action="store_true",
        help="Use GraphQL API for faster bulk metadata fetch",
    )
    parser.add_argument(
        "--diff",
        type=Path,
        default=None,
        metavar="PREVIOUS_REPORT",
        help="Compare against a previous audit-report JSON to show changes",
    )
    parser.add_argument(
        "--badges",
        action="store_true",
        help="Generate Shields.io badge JSON files and badges.md",
    )
    parser.add_argument(
        "--upload-badges",
        action="store_true",
        help="Upload badge JSON to GitHub Gist for endpoint badges (implies --badges)",
    )
    parser.add_argument(
        "--notion",
        action="store_true",
        help="Generate Notion audit event JSON (dry-run, no API calls)",
    )
    parser.add_argument(
        "--notion-sync",
        action="store_true",
        help="Push audit events to Notion API (implies --notion)",
    )
    parser.add_argument(
        "--portfolio-readme",
        action="store_true",
        help="Generate PORTFOLIO.md from audit data",
    )
    parser.add_argument(
        "--readme-suggestions",
        action="store_true",
        help="Generate per-repo README improvement suggestions",
    )
    parser.add_argument(
        "--notion-registry",
        action="store_true",
        help="Use Notion Local Portfolio Projects as registry source (requires NOTION_TOKEN)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate interactive HTML dashboard",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate PDF audit report",
    )
    parser.add_argument(
        "--excel-mode",
        choices=["template", "standard"],
        default="standard",
        help="Generate the stable standard workbook (default) or the template-backed presentation workbook",
    )
    parser.add_argument(
        "--scoring-profile",
        type=str,
        default=None,
        metavar="NAME",
        help="Use a custom scoring profile from config/scoring-profiles/NAME.json",
    )
    parser.add_argument(
        "--scorecards",
        type=Path,
        default=None,
        metavar="PATH",
        help="Use a custom scorecards config file (default: config/scorecards.yaml)",
    )
    parser.add_argument(
        "--portfolio-profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Apply a ranking overlay profile for analyst-facing outputs (default: default)",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        metavar="NAME",
        help="Filter analyst-facing outputs to a named collection (does not affect audited repos)",
    )
    parser.add_argument(
        "--review-pack",
        action="store_true",
        help="Generate a concise analyst review pack from the current run and compare context",
    )
    parser.add_argument(
        "--scorecard",
        action="store_true",
        help="Enrich public repos with OpenSSF Scorecard data",
    )
    parser.add_argument(
        "--security-offline",
        action="store_true",
        help="Use local security analysis only and skip GitHub-native or external security enrichment",
    )
    parser.add_argument(
        "--campaign",
        choices=["security-review", "promotion-push", "archive-sweep", "showcase-publish", "maintenance-cleanup"],
        default=None,
        help="Build a managed campaign view from the current report facts",
    )
    parser.add_argument(
        "--writeback-target",
        choices=["github", "notion", "all"],
        default=None,
        help="Select which external system should receive writeback actions",
    )
    parser.add_argument(
        "--writeback-apply",
        action="store_true",
        help="Execute live writeback instead of preview-only planning",
    )
    parser.add_argument(
        "--github-projects",
        action="store_true",
        help="Mirror managed GitHub campaign actions into a configured GitHub Projects v2 board",
    )
    parser.add_argument(
        "--github-projects-config",
        type=Path,
        default=None,
        help="Path to github-projects.yaml for GitHub Projects v2 mirroring",
    )
    parser.add_argument(
        "--campaign-sync-mode",
        choices=["reconcile", "append-only", "close-missing"],
        default="reconcile",
        help="How managed campaign records should reconcile against prior state (default: reconcile)",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=20,
        help="Maximum managed actions to include in a campaign run (default: 20)",
    )
    parser.add_argument(
        "--governance-view",
        choices=["all", "ready", "drifted", "approved", "applied"],
        default="all",
        help="Filter governance surfaces to a specific operator state (default: all)",
    )
    parser.add_argument(
        "--governance-scope",
        choices=["all", "codeql", "secret-scanning", "push-protection", "code-security"],
        default="all",
        help="Select which governed control family a local approval should cover (default: all)",
    )
    parser.add_argument(
        "--auto-archive",
        action="store_true",
        help="Generate archive candidate report for consistently low-scoring repos",
    )
    parser.add_argument(
        "--narrative",
        action="store_true",
        help="Generate AI portfolio narrative (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to audit-config.yaml (default: ./audit-config.yaml if exists)",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run setup diagnostics only and exit without auditing repos",
    )
    parser.add_argument(
        "--control-center",
        action="store_true",
        help="Summarize the latest operator state without running a new audit",
    )
    parser.add_argument(
        "--approval-center",
        action="store_true",
        help="Summarize the latest approval workflow state without running a new audit",
    )
    parser.add_argument(
        "--triage-view",
        choices=["all", "urgent", "ready", "blocked", "deferred"],
        default="all",
        help="Filter control-center triage output to one lane (default: all)",
    )
    parser.add_argument(
        "--approval-view",
        choices=["all", "ready", "approved", "needs-reapproval", "blocked", "applied"],
        default="all",
        help="Filter approval-center output to one approval state (default: all)",
    )
    parser.add_argument(
        "--approve-governance",
        action="store_true",
        help="Capture a local governance approval from the latest governed preview",
    )
    parser.add_argument(
        "--approve-packet",
        action="store_true",
        help="Capture a local campaign approval for the selected campaign packet",
    )
    parser.add_argument(
        "--review-governance",
        action="store_true",
        help="Capture a local follow-up review for an already-approved governance scope",
    )
    parser.add_argument(
        "--review-packet",
        action="store_true",
        help="Capture a local follow-up review for an already-approved campaign packet",
    )
    parser.add_argument(
        "--approval-reviewer",
        type=str,
        default=None,
        help="Reviewer name recorded on local approvals (default: $USER, then git user.name, then local-operator)",
    )
    parser.add_argument(
        "--approval-note",
        type=str,
        default="",
        help="Optional free-text note stored with the local approval record",
    )
    parser.add_argument(
        "--preflight-mode",
        choices=["auto", "off", "strict"],
        default="auto",
        help="Control automatic setup checks before a run (default: auto)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Re-run audit on interval (use with --watch-interval)",
    )
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=3600,
        help="Seconds between watch runs (default: 3600)",
    )
    parser.add_argument(
        "--watch-strategy",
        choices=["adaptive", "incremental", "full"],
        default="adaptive",
        help="How watch mode chooses each cycle: adaptive (default), incremental, or full",
    )
    parser.add_argument(
        "--create-issues",
        action="store_true",
        help="Create GitHub issues for high-priority action items",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview repos that would be audited without cloning or analyzing",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a Rich diff summary to stderr after audit (requires a previous report)",
    )
    parser.add_argument(
        "--analyzers-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Directory containing custom analyzer .py files to load and run",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a partial audit run from saved progress",
    )
    parser.add_argument(
        "--vuln-check",
        action="store_true",
        help="Query OSV.dev for known vulnerabilities in repo dependencies",
    )
    parser.add_argument(
        "--generate-manifest",
        action="store_true",
        help="Generate an improvement manifest from the latest audit report",
    )
    parser.add_argument(
        "--apply-metadata",
        action="store_true",
        help="Apply description and topics updates from an improvements file",
    )
    parser.add_argument(
        "--apply-readmes",
        action="store_true",
        help="Push README updates from an improvements file via the Contents API",
    )
    parser.add_argument(
        "--improvements-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a JSON file with generated improvements (descriptions, topics, READMEs)",
    )
    return parser


# ── Repo filtering and selection helpers ─────────────────────────────
def _filter_repos(
    repos: list[RepoMetadata],
    *,
    skip_forks: bool = False,
    skip_archived: bool = False,
) -> list[RepoMetadata]:
    """Apply exclusion filters to the repo list."""
    filtered = repos
    if skip_forks:
        filtered = [r for r in filtered if not r.fork]
    if skip_archived:
        filtered = [r for r in filtered if not r.archived]
    return filtered


def _write_json(
    username: str,
    repos: list[RepoMetadata],
    errors: list[dict],
    total_fetched: int,
    output_dir: Path,
    audits: list[RepoAudit] | None = None,
) -> Path:
    """Write audit results JSON and return the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "raw_metadata.json"

    if audits:
        # Compute tier distribution
        tier_dist: dict[str, int] = {}
        for a in audits:
            tier_dist[a.completeness_tier] = tier_dist.get(a.completeness_tier, 0) + 1
        avg_score = sum(a.overall_score for a in audits) / len(audits) if audits else 0.0

        report = {
            "username": username,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_repos": total_fetched,
            "repos_audited": len(audits),
            "average_score": round(avg_score, 3),
            "tier_distribution": tier_dist,
            "audits": [a.to_dict() for a in audits],
            "errors": errors,
        }
    else:
        report = {
            "username": username,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_repos": total_fetched,
            "repos_included": len(repos),
            "repos": [r.to_dict() for r in repos],
            "errors": errors,
        }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    return output_path


def _print_verbose(audit: RepoAudit) -> None:
    """Print per-dimension score breakdown for a repo."""
    print(f"\n  {'─' * 50}", file=sys.stderr)
    print(
        f"  {audit.metadata.name}  "
        f"score={audit.overall_score:.2f}  "
        f"tier={audit.completeness_tier}"
        f"{'  flags=' + ','.join(audit.flags) if audit.flags else ''}",
        file=sys.stderr,
    )
    for r in audit.analyzer_results:
        bar = "█" * int(r.score * 10) + "░" * (10 - int(r.score * 10))
        print(
            f"    {r.dimension:<17} {bar} {r.score:.2f}",
            file=sys.stderr,
        )
        for finding in r.findings[:3]:
            print(f"      · {finding}", file=sys.stderr)


def _resolve_repo_names(repos_arg: list[str]) -> list[str]:
    """Extract repo names from URLs or bare names."""
    names = []
    seen: set[str] = set()
    for r in repos_arg:
        r = r.strip().rstrip("/")
        if "/" in r:
            # URL like https://github.com/user/RepoName
            name = r.split("/")[-1]
        else:
            name = r
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def _normalize_profile_name(profile_name: str | None) -> str:
    return normalize_scoring_profile(profile_name)


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ── JSON deserialization helpers ──────────────────────────────────────
def _audit_from_dict(data: dict) -> RepoAudit:
    meta_data = data.get("metadata", {})
    metadata = RepoMetadata(
        name=meta_data["name"],
        full_name=meta_data["full_name"],
        description=meta_data.get("description"),
        language=meta_data.get("language"),
        languages=meta_data.get("languages", {}),
        private=meta_data["private"],
        fork=meta_data["fork"],
        archived=meta_data["archived"],
        created_at=_parse_iso_dt(meta_data.get("created_at")),  # type: ignore[arg-type]
        updated_at=_parse_iso_dt(meta_data.get("updated_at")),  # type: ignore[arg-type]
        pushed_at=_parse_iso_dt(meta_data.get("pushed_at")),
        default_branch=meta_data.get("default_branch", "main"),
        stars=meta_data.get("stars", 0),
        forks=meta_data.get("forks", 0),
        open_issues=meta_data.get("open_issues", 0),
        size_kb=meta_data.get("size_kb", 0),
        html_url=meta_data.get("html_url", ""),
        clone_url=meta_data.get("clone_url", ""),
        topics=meta_data.get("topics", []),
    )
    analyzer_results = [
        AnalyzerResult(
            dimension=result["dimension"],
            score=result["score"],
            max_score=result["max_score"],
            findings=result["findings"],
            details=result.get("details", {}),
        )
        for result in data.get("analyzer_results", [])
    ]
    return RepoAudit(
        metadata=metadata,
        analyzer_results=analyzer_results,
        overall_score=data.get("overall_score", 0),
        completeness_tier=data.get("completeness_tier", "abandoned"),
        interest_score=data.get("interest_score", 0),
        interest_tier=data.get("interest_tier", "mundane"),
        grade=data.get("grade", "F"),
        interest_grade=data.get("interest_grade", "F"),
        badges=data.get("badges", []),
        next_badges=data.get("next_badges", []),
        flags=data.get("flags", []),
        lenses=data.get("lenses", {}),
        hotspots=data.get("hotspots", []),
        action_candidates=data.get("action_candidates", []),
        security_posture=data.get("security_posture", {}),
        score_explanation=data.get("score_explanation", {}),
        portfolio_catalog=data.get("portfolio_catalog", {}),
        scorecard=data.get("scorecard", {}),
    )


def _report_from_dict(data: dict) -> AuditReport:
    from src.registry_parser import RegistryReconciliation

    reconciliation = None
    if data.get("reconciliation"):
        reconciliation = RegistryReconciliation(**data["reconciliation"])

    summary = data.get("summary", {})
    return AuditReport(
        username=data["username"],
        generated_at=_parse_iso_dt(data.get("generated_at")) or datetime.now(timezone.utc),
        total_repos=data.get("total_repos", 0),
        repos_audited=data.get("repos_audited", 0),
        tier_distribution=data.get("tier_distribution", {}),
        average_score=data.get("average_score", 0),
        language_distribution=data.get("language_distribution", {}),
        audits=[_audit_from_dict(audit) for audit in data.get("audits", [])],
        errors=data.get("errors", []),
        portfolio_grade=data.get("portfolio_grade", "F"),
        portfolio_health_score=data.get("portfolio_health_score", 0),
        tech_stack=data.get("tech_stack", {}),
        best_work=data.get("best_work", []),
        most_active=summary.get("most_active", []),
        most_neglected=summary.get("most_neglected", []),
        highest_scored=summary.get("highest_scored", []),
        lowest_scored=summary.get("lowest_scored", []),
        scoring_profile=data.get("scoring_profile", "default"),
        run_mode=data.get("run_mode", "full"),
        portfolio_baseline_size=data.get("portfolio_baseline_size", len(data.get("audits", []))),
        baseline_signature=data.get("baseline_signature", ""),
        baseline_context=data.get("baseline_context", {}),
        schema_version=data.get("schema_version", "3.7"),
        lenses=data.get("lenses", {}),
        hotspots=data.get("hotspots", []),
        implementation_hotspots=data.get("implementation_hotspots", []),
        implementation_hotspots_summary=data.get("implementation_hotspots_summary", {}),
        portfolio_outcomes_summary=data.get("portfolio_outcomes_summary", {}),
        operator_effectiveness_summary=data.get("operator_effectiveness_summary", {}),
        high_pressure_queue_history=data.get("high_pressure_queue_history", []),
        campaign_readiness_summary=data.get("campaign_readiness_summary", {}),
        action_sync_summary=data.get("action_sync_summary", {}),
        next_action_sync_step=data.get("next_action_sync_step", ""),
        action_sync_packets=data.get("action_sync_packets", []),
        apply_readiness_summary=data.get("apply_readiness_summary", {}),
        next_apply_candidate=data.get("next_apply_candidate", {}),
        action_sync_outcomes=data.get("action_sync_outcomes", []),
        campaign_outcomes_summary=data.get("campaign_outcomes_summary", {}),
        next_monitoring_step=data.get("next_monitoring_step", {}),
        action_sync_tuning=data.get("action_sync_tuning", []),
        campaign_tuning_summary=data.get("campaign_tuning_summary", {}),
        next_tuned_campaign=data.get("next_tuned_campaign", {}),
        historical_portfolio_intelligence=data.get("historical_portfolio_intelligence", []),
        intervention_ledger_summary=data.get("intervention_ledger_summary", {}),
        next_historical_focus=data.get("next_historical_focus", {}),
        action_sync_automation=data.get("action_sync_automation", []),
        automation_guidance_summary=data.get("automation_guidance_summary", {}),
        next_safe_automation_step=data.get("next_safe_automation_step", {}),
        approval_ledger=data.get("approval_ledger", []),
        approval_workflow_summary=data.get("approval_workflow_summary", {}),
        next_approval_review=data.get("next_approval_review", {}),
        security_posture=data.get("security_posture", {}),
        security_governance_preview=data.get("security_governance_preview", []),
        collections=data.get("collections", {}),
        profiles=data.get("profiles", {}),
        scenario_summary=data.get("scenario_summary", {}),
        action_backlog=data.get("action_backlog", []),
        campaign_summary=data.get("campaign_summary", {}),
        writeback_preview=data.get("writeback_preview", {}),
        writeback_results=data.get("writeback_results", {}),
        action_runs=data.get("action_runs", []),
        external_refs=data.get("external_refs", {}),
        managed_state_drift=data.get("managed_state_drift", []),
        rollback_preview=data.get("rollback_preview", {}),
        campaign_history=data.get("campaign_history", []),
        governance_preview=data.get("governance_preview", {}),
        governance_approval=data.get("governance_approval", {}),
        governance_results=data.get("governance_results", {}),
        governance_history=data.get("governance_history", []),
        governance_drift=data.get("governance_drift", []),
        governance_summary=data.get("governance_summary", {}),
        preflight_summary=data.get("preflight_summary", {}),
        review_summary=data.get("review_summary", {}),
        review_alerts=data.get("review_alerts", []),
        material_changes=data.get("material_changes", []),
        review_targets=data.get("review_targets", []),
        review_history=data.get("review_history", []),
        watch_state=data.get("watch_state", {}),
        operator_summary=data.get("operator_summary", {}),
        operator_queue=data.get("operator_queue", []),
        portfolio_catalog_summary=data.get("portfolio_catalog_summary", {}),
        operating_paths_summary=data.get("operating_paths_summary", {}),
        intent_alignment_summary=data.get("intent_alignment_summary", {}),
        scorecards_summary=data.get("scorecards_summary", {}),
        scorecard_programs=data.get("scorecard_programs", {}),
        reconciliation=reconciliation,
    )


def _apply_portfolio_catalog(report: AuditReport, args) -> AuditReport:
    from src.portfolio_catalog import (
        DEFAULT_CATALOG_PATH,
        build_catalog_line,
        build_intent_alignment_summary,
        build_portfolio_catalog_summary,
        catalog_entry_for_repo,
        evaluate_intent_alignment,
        load_portfolio_catalog,
    )
    from src.report_enrichment import build_operator_focus

    catalog_path = getattr(args, "catalog", None) or DEFAULT_CATALOG_PATH
    catalog_data = load_portfolio_catalog(Path(catalog_path))
    queue_by_repo = {
        str(item.get("repo") or item.get("repo_name") or "").strip(): item
        for item in (report.operator_queue or [])
        if str(item.get("repo") or item.get("repo_name") or "").strip()
    }
    for audit in report.audits:
        metadata = audit.metadata.to_dict()
        base_entry = catalog_entry_for_repo(metadata, catalog_data)
        focus_source = queue_by_repo.get(audit.metadata.name, {})
        operator_focus = build_operator_focus(focus_source)
        intent_alignment, intent_alignment_reason = evaluate_intent_alignment(
            base_entry,
            completeness_tier=audit.completeness_tier,
            archived=audit.metadata.archived,
            operator_focus=operator_focus,
        )
        audit.portfolio_catalog = {
            **base_entry,
            "catalog_line": build_catalog_line(base_entry),
            "intent_alignment": intent_alignment,
            "intent_alignment_reason": intent_alignment_reason,
            "intent_alignment_line": f"{intent_alignment}: {intent_alignment_reason}",
            "operator_focus": operator_focus,
        }

    audit_lookup = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
    for item in report.operator_queue:
        repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
        catalog_entry = audit_lookup.get(repo_name, {})
        if catalog_entry:
            item["portfolio_catalog"] = dict(catalog_entry)
            item["catalog_line"] = catalog_entry.get("catalog_line", "")
            item["intent_alignment"] = catalog_entry.get("intent_alignment", "missing-contract")
            item["intent_alignment_reason"] = catalog_entry.get("intent_alignment_reason", "")

    report.portfolio_catalog_summary = build_portfolio_catalog_summary(
        report.audits,
        catalog_path=str(catalog_path),
    )
    report.portfolio_catalog_summary["catalog_exists"] = catalog_data.get("exists", False)
    report.portfolio_catalog_summary["errors"] = catalog_data.get("errors", [])
    report.portfolio_catalog_summary["warnings"] = catalog_data.get("warnings", [])
    report.intent_alignment_summary = build_intent_alignment_summary(report.audits)
    return report


def _apply_scorecards(report: AuditReport, args) -> AuditReport:
    from src.report_enrichment import build_maturity_gap_summary, build_scorecard_line
    from src.scorecards import (
        DEFAULT_SCORECARDS_PATH,
        evaluate_scorecards_for_report,
        load_scorecards,
    )

    scorecards_path = getattr(args, "scorecards", None) or DEFAULT_SCORECARDS_PATH
    scorecards_data = load_scorecards(Path(scorecards_path))
    repo_results, summary, programs = evaluate_scorecards_for_report(report, scorecards_data)
    by_repo = {result.get("repo", ""): result for result in repo_results}
    for audit in report.audits:
        result = by_repo.get(audit.metadata.name, {})
        audit.scorecard = dict(result)
        if audit.portfolio_catalog:
            audit.portfolio_catalog["scorecard"] = dict(result)
    for item in report.operator_queue:
        repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
        result = by_repo.get(repo_name, {})
        if result:
            item["scorecard"] = dict(result)
            item["scorecard_line"] = build_scorecard_line(item)
            item["maturity_gap_summary"] = build_maturity_gap_summary(item)
    report.scorecards_summary = summary
    report.scorecard_programs = programs
    return report


def _apply_operating_paths(report: AuditReport) -> AuditReport:
    from src.portfolio_pathing import (
        build_operating_path_entry,
        build_operating_path_line,
        build_operating_paths_summary,
    )

    for audit in report.audits:
        catalog_entry = dict(audit.portfolio_catalog or {})
        if not catalog_entry:
            continue
        path_entry = build_operating_path_entry(
            catalog_entry,
            intent_alignment=catalog_entry.get("intent_alignment", ""),
            archived=audit.metadata.archived,
            completeness_tier=audit.completeness_tier,
            decision_quality_status=(report.operator_summary or {}).get("decision_quality_v1", {}).get(
                "decision_quality_status",
                "",
            ),
        )
        path_line = build_operating_path_line(path_entry)
        audit.portfolio_catalog = {
            **path_entry,
            "operating_path_line": path_line,
            "operator_focus": catalog_entry.get("operator_focus", ""),
        }
        if audit.scorecard:
            audit.portfolio_catalog["scorecard"] = dict(audit.scorecard)

    audit_lookup = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
    for item in report.operator_queue:
        repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
        catalog_entry = audit_lookup.get(repo_name, {})
        if not catalog_entry:
            continue
        item["portfolio_catalog"] = dict(catalog_entry)
        item["operating_path"] = catalog_entry.get("operating_path", "")
        item["path_override"] = catalog_entry.get("path_override", "")
        item["path_confidence"] = catalog_entry.get("path_confidence", "")
        item["path_rationale"] = catalog_entry.get("path_rationale", "")
        item["operating_path_line"] = catalog_entry.get("operating_path_line", "")

    report.operating_paths_summary = build_operating_paths_summary(report.audits)
    return report


def _load_latest_report(output_dir: Path) -> tuple[Path | None, dict | None]:
    reports = sorted(
        output_dir.glob("audit-report-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None, None
    latest = reports[0]
    return latest, json.loads(latest.read_text())


def _latest_control_center_paths(output_dir: Path, username: str, generated_at: datetime) -> tuple[Path, Path]:
    stamp = _date_str(generated_at)
    return (
        output_dir / f"operator-control-center-{username}-{stamp}.json",
        output_dir / f"operator-control-center-{username}-{stamp}.md",
    )


def _latest_weekly_command_center_paths(output_dir: Path, username: str, generated_at: datetime) -> tuple[Path, Path]:
    stamp = _date_str(generated_at)
    return (
        output_dir / f"weekly-command-center-{username}-{stamp}.json",
        output_dir / f"weekly-command-center-{username}-{stamp}.md",
    )


def _latest_approval_center_paths(output_dir: Path, username: str, generated_at: datetime) -> tuple[Path, Path]:
    stamp = _date_str(generated_at)
    return (
        output_dir / f"approval-center-{username}-{stamp}.json",
        output_dir / f"approval-center-{username}-{stamp}.md",
    )


def _latest_approval_receipt_paths(output_dir: Path, username: str, generated_at: datetime) -> tuple[Path, Path]:
    stamp = _date_str(generated_at)
    return (
        output_dir / f"approval-receipt-{username}-{stamp}.json",
        output_dir / f"approval-receipt-{username}-{stamp}.md",
    )


def _latest_followup_review_receipt_paths(output_dir: Path, username: str, generated_at: datetime) -> tuple[Path, Path]:
    stamp = _date_str(generated_at)
    return (
        output_dir / f"approval-followup-receipt-{username}-{stamp}.json",
        output_dir / f"approval-followup-receipt-{username}-{stamp}.md",
    )


def _report_artifact_datetime(report_path: Path | None, fallback: datetime) -> datetime:
    if report_path:
        stem = report_path.stem
        if len(stem) >= 10:
            parsed = _parse_iso_dt(f"{stem[-10:]}T00:00:00+00:00")
            if parsed:
                return parsed
    return fallback


def _refresh_latest_report_state(
    output_dir: Path,
    args,
) -> tuple[Path, dict, AuditReport]:
    from src.diff import diff_reports
    from src.governance_activation import build_governance_summary
    from src.history import find_previous
    from src.operator_control_center import normalize_review_state

    report_path, report_data = _load_latest_report(output_dir)
    if not report_path or not report_data:
        raise FileNotFoundError("No existing audit report found in output directory")
    diff_dict = None
    previous_path = find_previous(report_path.name)
    if previous_path:
        diff_dict = diff_reports(
            previous_path,
            report_path,
            portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        ).to_dict()
    report = _report_from_dict(report_data)
    report_data = normalize_review_state(
        report.to_dict(),
        output_dir=output_dir,
        diff_data=diff_dict,
        portfolio_profile=args.portfolio_profile,
        collection_name=args.collection,
    )
    report_data["latest_report_path"] = str(report_path)
    report_data["governance_summary"] = build_governance_summary(report_data)
    report = _report_from_dict(report_data)
    report = _enrich_report_with_operator_state(
        report,
        output_dir=output_dir,
        diff_dict=diff_dict,
        triage_view=getattr(args, "triage_view", "all"),
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    return report_path, diff_dict or {}, report


def _write_approval_center_artifacts(
    report: AuditReport,
    output_dir: Path,
    *,
    approval_view: str,
) -> tuple[Path, Path, dict]:
    from src.approval_ledger import load_approval_ledger_bundle, render_approval_center_markdown

    report_data = report.to_dict()
    bundle = load_approval_ledger_bundle(
        output_dir,
        report_data,
        list(report.operator_queue or []),
        approval_view=approval_view,
    )
    report.approval_ledger = bundle["approval_ledger"]
    report.approval_workflow_summary = bundle["approval_workflow_summary"]
    report.next_approval_review = bundle["next_approval_review"]
    report.operator_queue = bundle.get("operator_queue", report.operator_queue)
    report.operator_summary = {
        **report.operator_summary,
        "approval_ledger": bundle["approval_ledger"],
        "approval_workflow_summary": bundle["approval_workflow_summary"],
        "next_approval_review": bundle["next_approval_review"],
        "top_ready_for_review_approvals": bundle["top_ready_for_review_approvals"],
        "top_needs_reapproval_approvals": bundle["top_needs_reapproval_approvals"],
        "top_overdue_approval_followups": bundle["top_overdue_approval_followups"],
        "top_due_soon_approval_followups": bundle["top_due_soon_approval_followups"],
        "top_approved_manual_approvals": bundle["top_approved_manual_approvals"],
        "top_blocked_approvals": bundle["top_blocked_approvals"],
    }
    generated_at = report.generated_at
    username = report.username
    json_path, md_path = _latest_approval_center_paths(output_dir, username, generated_at)
    payload = {
        "username": username,
        "generated_at": generated_at.isoformat(),
        "approval_view": approval_view,
        "approval_workflow_summary": bundle["approval_workflow_summary"],
        "next_approval_review": bundle["next_approval_review"],
        "approval_ledger": bundle["approval_ledger"],
        "top_ready_for_review_approvals": bundle["top_ready_for_review_approvals"],
        "top_needs_reapproval_approvals": bundle["top_needs_reapproval_approvals"],
        "top_overdue_approval_followups": bundle["top_overdue_approval_followups"],
        "top_due_soon_approval_followups": bundle["top_due_soon_approval_followups"],
        "top_approved_manual_approvals": bundle["top_approved_manual_approvals"],
        "top_blocked_approvals": bundle["top_blocked_approvals"],
        "operator_summary": report.operator_summary,
    }
    json_path.write_text(json.dumps(payload, indent=2))
    md_path.write_text(render_approval_center_markdown(payload))
    return json_path, md_path, payload


def _write_approval_receipt(
    output_dir: Path,
    username: str,
    *,
    generated_at: datetime,
    receipt: dict,
) -> tuple[Path, Path]:
    json_path, md_path = _latest_approval_receipt_paths(output_dir, username, generated_at)
    json_path.write_text(json.dumps(receipt, indent=2))
    lines = [
        f"# Approval Receipt: {username}",
        "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Subject: {receipt.get('label', 'Approval')}",
        f"- State: {receipt.get('approval_state', 'approved')}",
        f"- Reviewer: {receipt.get('approved_by', '') or 'local-operator'}",
        f"- Approved At: `{receipt.get('approved_at', '')}`",
        f"- Note: {receipt.get('approval_note', '') or '—'}",
        f"- Summary: {receipt.get('summary', 'Local approval captured.')}",
    ]
    if receipt.get("approval_command"):
        lines.append(f"- Approval Command: `{receipt.get('approval_command')}`")
    if receipt.get("manual_apply_command"):
        lines.append(f"- Manual Apply Command: `{receipt.get('manual_apply_command')}`")
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path


def _write_followup_review_receipt(
    output_dir: Path,
    username: str,
    *,
    generated_at: datetime,
    receipt: dict,
) -> tuple[Path, Path]:
    json_path, md_path = _latest_followup_review_receipt_paths(output_dir, username, generated_at)
    json_path.write_text(json.dumps(receipt, indent=2))
    lines = [
        f"# Approval Follow-Up Receipt: {username}",
        "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Subject: {receipt.get('label', 'Approval')}",
        f"- State: {receipt.get('approval_state', 'approved')} / {receipt.get('follow_up_state', 'not-applicable')}",
        f"- Reviewer: {receipt.get('reviewed_by', '') or 'local-operator'}",
        f"- Reviewed At: `{receipt.get('reviewed_at', '')}`",
        f"- Next Follow-Up Due: `{receipt.get('next_follow_up_due_at', '') or '—'}`",
        f"- Note: {receipt.get('review_note', '') or '—'}",
        f"- Summary: {receipt.get('summary', 'Local follow-up review captured.')}",
    ]
    if receipt.get("follow_up_command"):
        lines.append(f"- Follow-Up Command: `{receipt.get('follow_up_command')}`")
    if receipt.get("manual_apply_command"):
        lines.append(f"- Manual Apply Command: `{receipt.get('manual_apply_command')}`")
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path


def _refresh_shared_artifacts_from_report(
    report: AuditReport,
    output_dir: Path,
    args,
    *,
    diff_dict: dict | None = None,
) -> dict[str, Path]:
    from src.excel_export import export_excel
    from src.history import load_repo_score_history, load_trend_data
    from src.operator_control_center import (
        control_center_artifact_payload,
        render_control_center_markdown,
    )
    from src.review_pack import export_review_pack
    from src.warehouse import write_warehouse_snapshot
    from src.web_export import export_html_dashboard
    from src.weekly_command_center import (
        build_weekly_command_center_digest,
        load_latest_portfolio_truth,
        write_weekly_command_center_artifacts,
    )

    approval_json, approval_md, _payload = _write_approval_center_artifacts(
        report,
        output_dir,
        approval_view=getattr(args, "approval_view", "all"),
    )
    json_path = write_json_report(report, output_dir)
    write_markdown_report(report, output_dir, diff_data=diff_dict)
    write_pcc_export(report, output_dir)
    write_raw_metadata(report, output_dir)
    trend_data = load_trend_data()
    score_history = load_repo_score_history()
    export_excel(
        json_path,
        output_dir / f"audit-dashboard-{report.username}-{_date_str(report.generated_at)}.xlsx",
        trend_data=trend_data,
        diff_data=diff_dict,
        score_history=score_history,
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
        excel_mode=args.excel_mode,
    )
    export_review_pack(
        report.to_dict(),
        output_dir,
        diff_data=diff_dict,
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    export_html_dashboard(
        report.to_dict(),
        output_dir,
        trend_data,
        score_history,
        diff_data=diff_dict,
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    artifact_generated_at = _report_artifact_datetime(json_path, report.generated_at)
    control_json, control_md = _latest_control_center_paths(output_dir, report.username, artifact_generated_at)
    report.operator_summary["control_center_reference"] = str(control_json)
    snapshot = {"operator_summary": report.operator_summary, "operator_queue": report.operator_queue}
    portfolio_truth_path, portfolio_truth = load_latest_portfolio_truth(output_dir)
    weekly_digest = build_weekly_command_center_digest(
        report.to_dict(),
        snapshot,
        diff_data=diff_dict,
        portfolio_truth=portfolio_truth,
        portfolio_truth_reference=str(portfolio_truth_path) if portfolio_truth_path else "",
        control_center_reference=str(control_json),
        report_reference=str(json_path),
        generated_at=artifact_generated_at.isoformat(),
    )
    weekly_json, weekly_md = write_weekly_command_center_artifacts(
        output_dir,
        username=report.username,
        generated_at=artifact_generated_at,
        digest=weekly_digest,
    )
    control_payload = control_center_artifact_payload(report.to_dict(), snapshot)
    control_payload["weekly_command_center_digest_v1"] = weekly_digest
    control_payload["weekly_command_center_reference"] = {
        "json_path": str(weekly_json),
        "markdown_path": str(weekly_md),
    }
    control_json.write_text(json.dumps(control_payload, indent=2))
    control_md.write_text(
        render_control_center_markdown(snapshot, report.username, artifact_generated_at.isoformat())
    )
    write_warehouse_snapshot(report, output_dir, json_path)
    return {
        "json_path": json_path,
        "control_center_json": control_json,
        "control_center_md": control_md,
        "weekly_command_center_json": weekly_json,
        "weekly_command_center_md": weekly_md,
        "approval_center_json": approval_json,
        "approval_center_md": approval_md,
    }


def _doctor_next_step_hint(username: str) -> str:
    return (
        f"Next step: run `audit {username} --html` for the standard workbook, then "
        f"`audit {username} --control-center` for read-only weekly triage."
    )


def _control_center_next_step_hint() -> str:
    return (
        "Reading order: workbook Dashboard -> Run Changes -> Review Queue -> Repo Detail. "
        "Move into Action Sync only when the local weekly story is already settled."
    )


def _normal_audit_next_step_hint(username: str) -> str:
    return (
        f"Next step: open the standard workbook first, then run `audit {username} --control-center` "
        "for the read-only operator queue."
    )


def _print_control_center_summary(snapshot: dict) -> None:
    summary = snapshot.get("operator_summary", {})
    queue = snapshot.get("operator_queue", [])
    recent_changes = snapshot.get("operator_recent_changes", [])
    print(f"\nOperator Control Center\n  {summary.get('headline', 'No operator triage items are currently surfaced.')}")
    if summary.get("report_reference"):
        print(f"  Latest report: {summary['report_reference']}")
    if summary.get("source_run_id"):
        print(f"  Source run: {summary['source_run_id']}")
    if summary.get("next_recommended_run_mode"):
        print(
            "  Next recommended run: "
            f"{summary.get('next_recommended_run_mode', 'unknown')}"
            f" ({summary.get('watch_decision_summary', 'No watch decision summary available.')})"
        )
    if summary.get("watch_strategy"):
        print(f"  Watch strategy: {summary['watch_strategy']}")
    if summary.get("what_changed"):
        print(f"  What changed: {summary['what_changed']}")
    if summary.get("why_it_matters"):
        print(f"  Why it matters: {summary['why_it_matters']}")
    if summary.get("what_to_do_next"):
        print(f"  What to do next: {summary['what_to_do_next']}")
    if summary.get("trend_summary"):
        print(f"  Trend: {summary['trend_summary']}")
    if summary.get("accountability_summary"):
        print(f"  Accountability: {summary['accountability_summary']}")
    primary_target = summary.get("primary_target") or {}
    if primary_target:
        repo = f"{primary_target.get('repo')}: " if primary_target.get("repo") else ""
        print(f"  Primary target: {repo}{primary_target.get('title', 'Operator target')}")
    if summary.get("primary_target_reason"):
        print(f"  Why this is the top target: {summary['primary_target_reason']}")
    if summary.get("primary_target_done_criteria"):
        print(f"  What counts as done: {summary['primary_target_done_criteria']}")
    if summary.get("closure_guidance"):
        print(f"  Closure guidance: {summary['closure_guidance']}")
    if summary.get("primary_target_last_intervention"):
        intervention = summary.get("primary_target_last_intervention") or {}
        when = (intervention.get("recorded_at") or "")[:10]
        event_type = intervention.get("event_type", "recorded")
        outcome = intervention.get("outcome", event_type)
        print(f"  What we tried: {when} {event_type} ({outcome})".strip())
    if summary.get("primary_target_resolution_evidence"):
        print(f"  Resolution evidence: {summary['primary_target_resolution_evidence']}")
    if summary.get("primary_target_confidence_label"):
        print(
            "  Primary target confidence: "
            f"{summary.get('primary_target_confidence_label', 'low')} "
            f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
        )
    if summary.get("primary_target_confidence_reasons"):
        print(
            "  Confidence reasons: "
            + ", ".join(summary.get("primary_target_confidence_reasons") or [])
        )
    if summary.get("next_action_confidence_label"):
        print(
            "  Next action confidence: "
            f"{summary.get('next_action_confidence_label', 'low')} "
            f"({summary.get('next_action_confidence_score', 0.0):.2f})"
        )
    if summary.get("primary_target_trust_policy"):
        print(
            "  Trust policy: "
            f"{summary.get('primary_target_trust_policy', 'monitor')} "
            f"({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
        )
    if summary.get("adaptive_confidence_summary"):
        print(f"  Why this confidence is actionable: {summary['adaptive_confidence_summary']}")
    if summary.get("primary_target_exception_status") not in {None, "", "none"}:
        print(
            "  Trust policy exception: "
            f"{summary.get('primary_target_exception_status', 'none')} "
            f"({summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')})"
        )
    if summary.get("primary_target_exception_pattern_status") not in {None, "", "none"}:
        print(
            "  Exception pattern learning: "
            f"{summary.get('primary_target_exception_pattern_status', 'none')} "
            f"({summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')})"
        )
    if summary.get("primary_target_trust_recovery_status") not in {None, "", "none"}:
        print(
            "  Trust recovery: "
            f"{summary.get('primary_target_trust_recovery_status', 'none')} "
            f"({summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.')})"
        )
    if summary.get("primary_target_recovery_confidence_label"):
        print(
            "  Recovery confidence: "
            f"{summary.get('primary_target_recovery_confidence_label', 'low')} "
            f"({summary.get('primary_target_recovery_confidence_score', 0.0):.2f})"
        )
    if summary.get("recovery_confidence_summary"):
        print(f"  Recovery confidence summary: {summary['recovery_confidence_summary']}")
    if summary.get("primary_target_exception_retirement_status") not in {None, "", "none"}:
        print(
            "  Exception retirement: "
            f"{summary.get('primary_target_exception_retirement_status', 'none')} "
            f"({summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')})"
        )
    if summary.get("primary_target_policy_debt_status") not in {None, "", "none"}:
        print(
            "  Policy debt cleanup: "
            f"{summary.get('primary_target_policy_debt_status', 'none')} "
            f"({summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')})"
        )
    if summary.get("primary_target_class_normalization_status") not in {None, "", "none"}:
        print(
            "  Class-level trust normalization: "
            f"{summary.get('primary_target_class_normalization_status', 'none')} "
            f"({summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.')})"
        )
    if summary.get("primary_target_class_memory_freshness_status"):
        print(
            "  Class memory freshness: "
            f"{summary.get('primary_target_class_memory_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.')})"
        )
    if summary.get("primary_target_class_decay_status") is not None:
        print(
            "  Trust decay controls: "
            f"{summary.get('primary_target_class_decay_status', 'none')} "
            f"({summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.')})"
        )
    if summary.get("primary_target_transition_closure_confidence_label"):
        print(
            "  Transition closure confidence: "
            f"{summary.get('primary_target_transition_closure_confidence_label', 'low')} "
            f"({summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_transition_closure_likely_outcome', 'none')})"
        )
    if summary.get("transition_closure_confidence_summary"):
        print(f"  Transition closure summary: {summary['transition_closure_confidence_summary']}")
    if summary.get("primary_target_class_pending_debt_status") not in {None, "", "none"}:
        print(
            "  Class pending debt audit: "
            f"{summary.get('primary_target_class_pending_debt_status', 'none')} "
            f"({summary.get('primary_target_class_pending_debt_reason', 'No class pending-debt reason is recorded yet.')})"
        )
    if summary.get("class_pending_debt_summary"):
        print(f"  Class pending debt summary: {summary['class_pending_debt_summary']}")
    if summary.get("class_pending_resolution_summary"):
        print(f"  Class pending resolution summary: {summary['class_pending_resolution_summary']}")
    if summary.get("primary_target_pending_debt_freshness_status"):
        print(
            "  Pending debt freshness: "
            f"{summary.get('primary_target_pending_debt_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_pending_debt_freshness_reason', 'No pending-debt freshness reason is recorded yet.')})"
        )
    if summary.get("pending_debt_freshness_summary"):
        print(f"  Pending debt freshness summary: {summary['pending_debt_freshness_summary']}")
    if summary.get("pending_debt_decay_summary"):
        print(f"  Pending debt decay summary: {summary['pending_debt_decay_summary']}")
    if summary.get("primary_target_closure_forecast_reweight_direction"):
        print(
            "  Closure forecast reweighting: "
            f"{summary.get('primary_target_closure_forecast_reweight_direction', 'neutral')} "
            f"({summary.get('primary_target_closure_forecast_reweight_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reweighting_summary"):
        print(f"  Closure forecast reweighting summary: {summary['closure_forecast_reweighting_summary']}")
    if summary.get("primary_target_closure_forecast_momentum_status"):
        print(
            "  Closure forecast momentum: "
            f"{summary.get('primary_target_closure_forecast_momentum_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_momentum_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_momentum_summary"):
        print(f"  Closure forecast momentum summary: {summary['closure_forecast_momentum_summary']}")
    if summary.get("primary_target_closure_forecast_freshness_status"):
        print(
            "  Closure forecast freshness: "
            f"{summary.get('primary_target_closure_forecast_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_freshness_summary"):
        print(f"  Closure forecast freshness summary: {summary['closure_forecast_freshness_summary']}")
    if summary.get("primary_target_closure_forecast_stability_status"):
        print(
            "  Closure forecast hysteresis: "
            f"{summary.get('primary_target_closure_forecast_stability_status', 'watch')} "
            f"({summary.get('primary_target_closure_forecast_hysteresis_status', 'none')}: "
            f"{summary.get('primary_target_closure_forecast_hysteresis_reason', 'No closure-forecast hysteresis reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_hysteresis_summary"):
        print(f"  Closure forecast hysteresis summary: {summary['closure_forecast_hysteresis_summary']}")
    if summary.get("primary_target_closure_forecast_decay_status") not in {None, "", "none"}:
        print(
            "  Hysteresis decay controls: "
            f"{summary.get('primary_target_closure_forecast_decay_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_decay_summary"):
        print(f"  Closure forecast decay summary: {summary['closure_forecast_decay_summary']}")
    if summary.get("primary_target_closure_forecast_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Closure forecast refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_refresh_recovery_summary"):
        print(f"  Closure forecast refresh recovery summary: {summary['closure_forecast_refresh_recovery_summary']}")
    if summary.get("primary_target_closure_forecast_reacquisition_status") not in {None, "", "none"}:
        print(
            "  Reacquisition controls: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reacquisition_summary"):
        print(f"  Closure forecast reacquisition summary: {summary['closure_forecast_reacquisition_summary']}")
    if summary.get("primary_target_closure_forecast_reacquisition_persistence_status") not in {None, "", "none"}:
        print(
            "  Reacquisition persistence: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reacquisition_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reacquisition_persistence_summary"):
        print(f"  Reacquisition persistence summary: {summary['closure_forecast_reacquisition_persistence_summary']}")
    if summary.get("primary_target_closure_forecast_recovery_churn_status") not in {None, "", "none"}:
        print(
            "  Recovery churn controls: "
            f"{summary.get('primary_target_closure_forecast_recovery_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_recovery_churn_summary"):
        print(f"  Recovery churn summary: {summary['closure_forecast_recovery_churn_summary']}")
    if summary.get("primary_target_closure_forecast_reacquisition_freshness_status") not in {None, "", "insufficient-data"}:
        print(
            "  Reacquisition freshness: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_freshness_reason', 'No reacquisition-freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reacquisition_freshness_summary"):
        print(f"  Reacquisition freshness summary: {summary['closure_forecast_reacquisition_freshness_summary']}")
    if summary.get("primary_target_closure_forecast_persistence_reset_status") not in {None, "", "none"}:
        print(
            "  Persistence reset controls: "
            f"{summary.get('primary_target_closure_forecast_persistence_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_persistence_reset_reason', 'No persistence-reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_persistence_reset_summary"):
        print(f"  Persistence reset summary: {summary['closure_forecast_persistence_reset_summary']}")
    if summary.get("primary_target_closure_forecast_reset_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_refresh_recovery_summary"):
        print(f"  Reset refresh recovery summary: {summary['closure_forecast_reset_refresh_recovery_summary']}")
    if summary.get("primary_target_closure_forecast_reset_reentry_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_reason', 'No reset re-entry reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_summary"):
        print(f"  Reset re-entry summary: {summary['closure_forecast_reset_reentry_summary']}")
    if summary.get("primary_target_closure_forecast_reset_reentry_persistence_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_persistence_summary"):
        print(
            "  Reset re-entry persistence summary: "
            f"{summary['closure_forecast_reset_reentry_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_churn_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_churn_reason', 'No reset re-entry churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_churn_summary"):
        print(
            "  Reset re-entry churn summary: "
            f"{summary['closure_forecast_reset_reentry_churn_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_freshness_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_freshness_reason', 'No reset re-entry freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_freshness_summary"):
        print(
            "  Reset re-entry freshness summary: "
            f"{summary['closure_forecast_reset_reentry_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_reset_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_reset_reason', 'No reset re-entry reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_reset_summary"):
        print(
            "  Reset re-entry reset summary: "
            f"{summary['closure_forecast_reset_reentry_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_reentry_refresh_recovery_summary"):
        print(
            "  Reset re-entry refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reason', 'No reset re-entry rebuild reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_summary"):
        print(
            "  Reset re-entry rebuild summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_freshness_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason', 'No reset re-entry rebuild freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_freshness_summary"):
        print(
            "  Reset re-entry rebuild freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reset_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_reason', 'No reset re-entry rebuild reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reset_summary"):
        print(
            "  Reset re-entry rebuild reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_refresh_recovery_summary"):
        print(
            "  Reset re-entry rebuild refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason', 'No reset re-entry rebuild re-entry reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_summary"):
        print(
            "  Reset re-entry rebuild re-entry summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_summary"):
        print(
            "  Reset re-entry rebuild re-entry persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason', 'No reset re-entry rebuild re-entry churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_churn_summary"):
        print(
            "  Reset re-entry rebuild re-entry churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_churn_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason', 'No reset re-entry rebuild re-entry freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_summary"):
        print(
            "  Reset re-entry rebuild re-entry freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason', 'No reset re-entry rebuild re-entry reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_reset_summary"):
        print(
            "  Reset re-entry rebuild re-entry reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary', 'No reset re-entry rebuild re-entry refresh recovery summary is recorded yet.')})"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason', 'No reset re-entry rebuild re-entry restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status") not in {None, "", "insufficient-data"}:
        print(
            "  Reset re-entry rebuild re-entry restore freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason', 'No reset re-entry rebuild re-entry restore freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason', 'No reset re-entry rebuild re-entry restore reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason', 'No reset re-entry rebuild re-entry restore re-restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-restore churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status") not in {None, "", "insufficient-data"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-restore freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-restore reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-restore churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_persistence_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_persistence_summary"):
        print(
            "  Reset re-entry rebuild persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_churn_status") not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_reason', 'No reset re-entry rebuild churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_churn_summary"):
        print(
            "  Reset re-entry rebuild churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_churn_summary']}"
        )
    if summary.get("recommendation_drift_status"):
        print(
            "  Recommendation drift: "
            f"{summary.get('recommendation_drift_status', 'stable')} "
            f"({summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')})"
        )
    if summary.get("exception_pattern_summary"):
        print(f"  Exception pattern summary: {summary['exception_pattern_summary']}")
    if summary.get("exception_retirement_summary"):
        print(f"  Exception retirement summary: {summary['exception_retirement_summary']}")
    if summary.get("policy_debt_summary"):
        print(f"  Policy debt summary: {summary['policy_debt_summary']}")
    if summary.get("trust_normalization_summary"):
        print(f"  Trust normalization summary: {summary['trust_normalization_summary']}")
    if summary.get("class_memory_summary"):
        print(f"  Class memory summary: {summary['class_memory_summary']}")
    if summary.get("class_decay_summary"):
        print(f"  Class decay summary: {summary['class_decay_summary']}")
    if summary.get("recommendation_quality_summary"):
        print(f"  Recommendation quality: {summary['recommendation_quality_summary']}")
    if summary.get("confidence_validation_status"):
        print(
            "  Confidence validation: "
            f"{summary.get('confidence_validation_status', 'insufficient-data')} "
            f"({summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')})"
        )
    if summary.get("recent_validation_outcomes"):
        recent_bits = []
        for item in (summary.get("recent_validation_outcomes") or [])[:3]:
            recent_bits.append(
                f"{item.get('target_label', 'Operator target')} "
                f"[{item.get('confidence_label', 'low')}] -> {str(item.get('outcome', 'unresolved')).replace('_', ' ')}"
            )
        print("  Recent confidence outcomes: " + "; ".join(recent_bits))
    if summary.get("follow_through_summary"):
        print(f"  Follow-through: {summary['follow_through_summary']}")
    lane_labels = [
        ("blocked", "Blocked"),
        ("urgent", "Needs Attention Now"),
        ("ready", "Ready for Manual Action"),
        ("deferred", "Safe to Defer"),
    ]
    for lane, label in lane_labels:
        items = [item for item in queue if item.get("lane") == lane]
        if not items:
            continue
        print(f"\n{label}")
        for item in items[:8]:
            repo = f"{item['repo']}: " if item.get("repo") else ""
            print(f"  - {repo}{item.get('title', 'Triage item')}")
            print(f"    {item.get('summary', '')}")
            print(f"    Why: {item.get('lane_reason', item.get('lane_label', ''))}")
            print(f"    Next: {item.get('recommended_action', '')}")
            if item.get("catalog_line"):
                print(f"    Catalog: {item.get('catalog_line')}")
            if item.get("intent_alignment"):
                print(
                    "    Intent alignment: "
                    f"{item.get('intent_alignment')} ({item.get('intent_alignment_reason', 'No alignment reason is recorded yet.')})"
                )
    if recent_changes:
        print("\nRecently Changed")
        for item in recent_changes[:5]:
            subject = item.get("repo") or item.get("repo_full_name") or item.get("item_id") or "portfolio"
            print(f"  - {item.get('generated_at', '')[:10]} {subject}: {item.get('summary', item.get('kind', 'change'))}")


def _fetch_repo_metadata(args, client: GitHubClient) -> tuple[list[RepoMetadata], list[dict]]:
    if args.graphql and args.token:
        from src.graphql_client import bulk_fetch_repos

        print_info("Using GraphQL bulk fetch...")
        raw_repos = bulk_fetch_repos(args.username, args.token)
        all_repos: list[RepoMetadata] = []
        errors: list[dict] = []
        for repo_data in raw_repos:
            try:
                langs = repo_data.pop("_languages", {})
                repo_data.pop("_releases", None)
                meta = RepoMetadata.from_api_response(repo_data, languages=langs)
                all_repos.append(meta)
            except Exception as exc:
                errors.append({"repo": repo_data.get("full_name", "?"), "error": str(exc)})
        print_info(f"GraphQL: {len(all_repos)} repos fetched")
        return all_repos, errors

    return client.get_repo_metadata(args.username)


def _print_filter_summary(all_repos: list[RepoMetadata], repos: list[RepoMetadata], args) -> None:
    forks_excluded = sum(1 for r in all_repos if r.fork) if args.skip_forks else 0
    archived_excluded = sum(1 for r in all_repos if r.archived) if args.skip_archived else 0
    skipped = len(all_repos) - len(repos)
    if skipped:
        parts = []
        if forks_excluded:
            parts.append(f"{forks_excluded} forks")
        if archived_excluded:
            parts.append(f"{archived_excluded} archived")
        print_info(f"Filtered out {skipped} repos ({', '.join(parts) or 'forks/archived'})")


def _compute_portfolio_lang_freq(repos: list[RepoMetadata]) -> dict[str, float]:
    lang_counts = Counter(repo.language for repo in repos if repo.language)
    return {lang: count / len(repos) for lang, count in lang_counts.items()} if repos else {}


def _portfolio_lang_freq_for_filtered_baseline(repos: list[RepoMetadata]) -> dict[str, float]:
    """Compute novelty baseline from the full filtered portfolio, never only the rerun subset."""
    return _compute_portfolio_lang_freq(repos)


def _select_target_repos(target_names: list[str], repos: list[RepoMetadata]) -> tuple[list[RepoMetadata], list[str]]:
    exact = {repo.name: repo for repo in repos}
    lower = {repo.name.lower(): repo for repo in repos}
    selected: list[RepoMetadata] = []
    missing: list[str] = []

    for name in target_names:
        repo = exact.get(name) or lower.get(name.lower())
        if repo:
            selected.append(repo)
        else:
            missing.append(name)

    return selected, missing


# ── Core analysis pipeline ────────────────────────────────────────────
def _analyze_repos(
    repos: list[RepoMetadata],
    *,
    args,
    client: GitHubClient,
    portfolio_lang_freq: dict[str, float],
    custom_weights: dict[str, float] | None,
    runtime_stats: dict | None = None,
) -> list[RepoAudit]:
    from src.analyzers import load_custom_analyzers

    if args.skip_clone:
        print_warning("Audit modes that score repos do not support --skip-clone.")
        return []

    extra_analyzers = []
    if getattr(args, "analyzers_dir", None):
        extra_analyzers = load_custom_analyzers(Path(args.analyzers_dir))
        if extra_analyzers:
            print_info(f"Loaded {len(extra_analyzers)} custom analyzer(s) from {args.analyzers_dir}")

    audits: list[RepoAudit] = []

    def _analyze_one(repo_meta: RepoMetadata, repo_path: Path) -> RepoAudit:
        worker_client = GitHubClient(token=client.token, cache=client.cache)
        results = run_all_analyzers(repo_path, repo_meta, worker_client, extra_analyzers=extra_analyzers)
        return score_repo(
            repo_meta,
            results,
            repo_path=repo_path,
            portfolio_lang_freq=portfolio_lang_freq,
            custom_weights=custom_weights,
            github_client=worker_client,
            scorecard_enabled=args.scorecard,
            security_offline=args.security_offline,
        )

    progress = create_progress()
    clone_start = perf_counter()
    with clone_workspace(
        repos,
        token=args.token,
        on_progress=lambda i, t, n: None,
        on_error=lambda n, m: print_warning(f"Failed to clone {n}"),
    ) as cloned:
        clone_seconds = perf_counter() - clone_start
        if runtime_stats is not None:
            runtime_stats["clone_fetch_seconds"] = round(clone_seconds, 3)
        print_info(f"Cloned {len(cloned)}/{len(repos)} repos. Analyzing...")
        analyzable = [(index, repo_meta, cloned.get(repo_meta.name)) for index, repo_meta in enumerate(repos)]
        analyzable = [(index, repo_meta, repo_path) for index, repo_meta, repo_path in analyzable if repo_path]
        workers = min(ANALYSIS_WORKERS, max(1, len(analyzable)))
        analyze_start = perf_counter()
        if progress:
            with progress:
                task = progress.add_task("Analyzing", total=len(repos))
                completed: dict[int, RepoAudit] = {}
                skipped = len(repos) - len(analyzable)
                for _ in range(skipped):
                    progress.advance(task)
                if workers == 1:
                    for index, repo_meta, repo_path in analyzable:
                        progress.update(task, description=f"Analyzing {repo_meta.name}")
                        completed[index] = _analyze_one(repo_meta, repo_path)
                        if args.verbose:
                            _print_verbose(completed[index])
                        progress.advance(task)
                else:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        futures = {
                            executor.submit(_analyze_one, repo_meta, repo_path): (index, repo_meta.name)
                            for index, repo_meta, repo_path in analyzable
                        }
                        for future in as_completed(futures):
                            index, repo_name = futures[future]
                            progress.update(task, description=f"Analyzing {repo_name}")
                            completed[index] = future.result()
                            if args.verbose:
                                _print_verbose(completed[index])
                            progress.advance(task)
                audits.extend(completed[index] for index in sorted(completed))
        else:
            completed: dict[int, RepoAudit] = {}
            if workers == 1:
                for index, repo_meta, repo_path in analyzable:
                    print(f"  [{index + 1}/{len(repos)}] Analyzing {repo_meta.name}...", file=sys.stderr)
                    completed[index] = _analyze_one(repo_meta, repo_path)
                    if args.verbose:
                        _print_verbose(completed[index])
            else:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {
                        executor.submit(_analyze_one, repo_meta, repo_path): (index, repo_meta.name)
                        for index, repo_meta, repo_path in analyzable
                    }
                    finished = 0
                    for future in as_completed(futures):
                        index, repo_name = futures[future]
                        finished += 1
                        print(f"  [{finished}/{len(analyzable)}] Analyzing {repo_name}...", file=sys.stderr)
                        completed[index] = future.result()
                        if args.verbose:
                            _print_verbose(completed[index])
            audits.extend(completed[index] for index in sorted(completed))
        if runtime_stats is not None:
            runtime_stats["analyzer_seconds"] = round(perf_counter() - analyze_start, 3)

    print_info("Clones cleaned up")
    return audits


def _apply_requested_reconciliation(report: AuditReport, args, audits: list[RepoAudit]) -> None:
    if args.registry:
        from src.registry_parser import parse_registry, reconcile, sync_new_repos

        registry = parse_registry(args.registry)
        report.reconciliation = reconcile(registry, audits)
        print_info(
            f"Registry: {report.reconciliation.registry_total} projects, "
            f"{len(report.reconciliation.matched)} matched"
        )
        if args.sync_registry and report.reconciliation.on_github_not_registry:
            added = sync_new_repos(
                args.registry,
                report.reconciliation.on_github_not_registry,
                audits,
            )
            if added:
                print_info(
                    f"Synced {len(added)} repos to registry: {', '.join(added[:5])}"
                    + (f"... (+{len(added) - 5})" if len(added) > 5 else "")
                )
        return

    if args.notion_registry:
        from src.notion_registry import load_notion_registry
        from src.registry_parser import reconcile

        notion_projects = load_notion_registry(Path("config"))
        if notion_projects:
            report.reconciliation = reconcile(notion_projects, audits)
            print_info(
                f"Notion registry: {len(notion_projects)} projects, "
                f"{len(report.reconciliation.matched)} matched"
            )


def _run_portfolio_truth_mode(args) -> None:
    from src.portfolio_truth_publish import publish_portfolio_truth

    output_dir = Path(args.output_dir)
    workspace_root = Path(args.workspace_root)
    registry_output = Path(args.registry_output) if args.registry_output else workspace_root / "project-registry.md"
    portfolio_report_output = (
        Path(args.portfolio_report_output)
        if args.portfolio_report_output
        else workspace_root / "PORTFOLIO-AUDIT-REPORT.md"
    )
    legacy_registry_path = Path(args.registry) if args.registry else registry_output

    result = publish_portfolio_truth(
        workspace_root=workspace_root,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
        catalog_path=Path(args.catalog) if args.catalog else None,
        legacy_registry_path=legacy_registry_path,
        include_notion=True,
    )
    print_info(f"Portfolio truth snapshot: {result.latest_path}")
    print_info(f"Portfolio truth history snapshot: {result.snapshot_path}")
    print_info(f"Project registry compatibility output: {result.registry_output}")
    print_info(f"Portfolio audit compatibility output: {result.portfolio_report_output}")
    print_info(
        f"Portfolio truth generated for {result.project_count} projects "
        f"(registry {'updated' if result.registry_changed else 'unchanged'}, "
        f"report {'updated' if result.report_changed else 'unchanged'})"
    )


def _run_portfolio_context_recovery_mode(args) -> None:
    from src.portfolio_context_recovery import (
        apply_context_recovery_plan,
        build_context_recovery_plan,
        write_context_recovery_plan_artifacts,
    )
    from src.portfolio_truth_publish import publish_portfolio_truth
    from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot

    output_dir = Path(args.output_dir)
    workspace_root = Path(args.workspace_root)
    registry_output = Path(args.registry_output) if args.registry_output else workspace_root / "project-registry.md"
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
    plan = build_context_recovery_plan(build_result.snapshot, workspace_root=workspace_root)
    plan_json, plan_markdown = write_context_recovery_plan_artifacts(plan, output_dir=output_dir)
    print_info(f"Context recovery plan JSON: {plan_json}")
    print_info(f"Context recovery plan Markdown: {plan_markdown}")
    eligible_count = sum(1 for project in plan.projects if project.status == "eligible")
    skipped_count = sum(1 for project in plan.projects if project.status == "skipped")
    excluded_count = sum(1 for project in plan.projects if project.status == "excluded")
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
        raise SystemExit(
            "Context recovery failed for: " + ", ".join(apply_result.failed_projects)
        )

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


def _apply_governance_view_filter(report: AuditReport, governance_view: str) -> None:
    if not isinstance(report.governance_preview, dict):
        report.governance_preview = {}
    report.governance_preview["selected_view"] = governance_view
    if governance_view == "all":
        return

    preview_actions = report.governance_preview.get("actions", []) if isinstance(report.governance_preview, dict) else []
    result_rows = report.governance_results.get("results", []) if isinstance(report.governance_results, dict) else []
    drift_rows = report.governance_drift if isinstance(report.governance_drift, list) else []

    if governance_view == "ready":
        filtered_preview = [item for item in preview_actions if item.get("applyable")]
        report.governance_preview = {
            **report.governance_preview,
            "actions": filtered_preview,
            "applyable_count": len(filtered_preview),
            "action_count": len(filtered_preview),
        }
        return

    if governance_view == "drifted":
        report.governance_drift = drift_rows
        report.governance_results = {
            **report.governance_results,
            "results": [item for item in result_rows if item.get("status") == "drifted"],
        }
        return

    if governance_view == "approved":
        if not report.governance_approval:
            report.governance_preview = {**report.governance_preview, "actions": []}
            report.governance_results = {**report.governance_results, "results": []}
        return

    if governance_view == "applied":
        report.governance_results = {
            **report.governance_results,
            "results": [item for item in result_rows if item.get("status") == "applied"],
        }


def _apply_ops_writeback(report: AuditReport, args, client: GitHubClient | None, output_dir: Path) -> None:
    if not args.campaign:
        return

    github_projects_config = None
    operator_context: dict[str, dict] = {}
    if getattr(args, "github_projects", False):
        from src.github_projects import load_github_projects_config, operator_context_by_repo
        from src.operator_control_center import build_operator_snapshot, normalize_review_state

        github_projects_config = load_github_projects_config(
            Path(args.github_projects_config) if getattr(args, "github_projects_config", None) else None
        )
        normalized = normalize_review_state(
            report.to_dict(),
            output_dir=output_dir,
            diff_data=None,
            portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        )
        operator_snapshot = build_operator_snapshot(
            normalized,
            output_dir=output_dir,
            triage_view="all",
        )
        operator_context = operator_context_by_repo(operator_snapshot.get("operator_queue", []))

    from src.notion_sync import sync_campaign_actions
    from src.ops_writeback import (
        apply_github_writeback,
        build_action_runs,
        build_campaign_bundle,
        build_campaign_run,
        build_rollback_preview,
        build_writeback_preview,
        summarize_writeback_results,
    )
    from src.warehouse import load_campaign_history, load_latest_campaign_state

    previous_state = load_latest_campaign_state(output_dir, args.campaign)
    campaign_summary, actions = build_campaign_bundle(
        report.to_dict(),
        campaign_type=args.campaign,
        portfolio_profile=args.portfolio_profile,
        collection_name=args.collection,
        max_actions=args.max_actions,
        writeback_target=args.writeback_target,
    )
    campaign_summary["sync_mode"] = args.campaign_sync_mode
    report.campaign_summary = campaign_summary
    report.writeback_preview = build_writeback_preview(
        campaign_summary,
        actions,
        writeback_target=args.writeback_target,
        apply=args.writeback_apply,
        previous_state=previous_state,
        sync_mode=args.campaign_sync_mode,
        github_projects_config=github_projects_config,
        operator_context=operator_context,
    )

    results: list[dict] = []
    external_refs: dict[str, dict] = {}
    managed_state_drift: list[dict] = []
    if args.writeback_apply and args.writeback_target:
        if args.writeback_target in {"github", "all"} and client is not None:
            github_results, github_refs, github_drift, _github_closure_events = apply_github_writeback(
                client,
                actions,
                previous_state=previous_state,
                sync_mode=args.campaign_sync_mode,
                campaign_summary=campaign_summary,
                github_projects_config=github_projects_config,
                operator_context=operator_context,
            )
            results.extend(github_results)
            external_refs.update(github_refs)
            managed_state_drift.extend(github_drift)
        if args.writeback_target in {"notion", "all"}:
            notion_results, notion_refs, notion_drift = sync_campaign_actions(
                actions,
                campaign_summary,
                config_dir=Path("config"),
                apply=True,
                previous_state=previous_state,
                sync_mode=args.campaign_sync_mode,
            )
            results.extend(notion_results)
            external_refs.update(notion_refs)
            managed_state_drift.extend(notion_drift)

    report.writeback_results = summarize_writeback_results(
        results,
        args.writeback_target,
        args.writeback_apply,
    )
    report.writeback_results["campaign_run"] = build_campaign_run(
        campaign_summary,
        actions,
        writeback_target=args.writeback_target,
        apply=args.writeback_apply,
        sync_mode=args.campaign_sync_mode,
    )
    report.action_runs = build_action_runs(
        actions,
        results,
        args.writeback_target,
        args.writeback_apply,
        previous_state=previous_state,
        sync_mode=args.campaign_sync_mode,
    )
    report.external_refs = external_refs
    report.managed_state_drift = managed_state_drift
    report.rollback_preview = build_rollback_preview(results)
    historical_entries = load_campaign_history(output_dir, args.campaign, limit=20)
    report.campaign_history = report.action_runs + historical_entries[:20]


def _enrich_report_with_operator_state(
    report: AuditReport,
    *,
    output_dir: Path,
    diff_dict: dict | None,
    triage_view: str,
    portfolio_profile: str,
    collection: str | None,
) -> AuditReport:
    from src.governance_activation import build_governance_summary
    from src.operator_control_center import build_operator_snapshot, normalize_review_state

    normalized = normalize_review_state(
        report.to_dict(),
        output_dir=output_dir,
        diff_data=diff_dict,
        portfolio_profile=portfolio_profile,
        collection_name=collection,
    )
    normalized["governance_summary"] = build_governance_summary(normalized)
    snapshot = build_operator_snapshot(
        normalized,
        output_dir=output_dir,
        triage_view=triage_view,
    )
    report.governance_summary = normalized.get("governance_summary", {})
    report.review_summary = normalized.get("review_summary", {})
    report.review_alerts = normalized.get("review_alerts", [])
    report.material_changes = normalized.get("material_changes", [])
    report.review_targets = normalized.get("review_targets", [])
    report.review_history = normalized.get("review_history", [])
    report.watch_state = normalized.get("watch_state", {})
    report.operator_summary = snapshot.get("operator_summary", {})
    report.operator_queue = snapshot.get("operator_queue", [])
    report.portfolio_outcomes_summary = snapshot.get("portfolio_outcomes_summary", {})
    report.operator_effectiveness_summary = snapshot.get("operator_effectiveness_summary", {})
    report.high_pressure_queue_history = snapshot.get("high_pressure_queue_history", [])
    report.campaign_readiness_summary = snapshot.get("campaign_readiness_summary", {})
    report.action_sync_summary = snapshot.get("action_sync_summary", {})
    report.next_action_sync_step = snapshot.get("next_action_sync_step", "")
    report.action_sync_packets = snapshot.get("action_sync_packets", [])
    report.apply_readiness_summary = snapshot.get("apply_readiness_summary", {})
    report.next_apply_candidate = snapshot.get("next_apply_candidate", {})
    report.action_sync_outcomes = snapshot.get("action_sync_outcomes", [])
    report.campaign_outcomes_summary = snapshot.get("campaign_outcomes_summary", {})
    report.next_monitoring_step = snapshot.get("next_monitoring_step", {})
    report.action_sync_tuning = snapshot.get("action_sync_tuning", [])
    report.campaign_tuning_summary = snapshot.get("campaign_tuning_summary", {})
    report.next_tuned_campaign = snapshot.get("next_tuned_campaign", {})
    report.historical_portfolio_intelligence = snapshot.get("historical_portfolio_intelligence", [])
    report.intervention_ledger_summary = snapshot.get("intervention_ledger_summary", {})
    report.next_historical_focus = snapshot.get("next_historical_focus", {})
    report.action_sync_automation = snapshot.get("action_sync_automation", [])
    report.automation_guidance_summary = snapshot.get("automation_guidance_summary", {})
    report.next_safe_automation_step = snapshot.get("next_safe_automation_step", {})
    report.approval_ledger = snapshot.get("approval_ledger", [])
    report.approval_workflow_summary = snapshot.get("approval_workflow_summary", {})
    report.next_approval_review = snapshot.get("next_approval_review", {})
    return report


# ── Report output orchestration ───────────────────────────────────────
def _write_report_outputs(
    report: AuditReport,
    args,
    output_dir: Path,
    *,
    client: GitHubClient | None = None,
    cache: ResponseCache | None = None,
    json_path: Path | None = None,
    write_json: bool = True,
    archive: bool = True,
    save_fingerprint_data: bool = True,
    diff_source: Path | None = None,
) -> dict[str, object]:
    from src.diff import diff_reports, format_diff_markdown
    from src.excel_export import export_excel
    from src.history import (
        archive_report,
        find_previous,
        load_repo_score_history,
        load_trend_data,
        save_fingerprints,
    )
    from src.warehouse import write_warehouse_snapshot

    output_start = perf_counter()
    _apply_ops_writeback(report, args, client, output_dir)
    _apply_governance_view_filter(report, args.governance_view)
    if write_json:
        json_path = write_json_report(report, output_dir)
    elif json_path is None:
        raise ValueError("json_path is required when write_json is False")

    if diff_source is None and write_json:
        diff_source = find_previous(json_path.name)

    diff_dict = None
    if diff_source:
        diff = diff_reports(
            diff_source,
            json_path,
            portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        )
        diff_dict = diff.to_dict()
        diff_md_path = output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.md"
        diff_md_path.write_text(format_diff_markdown(diff))
        diff_json_path = output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.json"
        diff_json_path.write_text(json.dumps(diff_dict, indent=2))
        print_info(
            f"Diff: {len(diff.tier_changes)} tier changes, "
            f"{len([c for c in diff.score_changes if abs(c['delta']) > 0.05])} significant score changes"
        )

    report = _enrich_report_with_operator_state(
        report,
        output_dir=output_dir,
        diff_dict=diff_dict,
        triage_view=getattr(args, "triage_view", "all"),
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    report = _apply_portfolio_catalog(report, args)
    report = _apply_scorecards(report, args)
    report = _apply_operating_paths(report)
    report.run_change_summary = build_run_change_summary(diff_dict)
    report.run_change_counts = build_run_change_counts(diff_dict)
    report_data = report.to_dict()
    if write_json:
        json_path = write_json_report(report, output_dir)

    trend_data = load_trend_data()
    score_history = load_repo_score_history()
    workbook_start = perf_counter()
    excel_path = export_excel(
        json_path,
        output_dir / f"audit-dashboard-{report.username}-{_date_str(report.generated_at)}.xlsx",
        trend_data=trend_data,
        diff_data=diff_dict,
        score_history=score_history,
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
        excel_mode=args.excel_mode,
    )
    report.runtime_breakdown["workbook_build_seconds"] = round(perf_counter() - workbook_start, 3)
    md_path = write_markdown_report(report, output_dir, diff_data=diff_dict)
    pcc_path = write_pcc_export(report, output_dir)
    raw_path = write_raw_metadata(report, output_dir)
    warehouse_path = write_warehouse_snapshot(report, output_dir, json_path)

    if archive and write_json:
        archive_report(json_path)
    if save_fingerprint_data:
        save_fingerprints(report_data["audits"], output_dir / ".audit-fingerprints.json")
    report.runtime_breakdown["report_output_seconds"] = round(perf_counter() - output_start, 3)

    badge_info = ""
    if args.badges:
        from src.badge_export import _write_badges_markdown, export_badges, upload_badge_gist

        badge_result = export_badges(report_data, output_dir)
        badge_info = f"\n    {badge_result['badges_md']} ({badge_result['files_written']} badge files)"
        if args.upload_badges:
            gist_urls = upload_badge_gist(output_dir / "badges", report.username)
            if gist_urls:
                _write_badges_markdown(report_data, output_dir / "badges", gist_urls)

    notion_info = ""
    if args.notion:
        from src.notion_client import get_notion_token, load_notion_config
        from src.notion_export import _load_project_map, export_notion_events
        from src.notion_sync import (
            check_recommendation_followup,
            create_audit_action_requests,
            create_audit_history_entry,
            create_recommendation_run,
            patch_project_completeness_cards,
            patch_weekly_review,
            sync_notion_events,
        )

        notion_result = export_notion_events(report_data, output_dir)
        notion_info = (
            f"\n    {notion_result['events_path']} "
            f"({notion_result['event_count']} events, {len(notion_result['unmapped'])} unmapped)"
        )
        if args.notion_sync:
            sync_notion_events(notion_result["events_path"], Path("config"))
            sync_token = get_notion_token()
            sync_config = load_notion_config(Path("config"))
            if sync_token and sync_config:
                from src.notion_dashboard import create_notion_dashboard
                from src.quick_wins import find_quick_wins

                quick_wins = find_quick_wins(report.audits)
                project_map = _load_project_map(Path("config"))
                create_recommendation_run(report_data, quick_wins, sync_token, sync_config)
                create_audit_action_requests(
                    report_data.get("audits", []), project_map, sync_token, sync_config,
                )
                patch_weekly_review(report_data, diff_dict, quick_wins, sync_token, sync_config)
                create_audit_history_entry(report_data, sync_token, sync_config)
                patch_project_completeness_cards(
                    report_data.get("audits", []), project_map, sync_token, sync_config,
                )
                check_recommendation_followup(report_data, sync_token, sync_config)
                create_notion_dashboard(report_data, sync_token, sync_config)

    readme_info = ""
    if args.portfolio_readme:
        from src.portfolio_readme import export_portfolio_readme

        readme_result = export_portfolio_readme(report_data, output_dir)
        readme_info = f"\n    {readme_result['readme_path']}"

    suggestions_info = ""
    if args.readme_suggestions:
        from src.readme_suggestions import generate_readme_suggestions

        sug_result = generate_readme_suggestions(report_data, output_dir)
        suggestions_info = f"\n    {sug_result['suggestions_path']} ({sug_result['total_suggestions']} suggestions)"

    html_info = ""
    if args.html:
        from src.web_export import export_html_dashboard

        html_result = export_html_dashboard(
            report_data,
            output_dir,
            trend_data,
            score_history,
            diff_data=diff_dict,
            portfolio_profile=args.portfolio_profile,
            collection=args.collection,
        )
        html_info = f"\n    {html_result['html_path']}"

    pdf_info = ""
    if args.pdf:
        from src.pdf_export import export_pdf_report

        pdf_path = export_pdf_report(report_data, output_dir)
        if pdf_path:
            pdf_info = f"\n    {pdf_path}"

    review_pack_info = ""
    if args.review_pack:
        from src.review_pack import export_review_pack

        review_pack_result = export_review_pack(
            report_data,
            output_dir,
            diff_data=diff_dict,
            portfolio_profile=args.portfolio_profile,
            collection=args.collection,
        )
        review_pack_info = f"\n    {review_pack_result['review_pack_path']}"

    if args.auto_archive:
        from src.archive_candidates import export_archive_report, find_archive_candidates

        candidates = find_archive_candidates(score_history)
        if candidates:
            archive_result = export_archive_report(candidates, report.username, output_dir)
            print_info(f"Archive candidates: {archive_result['count']} repos → {archive_result['report_path']}")

    if getattr(args, "vuln_check", False):
        from src.vuln_check import check_vulnerabilities, format_vuln_summary

        vulns = check_vulnerabilities(report_data.get("audits", []), cache=cache)
        print_info(format_vuln_summary(vulns))
        if vulns:
            vuln_path = output_dir / f"vuln-report-{report.username}-{_date_str(report.generated_at)}.json"
            vuln_path.write_text(json.dumps(vulns, indent=2, default=str))
            print_info(f"Vulnerability report: {vuln_path}")

    if args.narrative:
        from src.narrative import generate_narrative

        generate_narrative(report_data, output_dir)

    cache_info = ""
    if cache:
        cache_info = f"\n  Cache: {cache.hits} hits, {cache.misses} misses"

    return {
        "json_path": json_path,
        "md_path": md_path,
        "excel_path": excel_path,
        "pcc_path": pcc_path,
        "raw_path": raw_path,
        "warehouse_path": warehouse_path,
        "badge_info": badge_info,
        "notion_info": notion_info,
        "readme_info": readme_info,
        "suggestions_info": suggestions_info,
        "html_info": html_info,
        "pdf_info": pdf_info,
        "review_pack_info": review_pack_info,
        "cache_info": cache_info,
    }


def _ensure_partial_run_baseline_compatible(existing_report_data: dict | None, current_context: dict) -> bool:
    if not existing_report_data:
        return True

    existing_context = extract_baseline_context(existing_report_data)
    if not existing_context:
        print_warning(
            "Latest report does not include baseline context.\n"
            "  Run a full audit first so targeted and incremental reruns have a trustworthy baseline."
        )
        return False

    mismatches = compare_baseline_context(current_context, existing_context)
    if not mismatches:
        return True

    details = "\n".join(
        f"  {item['label']}: existing={format_mismatch_value(item['actual'])} | requested={format_mismatch_value(item['expected'])}"
        for item in mismatches
    )
    print_warning(
        "Latest report was generated with an incompatible baseline context.\n"
        f"{details}\n"
        "  Run a full audit first before doing a partial rerun."
    )
    return False


def _print_output_summary(
    headline: str,
    report: AuditReport,
    outputs: dict[str, object],
) -> None:
    print(
        f"\n✓ {headline}\n"
        f"  Average score: {report.average_score:.2f}\n"
        f"  Tiers: {report.tier_distribution}"
        f"{outputs['cache_info']}\n"
        f"  Reports:\n"
        f"    {outputs['json_path']}\n"
        f"    {outputs['md_path']}\n"
        f"    {outputs['excel_path']}\n"
        f"    {outputs['pcc_path']}\n"
        f"    {outputs['raw_path']}\n"
        f"    {outputs['warehouse_path']}"
        f"{outputs['badge_info']}"
        f"{outputs['notion_info']}"
        f"{outputs['readme_info']}"
        f"{outputs['suggestions_info']}"
        f"{outputs['html_info']}"
        f"{outputs['pdf_info']}"
        f"{outputs['review_pack_info']}",
    )
    if report.campaign_outcomes_summary.get("summary"):
        print_info(f"Post-apply monitoring: {report.campaign_outcomes_summary.get('summary')}")
    if report.next_monitoring_step.get("summary"):
        print_info(f"Next monitoring step: {report.next_monitoring_step.get('summary')}")
    if report.campaign_tuning_summary.get("summary"):
        print_info(f"Campaign tuning: {report.campaign_tuning_summary.get('summary')}")
    if report.next_tuned_campaign.get("summary"):
        print_info(f"{ACTION_SYNC_CANONICAL_LABELS['next_tie_break_candidate']}: {report.next_tuned_campaign.get('summary')}")
    if report.intervention_ledger_summary.get("summary"):
        print_info(f"Historical portfolio intelligence: {report.intervention_ledger_summary.get('summary')}")
    if report.next_historical_focus.get("summary"):
        print_info(f"Next historical focus: {report.next_historical_focus.get('summary')}")
    if report.automation_guidance_summary.get("summary"):
        print_info(f"Automation guidance: {report.automation_guidance_summary.get('summary')}")
    if report.next_safe_automation_step.get("summary"):
        print_info(f"Next safe automation step: {report.next_safe_automation_step.get('summary')}")
    print_info(_normal_audit_next_step_hint(report.username))


# ── Partial run modes ─────────────────────────────────────────────────
def _run_targeted_audit(
    args,
    client: GitHubClient,
    output_dir: Path,
    *,
    all_repos: list[RepoMetadata],
    errors: list[dict],
    custom_weights: dict[str, float] | None,
    scoring_profile_name: str,
    existing_report_path: Path | None = None,
    existing_report_data: dict | None = None,
    watch_plan=None,
    latest_trusted_baseline: dict | None = None,
) -> None:
    """Audit only specific repos and merge into the most recent full report."""
    target_names = _resolve_repo_names(args.repos)
    print_status(f"Targeted audit: {len(target_names)} repos")

    if existing_report_path is None and existing_report_data is None:
        existing_report_path, existing_report_data = _load_latest_report(output_dir)

    filtered_repos = _filter_repos(
        all_repos,
        skip_forks=args.skip_forks,
        skip_archived=args.skip_archived,
    )
    targeted_repos, missing = _select_target_repos(target_names, filtered_repos)
    run_errors = list(errors)
    for name in missing:
        run_errors.append({"repo": f"{args.username}/{name}", "error": "Repo not found in fetched metadata"})
        print_warning(f"Repo not found: {name}")

    if not targeted_repos:
        print_warning("No repos to audit.")
        return

    baseline_context = build_baseline_context_from_args(
        args,
        scoring_profile=scoring_profile_name,
        portfolio_baseline_size=len(filtered_repos),
    )
    if not _ensure_partial_run_baseline_compatible(existing_report_data, baseline_context):
        return

    portfolio_lang_freq = _portfolio_lang_freq_for_filtered_baseline(filtered_repos)
    runtime_stats: dict[str, float] = {}
    new_audits = _analyze_repos(
        targeted_repos,
        args=args,
        client=client,
        portfolio_lang_freq=portfolio_lang_freq,
        custom_weights=custom_weights,
        runtime_stats=runtime_stats,
    )
    if not new_audits:
        return

    # Load existing audits from the latest report so we can merge into them
    existing_audits = existing_report_data.get("audits", []) if existing_report_data else []
    if existing_report_path:
        print_info(f"Merging into {existing_report_path.name} ({len(existing_audits)} existing repos)")

    # Replace any existing audit entries for the re-analyzed repos
    new_names = {audit.metadata.name for audit in new_audits}
    kept_audits = [
        _audit_from_dict(audit_data)
        for audit_data in existing_audits
        if audit_data["metadata"]["name"] not in new_names
    ]
    # new_audits first so they appear at the top of the report
    merged_audits = list(new_audits) + kept_audits
    total_repos = existing_report_data.get("total_repos", len(filtered_repos)) if existing_report_data else len(filtered_repos)

    report = AuditReport.from_audits(
        args.username,
        merged_audits,
        run_errors,
        total_repos,
        scoring_profile=scoring_profile_name,
        run_mode="targeted",
        portfolio_baseline_size=len(filtered_repos),
        baseline_signature=baseline_context["baseline_signature"],
        baseline_context=baseline_context,
    )
    report.watch_state = build_watch_state(
        args,
        scoring_profile=scoring_profile_name,
        portfolio_baseline_size=len(filtered_repos),
        run_mode="targeted",
        watch_plan=watch_plan,
        latest_trusted_baseline=latest_trusted_baseline,
        full_refresh_interval_days=FULL_REFRESH_DAYS,
    )
    report.preflight_summary = getattr(args, "_preflight_summary", {})
    report.runtime_breakdown = runtime_stats
    _apply_requested_reconciliation(report, args, merged_audits)

    outputs = _write_report_outputs(
        report,
        args,
        output_dir,
        client=client,
        cache=None,
        diff_source=args.diff or existing_report_path,
    )
    _print_output_summary(
        f"Targeted audit: {len(new_audits)} new/updated + {len(kept_audits)} existing = {len(merged_audits)} total",
        report,
        outputs,
    )


def _regenerate_outputs_from_latest_report(
    args,
    output_dir: Path,
    *,
    client: GitHubClient | None,
    existing_report_path: Path,
    existing_report_data: dict,
    watch_state_override: dict | None = None,
) -> None:
    report = _report_from_dict(existing_report_data)
    if getattr(args, "_preflight_summary", {}):
        report.preflight_summary = getattr(args, "_preflight_summary", {})
    if watch_state_override:
        report.watch_state = watch_state_override
    needs_fresh_json = bool(args.campaign)
    outputs = _write_report_outputs(
        report,
        args,
        output_dir,
        client=client,
        json_path=None if needs_fresh_json else existing_report_path,
        write_json=needs_fresh_json,
        archive=needs_fresh_json,
        save_fingerprint_data=False,
    )
    print(
        f"\n✓ Regenerated outputs from latest audit for {report.username}\n"
        f"  Source report: {existing_report_path}\n"
        f"  Reports:\n"
        f"    {outputs['md_path']}\n"
        f"    {outputs['excel_path']}\n"
        f"    {outputs['pcc_path']}\n"
        f"    {outputs['raw_path']}\n"
        f"    {outputs['warehouse_path']}"
        f"{outputs['badge_info']}"
        f"{outputs['notion_info']}"
        f"{outputs['readme_info']}"
        f"{outputs['suggestions_info']}"
        f"{outputs['html_info']}"
        f"{outputs['review_pack_info']}",
    )


def _run_incremental_audit(
    args,
    client: GitHubClient,
    output_dir: Path,
    *,
    all_repos: list[RepoMetadata],
    errors: list[dict],
    custom_weights: dict[str, float] | None,
    scoring_profile_name: str,
    watch_plan=None,
    latest_trusted_baseline: dict | None = None,
) -> None:
    """Only re-audit repos whose pushed_at changed since last run."""
    from src.history import load_fingerprints

    existing_report_path, existing_report_data = _load_latest_report(output_dir)
    if not existing_report_path or not existing_report_data:
        print_warning("No previous audit report found. Run a full audit first.")
        return

    fingerprints = load_fingerprints(output_dir / ".audit-fingerprints.json")
    if not fingerprints:
        print_warning("No fingerprints found. Run a full audit first.")
        print_info(f"Usage: python -m src {args.username}")
        return

    repos = _filter_repos(all_repos, skip_forks=args.skip_forks, skip_archived=args.skip_archived)

    # Compare current pushed_at timestamps against stored fingerprints
    changed: list[str] = []
    new: list[str] = []
    for repo in repos:
        prev = fingerprints.get(repo.name)
        curr_pushed = repo.pushed_at.isoformat() if repo.pushed_at else None
        if prev is None:
            # Repo not seen before — add to audit queue
            new.append(repo.name)
        elif prev.get("pushed_at") != curr_pushed:
            # pushed_at changed — new commits since last run
            changed.append(repo.name)

    needs_audit = changed + new
    unchanged = len(repos) - len(needs_audit)
    print_info(
        f"Incremental: {len(needs_audit)} need audit "
        f"({len(changed)} changed, {len(new)} new), {unchanged} unchanged"
    )

    if not needs_audit:
        effective_watch_plan = watch_plan or argparse.Namespace(
            mode="incremental",
            reason="manual-incremental-run",
            full_refresh_due=False,
        )
        print_info("No changes. Regenerating outputs from latest report.")
        watch_state = build_watch_state(
            args,
            scoring_profile=scoring_profile_name,
            portfolio_baseline_size=existing_report_data.get("portfolio_baseline_size", len(repos)),
            run_mode="incremental",
            watch_plan=effective_watch_plan,
            latest_trusted_baseline=latest_trusted_baseline,
            full_refresh_interval_days=FULL_REFRESH_DAYS,
        )
        _regenerate_outputs_from_latest_report(
            args,
            output_dir,
            client=client,
            existing_report_path=existing_report_path,
            existing_report_data=existing_report_data,
            watch_state_override=watch_state,
        )
        return

    args.repos = needs_audit
    effective_watch_plan = watch_plan or argparse.Namespace(
        mode="incremental",
        reason="manual-incremental-run",
        full_refresh_due=False,
    )
    _run_targeted_audit(
        args,
        client,
        output_dir,
        all_repos=all_repos,
        errors=errors,
        custom_weights=custom_weights,
        scoring_profile_name=scoring_profile_name,
        existing_report_path=existing_report_path,
        existing_report_data=existing_report_data,
        watch_plan=effective_watch_plan,
        latest_trusted_baseline=latest_trusted_baseline,
    )


# ── Scoring profile loader ─────────────────────────────────────────────
def _load_scoring_profile(profile_name: str | None) -> tuple[dict[str, float] | None, str]:
    normalized = _normalize_profile_name(profile_name)
    if not profile_name:
        return None, normalized

    profile_path = Path(f"config/scoring-profiles/{profile_name}.json")
    if profile_path.is_file():
        print_info(f"Using scoring profile: {profile_name}")
        return json.loads(profile_path.read_text()), normalized

    print_warning(f"Scoring profile not found: {profile_path}")
    return None, normalized


# ── Dry-run preview ───────────────────────────────────────────────────
def _print_dry_run_summary(repos: list[RepoMetadata]) -> None:
    """Print a Rich table of repos that would be audited, then return."""
    from datetime import timezone

    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print(f"[dry-run] {len(repos)} repos would be audited", file=sys.stderr)
        for r in repos:
            print(f"  {r.name}", file=sys.stderr)
        return

    console = Console(stderr=True)
    table = Table(title=f"[dry-run] {len(repos)} repos would be audited", show_lines=False)
    table.add_column("Name")
    table.add_column("Language")
    table.add_column("Size (KB)", justify="right")
    table.add_column("Stars", justify="right")
    table.add_column("Days Since Push", justify="right")

    now = datetime.now(timezone.utc)
    total_kb = 0
    for r in repos:
        days = ""
        if r.pushed_at:
            pushed = r.pushed_at
            if pushed.tzinfo is None:
                pushed = pushed.replace(tzinfo=timezone.utc)
            days = str((now - pushed).days)
        total_kb += r.size_kb or 0
        table.add_row(
            r.name,
            r.language or "",
            str(r.size_kb or 0),
            str(r.stars or 0),
            days,
        )

    console.print(table)
    est_mb = total_kb / 1024
    console.print(f"[dim]{len(repos)} repos would be audited, est {est_mb:.1f} MB[/dim]")


# ── Main entry point ──────────────────────────────────────────────────
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    from src.approval_ledger import default_approval_reviewer

    # Load config file and merge into args (CLI flags take precedence)
    from src.config import inspect_config, merge_config_with_args
    from src.diagnostics import (
        format_diagnostics_report,
        format_preflight_summary,
        run_diagnostics,
        should_block_run,
        write_diagnostics_report,
    )

    config_inspection = inspect_config(Path(args.config) if args.config else None)
    if config_inspection.data:
        merge_config_with_args(args, config_inspection.data)
    setattr(args, "_preflight_summary", {})
    if not getattr(args, "approval_reviewer", None):
        args.approval_reviewer = default_approval_reviewer()

    # Validate mutually exclusive registry flags
    if args.registry and args.notion_registry:
        parser.error("--registry and --notion-registry cannot be used together")
    if args.sync_registry:
        parser.error(
            "--sync-registry has been retired. Use --portfolio-truth to regenerate project-registry.md from the canonical truth snapshot."
        )
    portfolio_truth_mode = bool(getattr(args, "portfolio_truth", False))
    portfolio_context_recovery_mode = bool(getattr(args, "portfolio_context_recovery", False))
    apply_context_recovery = bool(getattr(args, "apply_context_recovery", False))
    context_recovery_limit = getattr(args, "context_recovery_limit", None)

    if portfolio_truth_mode and portfolio_context_recovery_mode:
        parser.error("--portfolio-truth and --portfolio-context-recovery are separate standalone modes; run one at a time.")
    standalone_portfolio_modes = portfolio_truth_mode or portfolio_context_recovery_mode
    if apply_context_recovery and not portfolio_context_recovery_mode:
        parser.error("--apply-context-recovery requires --portfolio-context-recovery.")
    if context_recovery_limit is not None and context_recovery_limit <= 0:
        parser.error("--context-recovery-limit must be a positive integer.")
    if standalone_portfolio_modes and (
        args.control_center
        or args.approval_center
        or args.campaign
        or args.writeback_apply
        or args.writeback_target
        or args.github_projects
        or args.doctor
    ):
        parser.error(
            "Portfolio truth and context recovery are standalone workspace modes and cannot be combined with control-center, doctor, or Action Sync flags."
        )

    # Implied flag dependencies
    if args.upload_badges:
        args.badges = True
    if args.notion_sync:
        args.notion = True
    if args.writeback_apply and not args.writeback_target:
        parser.error("--writeback-apply requires --writeback-target")
    if args.writeback_target and not args.campaign:
        parser.error(
            "--writeback-target belongs to Action Sync mode. Add --campaign <name> before choosing a writeback target."
        )
    if args.github_projects and not args.campaign:
        parser.error(
            "--github-projects belongs to Action Sync mode. Add --campaign <name> before enabling GitHub Projects mirroring."
        )
    if args.github_projects and args.writeback_target not in {"github", "all"}:
        parser.error(
            "--github-projects only runs inside Action Sync with --writeback-target github or all."
        )
    if args.approve_packet and not args.campaign:
        parser.error("--approve-packet requires --campaign")
    if args.review_packet and not args.campaign:
        parser.error("--review-packet requires --campaign")
    if args.approve_packet and args.writeback_apply:
        parser.error("--approve-packet captures local approval only. Remove --writeback-apply and run apply separately.")
    if args.review_packet and args.writeback_apply:
        parser.error("--review-packet captures a local follow-up review only. Remove --writeback-apply and run apply separately.")
    if args.approve_governance and args.approval_center:
        parser.error("--approve-governance captures a local approval. Remove --approval-center for read-only mode.")
    if args.review_governance and args.approval_center:
        parser.error("--review-governance captures a local follow-up review. Remove --approval-center for read-only mode.")
    if args.approval_center and args.control_center:
        parser.error("--approval-center and --control-center are separate read-only views; run one at a time.")
    if args.approve_governance and args.review_governance:
        parser.error("--approve-governance and --review-governance are separate local actions; run one at a time.")
    if args.approve_packet and args.review_packet:
        parser.error("--approve-packet and --review-packet are separate local actions; run one at a time.")
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
        parser.error(
            "--approval-center is the read-only approval view. Remove campaign, writeback, or approval-capture flags."
        )
    if args.control_center and (args.campaign or args.writeback_target or args.writeback_apply or args.github_projects):
        parser.error(
            "--control-center is the read-only Weekly Review entrypoint. Remove campaign/writeback flags or run a normal audit for Action Sync."
        )

    if args.approval_center:
        report_output_dir = Path(args.output_dir)
        try:
            _report_path, _diff_dict, report = _refresh_latest_report_state(report_output_dir, args)
        except FileNotFoundError:
            parser.error("No existing audit report found in output directory")
        approval_json, approval_md, payload = _write_approval_center_artifacts(
            report,
            report_output_dir,
            approval_view=args.approval_view,
        )
        print_info(payload.get("approval_workflow_summary", {}).get("summary", "No current approval needs review yet."))
        print_info(payload.get("next_approval_review", {}).get("summary", "Stay local for now; no current approval needs review."))
        print_info(f"Approval center JSON: {approval_json}")
        print_info(f"Approval center Markdown: {approval_md}")
        return

    if args.approve_governance or args.approve_packet or args.review_governance or args.review_packet:
        from src.approval_ledger import (
            build_approval_followup_record,
            build_approval_record,
            load_approval_ledger_bundle,
        )
        from src.warehouse import save_approval_followup_event, save_approval_record

        report_output_dir = Path(args.output_dir)
        try:
            _report_path, diff_dict, report = _refresh_latest_report_state(report_output_dir, args)
        except FileNotFoundError:
            parser.error("No existing audit report found in output directory")
        bundle = load_approval_ledger_bundle(
            report_output_dir,
            report.to_dict(),
            list(report.operator_queue or []),
            approval_view="all",
        )
        ledger = {str(item.get("approval_id") or ""): item for item in bundle.get("approval_ledger", [])}
        if args.approve_governance or args.review_governance:
            approval_id = f"governance:{args.governance_scope}"
        else:
            approval_id = f"campaign:{args.campaign}"
        ledger_record = ledger.get(approval_id)
        if not ledger_record:
            parser.error("No matching approval subject is surfaced in the latest report.")
        if args.approve_governance or args.approve_packet:
            if ledger_record.get("approval_state") == "blocked":
                parser.error("That approval subject is blocked by non-approval prerequisites and cannot be approved yet.")
            if ledger_record.get("approval_state") == "not-applicable":
                parser.error("That approval subject is not part of the current approval workflow.")
            approval_record = build_approval_record(
                ledger_record,
                reviewer=args.approval_reviewer,
                note=args.approval_note or "",
            )
            save_approval_record(report_output_dir, approval_record)
        else:
            if ledger_record.get("approval_state") in {"ready-for-review", "needs-reapproval", "blocked", "not-applicable"}:
                parser.error(
                    "That approval subject is not currently eligible for a recurring local follow-up review."
                )
            if str(ledger_record.get("follow_up_command") or "").strip() == "":
                parser.error("That approval subject does not currently expose a follow-up review command.")
            followup_event = build_approval_followup_record(
                ledger_record,
                reviewer=args.approval_reviewer,
                note=args.approval_note or "",
            )
            save_approval_followup_event(report_output_dir, followup_event)
        _report_path, diff_dict, report = _refresh_latest_report_state(report_output_dir, args)
        _refresh_shared_artifacts_from_report(report, report_output_dir, args, diff_dict=diff_dict)
        approval_json, approval_md, payload = _write_approval_center_artifacts(
            report,
            report_output_dir,
            approval_view="all",
        )
        updated_bundle = load_approval_ledger_bundle(
            report_output_dir,
            report.to_dict(),
            list(report.operator_queue or []),
            approval_view="all",
        )
        updated_record = next(
            (item for item in updated_bundle.get("approval_ledger", []) if item.get("approval_id") == approval_id),
            ledger_record,
        )
        if args.approve_governance or args.approve_packet:
            receipt_payload = {**updated_record, **approval_record}
            receipt_json, receipt_md = _write_approval_receipt(
                report_output_dir,
                report.username,
                generated_at=datetime.now(timezone.utc),
                receipt=receipt_payload,
            )
            print_info(receipt_payload.get("summary", "Local approval captured."))
            print_info(f"Approval receipt JSON: {receipt_json}")
            print_info(f"Approval receipt Markdown: {receipt_md}")
        else:
            receipt_payload = {**updated_record, **followup_event}
            receipt_json, receipt_md = _write_followup_review_receipt(
                report_output_dir,
                report.username,
                generated_at=datetime.now(timezone.utc),
                receipt=receipt_payload,
            )
            print_info(receipt_payload.get("summary", "Local follow-up review captured."))
            print_info(f"Approval follow-up receipt JSON: {receipt_json}")
            print_info(f"Approval follow-up receipt Markdown: {receipt_md}")
        print_info(f"Approval center JSON: {approval_json}")
        print_info(f"Approval center Markdown: {approval_md}")
        return

    if portfolio_truth_mode:
        _run_portfolio_truth_mode(args)
        return
    if portfolio_context_recovery_mode:
        _run_portfolio_context_recovery_mode(args)
        return

    if args.doctor:
        result = run_diagnostics(args, config_inspection=config_inspection, full=True)
        output_dir = Path(args.output_dir)
        artifact_path = write_diagnostics_report(result, output_dir, args.username)
        print(format_diagnostics_report(result))
        print_info(f"Diagnostics artifact: {artifact_path}")
        print_info(_doctor_next_step_hint(args.username))
        if result.blocking_errors:
            raise SystemExit(1)
        return

    if args.control_center:
        from src.diff import diff_reports
        from src.governance_activation import build_governance_summary
        from src.history import find_previous
        from src.operator_control_center import (
            build_operator_snapshot,
            control_center_artifact_payload,
            normalize_review_state,
            render_control_center_markdown,
        )
        from src.weekly_command_center import (
            build_weekly_command_center_digest,
            load_latest_portfolio_truth,
            write_weekly_command_center_artifacts,
        )

        output_dir = Path(args.output_dir)
        report_path, report_data = _load_latest_report(output_dir)
        if not report_path or not report_data:
            parser.error("No existing audit report found in output directory")

        diff_dict = None
        previous_path = find_previous(report_path.name)
        if previous_path:
            diff_dict = diff_reports(
                previous_path,
                report_path,
                portfolio_profile=args.portfolio_profile,
                collection_name=args.collection,
            ).to_dict()

        report_data["latest_report_path"] = str(report_path)
        normalized = normalize_review_state(
            report_data,
            output_dir=output_dir,
            diff_data=diff_dict,
            portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        )
        normalized["governance_summary"] = build_governance_summary(normalized)
        snapshot = build_operator_snapshot(
            normalized,
            output_dir=output_dir,
            triage_view=args.triage_view,
        )
        artifact_generated_at = _report_artifact_datetime(
            report_path,
            _parse_iso_dt(normalized.get("generated_at")) or datetime.now(timezone.utc),
        )
        json_artifact, md_artifact = _latest_control_center_paths(
            output_dir,
            normalized.get("username", args.username),
            artifact_generated_at,
        )
        snapshot.setdefault("operator_summary", {})["control_center_reference"] = str(json_artifact)
        portfolio_truth_path, portfolio_truth = load_latest_portfolio_truth(output_dir)
        weekly_digest = build_weekly_command_center_digest(
            normalized,
            snapshot,
            diff_data=diff_dict,
            portfolio_truth=portfolio_truth,
            portfolio_truth_reference=str(portfolio_truth_path) if portfolio_truth_path else "",
            control_center_reference=str(json_artifact),
            report_reference=str(report_path),
            generated_at=artifact_generated_at.isoformat(),
        )
        weekly_json, weekly_md = write_weekly_command_center_artifacts(
            output_dir,
            username=normalized.get("username", args.username),
            generated_at=artifact_generated_at,
            digest=weekly_digest,
        )
        control_payload = control_center_artifact_payload(normalized, snapshot)
        control_payload["weekly_command_center_digest_v1"] = weekly_digest
        control_payload["weekly_command_center_reference"] = {
            "json_path": str(weekly_json),
            "markdown_path": str(weekly_md),
        }
        json_artifact.write_text(json.dumps(control_payload, indent=2))
        md_artifact.write_text(
            render_control_center_markdown(
                snapshot,
                normalized.get("username", args.username),
                artifact_generated_at.isoformat(),
            )
        )
        _print_control_center_summary(snapshot)
        print_info(f"Control center JSON: {json_artifact}")
        print_info(f"Control center Markdown: {md_artifact}")
        print_info(f"Weekly command center JSON: {weekly_json}")
        print_info(f"Weekly command center Markdown: {weekly_md}")
        print_info(_control_center_next_step_hint())
        return

    # ── Improvement campaign workflow (standalone, no audit needed) ────
    if getattr(args, "generate_manifest", False):
        from src.repo_improver import generate_manifest, write_manifest

        output_dir = Path(args.output_dir)
        report_path, report_data = _load_latest_report(output_dir)
        if not report_data:
            parser.error("No existing audit report found in output directory")
        manifest = generate_manifest(report_data)
        manifest_path = write_manifest(manifest, output_dir)
        print_info(f"Improvement manifest: {manifest_path} ({len(manifest)} repos)")
        return

    if getattr(args, "apply_metadata", False) or getattr(args, "apply_readmes", False):
        from src.repo_improver import (
            apply_metadata_updates,
            apply_readme_updates,
            generate_execution_report,
            load_improvements,
        )

        improvements_file = getattr(args, "improvements_file", None)
        if not improvements_file:
            parser.error("--apply-metadata / --apply-readmes requires --improvements-file")
        improvements = load_improvements(improvements_file)
        cache = None if args.no_cache else ResponseCache()
        client = GitHubClient(token=args.token, cache=cache)
        output_dir = Path(args.output_dir)
        dry_run = getattr(args, "dry_run", False)
        updates = list(improvements.values())

        all_results: list[dict] = []
        if getattr(args, "apply_metadata", False):
            results = apply_metadata_updates(client, args.username, updates, dry_run=dry_run)
            all_results.extend(results)
            ok_count = sum(1 for r in results for a in r.get("actions", []) if a.get("ok") or a.get("dry_run"))
            print_info(f"Metadata updates: {ok_count} actions {'previewed' if dry_run else 'applied'}")

        if getattr(args, "apply_readmes", False):
            results = apply_readme_updates(client, args.username, updates, dry_run=dry_run)
            all_results.extend(results)
            ok_count = sum(1 for r in results if r.get("ok") or r.get("dry_run"))
            print_info(f"README updates: {ok_count} repos {'previewed' if dry_run else 'pushed'}")

        report_path = generate_execution_report(all_results, output_dir)
        print_info(f"Execution report: {report_path}")
        return

    def _run_once() -> None:
        if args.preflight_mode != "off":
            preflight = run_diagnostics(args, config_inspection=config_inspection, full=False)
            setattr(args, "_preflight_summary", preflight.to_preflight_summary())
            print_info(format_preflight_summary(preflight))
            if preflight.status != "ok":
                for check in [item for item in preflight.checks if item.status != "ok"][:5]:
                    print_warning(f"{check.summary} ({check.category})")
            if should_block_run(preflight, args.preflight_mode):
                raise SystemExit(1)

        custom_weights, scoring_profile_name = _load_scoring_profile(args.scoring_profile)

        if not args.token:
            print_warning(
                "No token provided. Only public repos will be fetched.\n"
                "  Set GITHUB_TOKEN or pass --token for private repo access."
            )

        cache = None if args.no_cache else ResponseCache()
        client = GitHubClient(token=args.token, cache=cache)
        output_dir = Path(args.output_dir)

        # Fetch all repo metadata from GitHub API (REST or GraphQL depending on flag)
        all_repos, errors = _fetch_repo_metadata(args, client)
        total_fetched = len(all_repos)
        repos = _filter_repos(
            all_repos,
            skip_forks=args.skip_forks,
            skip_archived=args.skip_archived,
        )
        _print_filter_summary(all_repos, repos, args)

        # Dry-run: preview repos and exit early
        if getattr(args, "dry_run", False):
            _print_dry_run_summary(repos)
            return

        # Dispatch to partial run mode if requested
        if args.repos:
            _run_targeted_audit(
                args,
                client,
                output_dir,
                all_repos=all_repos,
                errors=errors,
                custom_weights=custom_weights,
                scoring_profile_name=scoring_profile_name,
                watch_plan=getattr(args, "_watch_plan", None),
                latest_trusted_baseline=getattr(args, "_latest_trusted_watch_baseline", None),
            )
            return

        if args.incremental:
            _run_incremental_audit(
                args,
                client,
                output_dir,
                all_repos=all_repos,
                errors=errors,
                custom_weights=custom_weights,
                scoring_profile_name=scoring_profile_name,
                watch_plan=getattr(args, "_watch_plan", None),
                latest_trusted_baseline=getattr(args, "_latest_trusted_watch_baseline", None),
            )
            return

        # Resume: load previously completed audits and skip re-analyzing them
        resumed_names: set[str] = set()
        resumed_audits: list[RepoAudit] = []
        if getattr(args, "resume", False):
            from src.progress import load_progress

            saved = load_progress(output_dir)
            if saved:
                completed_dicts, _run_meta = saved
                for audit_dict in completed_dicts:
                    try:
                        resumed_audits.append(_audit_from_dict(audit_dict))
                        resumed_names.add(audit_dict.get("metadata", {}).get("name", ""))
                    except Exception:
                        pass
                if resumed_audits:
                    print_info(f"Resumed {len(resumed_audits)} previously completed repo(s)")
                    repos = [r for r in repos if r.name not in resumed_names]

        runtime_stats: dict[str, float] = {}
        audits = _analyze_repos(
            repos,
            args=args,
            client=client,
            portfolio_lang_freq=_portfolio_lang_freq_for_filtered_baseline(repos),
            custom_weights=custom_weights,
            runtime_stats=runtime_stats,
        )
        all_audits = resumed_audits + audits

        # Full audit path: score every repo and write all output formats
        if all_audits:
            audits = all_audits
            baseline_context = build_baseline_context_from_args(
                args,
                scoring_profile=scoring_profile_name,
                portfolio_baseline_size=len(repos),
            )
            report = AuditReport.from_audits(
                args.username,
                audits,
                errors,
                total_fetched,
                scoring_profile=scoring_profile_name,
                run_mode="full",
                portfolio_baseline_size=len(repos),
                baseline_signature=baseline_context["baseline_signature"],
                baseline_context=baseline_context,
            )
            report.watch_state = build_watch_state(
                args,
                scoring_profile=scoring_profile_name,
                portfolio_baseline_size=len(repos),
                run_mode="full",
                watch_plan=getattr(args, "_watch_plan", None),
                latest_trusted_baseline=getattr(args, "_latest_trusted_watch_baseline", None),
                full_refresh_interval_days=FULL_REFRESH_DAYS,
            )
            report.preflight_summary = getattr(args, "_preflight_summary", {})
            report.runtime_breakdown = runtime_stats
            _apply_requested_reconciliation(report, args, audits)
            outputs = _write_report_outputs(report, args, output_dir, client=client, cache=cache)
            _print_output_summary(f"Audited {report.repos_audited} repos for {report.username}", report, outputs)

            if getattr(args, "create_issues", False):
                from src.issue_creator import create_audit_issues
                from src.quick_wins import find_quick_wins

                quick_wins = find_quick_wins(audits)
                issue_result = create_audit_issues(
                    quick_wins,
                    args.username,
                    client,
                    dry_run=getattr(args, "dry_run", False),
                )
                print_info(
                    f"Issues: {len(issue_result['created'])} created, "
                    f"{len(issue_result['skipped'])} skipped (already exist)"
                )

            if getattr(args, "summary", False) and outputs.get("json_path"):
                from src.diff import diff_reports, print_diff_summary
                from src.history import find_previous

                prev_path = find_previous(outputs["json_path"].name)
                if prev_path:
                    diff = diff_reports(
                        prev_path,
                        outputs["json_path"],
                        portfolio_profile=args.portfolio_profile,
                        collection_name=args.collection,
                    )
                    print_diff_summary(diff)

            return

        # Fallback: --skip-clone was used, write raw metadata only
        raw_path = _write_json(
            args.username, repos, errors, total_fetched, output_dir,
        )
        print(
            f"\n✓ Fetched {total_fetched} repos for {args.username}\n"
            f"  Included: {len(repos)} | Errors: {len(errors)}\n"
            f"  Output: {raw_path}",
        )

    if args.watch:
        from src.recurring_review import choose_watch_plan
        from src.watch import run_watch_loop

        def _run_watch_once() -> None:
            watch_plan = choose_watch_plan(
                Path(args.output_dir),
                args,
                scoring_profile=normalize_scoring_profile(args.scoring_profile),
            )
            print_info(
                "Watch decision: "
                f"{watch_plan.mode} ({watch_plan.reason})"
            )
            original_incremental = args.incremental
            original_repos = args.repos
            setattr(args, "_watch_plan", watch_plan)
            setattr(args, "_latest_trusted_watch_baseline", watch_plan.latest_trusted_baseline)
            try:
                args.incremental = watch_plan.mode == "incremental"
                args.repos = None
                _run_once()
            finally:
                args.incremental = original_incremental
                args.repos = original_repos

        run_watch_loop(_run_watch_once, interval=args.watch_interval)
        return

    _run_once()
