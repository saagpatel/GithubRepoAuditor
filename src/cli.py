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
import re
import subprocess
import sys
import warnings
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
from src.cli_mode_validation import validate_cli_mode_args
from src.cli_output import create_progress, print_info, print_status, print_warning
from src.cloner import clone_workspace
from src.github_client import GitHubClient
from src.models import AuditReport, RepoAudit, RepoMetadata
from src.operator_approval_artifacts import (
    write_approval_center_artifacts as _write_approval_center_artifacts,
    write_approval_receipt as _write_approval_receipt,
    write_followup_review_receipt as _write_followup_review_receipt,
)
from src.operator_control_center_artifacts import (
    should_print_control_center_item as _should_print_control_center_item,
    write_control_center_artifacts as _write_control_center_artifacts,
)
from src.portfolio_truth_types import TRUTH_LATEST_FILENAME, truth_latest_path
from src.recurring_review import FULL_REFRESH_DAYS
from src.report_enrichment import build_run_change_counts, build_run_change_summary
from src.report_state import (
    audit_from_dict as _audit_from_dict,
    load_latest_report as _load_latest_report,
    parse_iso_datetime as _parse_iso_dt,
    report_from_dict as _report_from_dict,
    report_artifact_datetime as _report_artifact_datetime,
)
from src.report_operating_paths import apply_operating_paths as _apply_operating_paths
from src.report_portfolio_catalog import apply_portfolio_catalog as _apply_portfolio_catalog
from src.report_scorecards import apply_scorecards as _apply_scorecards
from src.report_operator_state import enrich_report_with_operator_state as _enrich_report_with_operator_state
from src.reporter import (
    write_json_report,
    write_markdown_report,
    write_pcc_export,
    write_raw_metadata,
)
from src.scorer import score_repo
from src.terminology import ACTION_SYNC_CANONICAL_LABELS

# Emitted at most once per process when legacy flat invocation is used.
_LEGACY_WARNING_EVENTS: set[str] = set()

DEFAULT_ANALYSIS_WORKERS = 1
MAX_ANALYSIS_WORKERS = 8
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

CLI_MODE_EXAMPLES = """Subcommands: run, triage, report, serve
  Run `audit run --help`, `audit triage --help`, or `audit report --help` for flags.

Subcommand form (preferred):
  audit run   <github-username> --html
  audit run   <github-username> --repos <repo-name>
  audit triage <github-username> --control-center
  audit triage <github-username> --approval-center
  audit report <github-username> --portfolio-truth
  audit report <github-username> --campaign security-review --writeback-target github
  audit security-gate --output-dir output
  audit serve  [--port 8080]

Legacy flat form (deprecated, still supported):
  audit <github-username> --doctor
  audit <github-username> --html
  audit <github-username> --control-center
  audit <github-username> --campaign security-review --writeback-target all --github-projects"""


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
        # Missing or slow gh CLI auth falls back to unauthenticated/public mode.
        pass
    return None


# ── Subcommand builders ───────────────────────────────────────────────
#
# Each builder defines the PRIMARY (help-visible) flags for its subcommand.
# The legacy flat parser at the top level accepts ALL flags so that existing
# invocations (`audit username --flag`) continue to work unchanged.
#
# Global flags shared across all subcommands: --token, --output-dir, --config, --verbose


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags that appear on every subcommand."""
    parser.add_argument(
        "username",
        nargs="?",
        default=None,
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
        "--config",
        default=None,
        help="Path to audit-config.yaml (default: ./audit-config.yaml if exists)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed output",
    )


def _build_run_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Subcommand: `audit run` — produce a fresh audit."""
    p = subparsers.add_parser(
        "run",
        help="Run a fresh audit against a GitHub user's repos",
        description="Fetch, clone, analyze, and score all repos for the given username.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_global_flags(p)
    p.add_argument(
        "--repos",
        nargs="+",
        default=None,
        metavar="REPO",
        help="Audit only these specific repos (targeted mode)",
    )
    p.add_argument("--skip-forks", action="store_true", help="Exclude forked repos")
    p.add_argument("--skip-archived", action="store_true", help="Exclude archived repos")
    p.add_argument("--skip-clone", action="store_true", help="Skip clone step (metadata only)")
    p.add_argument(
        "--incremental", action="store_true", help="Re-audit only repos changed since last run"
    )
    p.add_argument("--graphql", action="store_true", help="Use GraphQL API for faster bulk fetch")
    p.add_argument("--badges", action="store_true", help="Generate Shields.io badge files")
    p.add_argument("--html", action="store_true", help="Generate interactive HTML dashboard")
    p.add_argument("--pdf", action="store_true", help="Generate PDF audit report")
    p.add_argument("--narrative", action="store_true", help="Generate AI portfolio narrative")
    p.add_argument(
        "--briefing", action="store_true", help="Generate structured weekly operator briefing"
    )
    p.add_argument(
        "--fetch-mode",
        choices=["sync", "async"],
        default="sync",
        help="Per-repo enrichment fetch strategy (default: sync)",
    )
    p.add_argument(
        "--analysis-workers", type=int, default=None, help="Number of repo-analysis workers"
    )
    p.add_argument("--no-cache", action="store_true", help="Bypass API response cache")
    p.add_argument(
        "--scoring-profile",
        type=str,
        default=None,
        metavar="NAME",
        help="Custom scoring profile from config/scoring-profiles/NAME.json",
    )
    p.add_argument(
        "--watch", action="store_true", help="Re-run audit on interval (see --watch-interval)"
    )
    p.add_argument("--resume", action="store_true", help="Resume a partial audit run")
    p.add_argument(
        "--vuln-check", action="store_true", help="Query OSV.dev for known vulnerabilities"
    )
    p.add_argument(
        "--reindex", action="store_true", help="Rebuild portfolio semantic index after audit"
    )
    p.add_argument(
        "--embedder",
        choices=["voyage", "local"],
        default="voyage",
        help="Embedder backend for --reindex (default: voyage)",
    )


def _build_triage_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Subcommand: `audit triage` — review existing run + approval workflows."""
    p = subparsers.add_parser(
        "triage",
        help="Review operator state and manage approval workflows",
        description="Inspect control-center, approval queues, acknowledgments, and semantic search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_global_flags(p)
    p.add_argument("--control-center", action="store_true", help="Show latest operator state")
    p.add_argument(
        "--approval-center", action="store_true", help="Show latest approval workflow state"
    )
    p.add_argument(
        "--triage-view",
        choices=["all", "urgent", "ready", "blocked", "deferred"],
        default="all",
        help="Filter control-center output (default: all)",
    )
    p.add_argument(
        "--approval-view",
        choices=["all", "ready", "approved", "needs-reapproval", "blocked", "applied"],
        default="all",
        help="Filter approval-center output (default: all)",
    )
    p.add_argument(
        "--auto-apply-approved",
        action="store_true",
        help="Apply approved campaign packets for repos passing the automation trust bar",
    )
    p.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    p.add_argument(
        "--approve-governance", action="store_true", help="Capture a governance approval"
    )
    p.add_argument("--approve-packet", action="store_true", help="Capture a campaign approval")
    p.add_argument(
        "--review-governance", action="store_true", help="Capture a governance follow-up review"
    )
    p.add_argument(
        "--review-packet", action="store_true", help="Capture a campaign follow-up review"
    )
    p.add_argument("--reset-prefs", action="store_true", help="Clear operator suppression hints")
    p.add_argument(
        "--acknowledge-target", type=str, default=None, help="Repo to acknowledge in review queue"
    )
    p.add_argument("--acknowledge-kind", type=str, default=None, help="Change type to acknowledge")
    p.add_argument(
        "--semantic-search",
        default=None,
        metavar="QUERY",
        help="Semantic search against portfolio index",
    )
    p.add_argument("--ask", default=None, metavar="QUERY", help="Alias for --semantic-search")
    # ── Initiative tracker (7A.3) ─────────────────────────────────────────
    p.add_argument(
        "--set-initiative",
        default=None,
        metavar="REPO",
        dest="set_initiative",
        help="Set or update a tier-upgrade initiative for REPO",
    )
    p.add_argument(
        "--target-tier",
        type=int,
        choices=[2, 3, 4],
        default=None,
        dest="target_tier",
        help="Target maturity tier (2=Silver, 3=Gold, 4=Platinum); required with --set-initiative",
    )
    p.add_argument(
        "--deadline",
        default=None,
        metavar="YYYY-MM-DD",
        help="Deadline for the initiative (YYYY-MM-DD); required with --set-initiative",
    )
    p.add_argument(
        "--initiatives",
        action="store_true",
        help="List all initiatives with current status",
    )
    p.add_argument(
        "--close-initiative",
        default=None,
        metavar="REPO",
        dest="close_initiative",
        help="Close the open initiative for REPO (marks as met)",
    )
    # ── LLM-suggested initiatives (8.4) ───────────────────────────────────
    p.add_argument(
        "--suggest-initiatives",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="TARGET_TIER",
        help="LLM-rank repos closest to qualifying for TARGET_TIER (default: next tier from current)",
    )
    p.add_argument(
        "--llm-budget",
        type=float,
        default=None,
        metavar="USD",
        help="Override default LLM cost ceiling (default $0.10 for --suggest-initiatives)",
    )
    # ── Accept suggestion (9.1) ───────────────────────────────────────────
    p.add_argument(
        "--accept-suggestion",
        type=str,
        default=None,
        metavar="REPO",
        dest="accept_suggestion",
        help="Convert a suggestion into an initiative (creates an initiatives.json entry)",
    )
    # ── Dismiss suggestion (11.4) ─────────────────────────────────────────
    p.add_argument(
        "--dismiss-suggestion",
        type=str,
        default=None,
        metavar="REPO",
        help="Suppress repo from future LLM-suggested initiatives",
    )
    p.add_argument(
        "--reason",
        type=str,
        default="",
        help="Reason for dismissal (used with --dismiss-suggestion)",
    )
    p.add_argument(
        "--undo-dismiss",
        type=str,
        default=None,
        metavar="REPO",
        help="Restore a dismissed repo to the suggestion pool",
    )
    p.add_argument(
        "--list-dismissed",
        action="store_true",
        help="List currently dismissed suggestion repos",
    )
    # ── Auto-expire + audit trail (12.1) ─────────────────────────────────────
    p.add_argument(
        "--dismiss-expires-days",
        type=int,
        default=None,
        metavar="N",
        help="Auto-expire dismissal after N days (default: permanent)",
    )
    p.add_argument(
        "--expire-dismissals",
        action="store_true",
        help="Run cleanup: remove dismissals whose expiry date has passed",
    )
    p.add_argument(
        "--dismissal-history",
        action="store_true",
        help="Show audit trail of dismissal events",
    )


def _add_automation_proposal_flags(parser: argparse.ArgumentParser) -> None:
    """Arc D phase-3b bounded-automation proposal triage flags.

    Added to both the ``report`` subparser and the legacy parser so the queue
    can be driven from either invocation form, mirroring the context-recovery
    flags. Execution is dry-run unless ``--apply`` is also given.
    """
    parser.add_argument(
        "--propose-automation",
        action="store_true",
        help="Generate/refresh bounded-automation proposals for eligible repos",
    )
    parser.add_argument(
        "--list-proposals",
        action="store_true",
        help="List the durable bounded-automation proposal queue",
    )
    parser.add_argument(
        "--approve-proposal",
        type=str,
        default=None,
        metavar="ID",
        help="Approve a pending bounded-automation proposal by id",
    )
    parser.add_argument(
        "--reject-proposal",
        type=str,
        default=None,
        metavar="ID",
        help="Reject a pending bounded-automation proposal by id",
    )
    parser.add_argument(
        "--execute-proposals",
        action="store_true",
        help="Execute approved bounded-automation proposals (dry-run unless --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --execute-proposals: actually apply (open PRs / write catalog seeds)",
    )


def _build_report_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Subcommand: `audit report` — generate exports, packets, and writebacks."""
    p = subparsers.add_parser(
        "report",
        help="Generate exports, campaign packets, and writeback actions",
        description="Portfolio truth, Excel workbooks, campaigns, writebacks, and context recovery.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_global_flags(p)
    p.add_argument(
        "--portfolio-truth", action="store_true", help="Generate canonical portfolio truth snapshot"
    )
    p.add_argument(
        "--portfolio-truth-allow-empty-notion",
        action="store_true",
        help=(
            "When live Notion context is unavailable, carry forward the previously "
            "published Notion context instead of refusing to publish. For headless or "
            "scheduled refreshes that update risk/activity signals without dropping "
            "advisory context to zero."
        ),
    )
    p.add_argument(
        "--portfolio-context-recovery",
        action="store_true",
        help="Build active/recent weak-context recovery plan",
    )
    p.add_argument(
        "--apply-context-recovery",
        action="store_true",
        help="Apply eligible context recovery updates",
    )
    p.add_argument(
        "--tier-recalibration-report",
        action="store_true",
        help="Generate tier distribution report and flag bunching",
    )
    p.add_argument(
        "--context-triage",
        action="store_true",
        help="Run context quality triage across the portfolio",
    )
    _add_automation_proposal_flags(p)
    p.add_argument(
        "--excel-mode",
        choices=["template", "standard"],
        default="standard",
        help="Workbook style: standard (default) or template-backed",
    )
    p.add_argument(
        "--diff",
        type=Path,
        default=None,
        metavar="PREVIOUS_REPORT",
        help="Compare against a previous report",
    )
    p.add_argument("--summary", action="store_true", help="Print a Rich diff summary to stderr")
    p.add_argument("--scorecard", action="store_true", help="Apply internal scorecard programs")
    p.add_argument(
        "--campaign",
        choices=[
            "security-review",
            "promotion-push",
            "archive-sweep",
            "showcase-publish",
            "maintenance-cleanup",
        ],
        default=None,
        help="Build a managed campaign view",
    )
    p.add_argument(
        "--writeback-target",
        choices=["github", "notion", "all"],
        default=None,
        help="External system to receive writeback actions",
    )
    p.add_argument(
        "--writeback-apply", action="store_true", help="Execute live writeback (not preview)"
    )
    p.add_argument(
        "--campaign-from-ledger",
        action="store_true",
        help="When paired with --writeback-apply, execute approved campaign-plan packets from the ledger",
    )
    p.add_argument(
        "--github-projects",
        action="store_true",
        help="Mirror campaign actions into GitHub Projects v2",
    )
    p.add_argument(
        "--campaign-sync-mode",
        choices=["reconcile", "append-only", "close-missing"],
        default="reconcile",
        help="Campaign record reconciliation strategy (default: reconcile)",
    )
    p.add_argument(
        "--max-actions",
        type=int,
        default=20,
        help="Max managed actions per campaign run (default: 20)",
    )
    p.add_argument(
        "--apply-metadata",
        action="store_true",
        help="Apply description/topics from improvements file",
    )
    p.add_argument(
        "--apply-readmes", action="store_true", help="Push README updates via Contents API"
    )
    p.add_argument(
        "--improvements-file", type=Path, default=None, help="Path to improvements JSON file"
    )
    p.add_argument(
        "--generate-manifest",
        action="store_true",
        help="Generate improvement manifest from latest report",
    )
    p.add_argument(
        "--create-issues",
        action="store_true",
        help="Create GitHub issues for high-priority action items",
    )
    p.add_argument("--upload-badges", action="store_true", help="Upload badge JSON to GitHub Gist")
    p.add_argument("--notion-sync", action="store_true", help="Push audit events to Notion API")
    p.add_argument("--notion-registry", action="store_true", help="Use Notion as registry source")
    p.add_argument(
        "--portfolio-profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Ranking overlay profile for analyst-facing outputs (default: default)",
    )
    p.add_argument(
        "--collection",
        type=str,
        default=None,
        metavar="NAME",
        help="Filter outputs to named collection",
    )
    # ── Draft README authoring (Arc G S5.1-5.3) ──────────────────────
    p.add_argument(
        "--draft-readmes",
        action="store_true",
        help="Draft README packets for qualifying repos via LLM",
    )
    p.add_argument(
        "--draft-readmes-all",
        action="store_true",
        help="Apply to every qualifying repo (stale/missing/short)",
    )
    p.add_argument(
        "--draft-readmes-repo",
        action="append",
        default=None,
        dest="draft_readmes_repos",
        metavar="REPO",
        help="Explicit per-repo opt-in (repeatable)",
    )
    # ── Campaign planner (Arc G S6.1-6.2) ────────────────────────────
    p.add_argument(
        "--plan-campaign",
        default=None,
        metavar="GOAL",
        dest="plan_campaign",
        help="Generate a goal-driven campaign plan via LLM (e.g. 'archive dead repos')",
    )
    p.add_argument(
        "--max-repos",
        type=int,
        default=50,
        dest="max_repos",
        help="Max repos to consider when planning a campaign (default: 50)",
    )
    # ── Tier-gap export (Arc G S12.4) ─────────────────────────────────
    p.add_argument(
        "--tier-gaps",
        action="store_true",
        help="Dump per-repo TierGap data (current tier + missing requirements + source) for external tooling",
    )
    p.add_argument(
        "--tier-gaps-target",
        type=int,
        choices=[2, 3, 4],
        default=None,
        metavar="TIER",
        help="Override target tier for gap calculation (default: current+1 per repo). Valid: 2-4.",
    )
    p.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format for --tier-gaps (default: json)",
    )


def _build_serve_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Subcommand: `audit serve` — start the local web UI."""
    p = subparsers.add_parser(
        "serve",
        help="Start local web UI (FastAPI + HTMX) for portfolio artefacts",
        description="Serve portfolio artefacts via a local FastAPI + HTMX web UI. Requires [serve] extra.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN") or _gh_auth_token(),
        help="GitHub personal access token",
    )
    p.add_argument(
        "--output-dir", default="output", help="Directory for output files (default: output/)"
    )
    p.add_argument("--config", default=None, help="Path to audit-config.yaml")
    p.add_argument("--verbose", action="store_true", help="Print detailed output")


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
        nargs="?",
        default=None,
        help="GitHub username to audit (omit when using --serve)",
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
        "--portfolio-truth-include-release-count",
        action="store_true",
        help=(
            "Overlay derived.release_count on each project from the latest "
            "output/audit-report-<username>-*.json warehouse file (requires a prior audit run)"
        ),
    )
    parser.add_argument(
        "--portfolio-truth-include-security",
        action="store_true",
        help=(
            "Overlay the security.* GHAS alert counts on each project from the latest "
            "output/ghas-alerts-<username>-*.json file, feeding the active-high-severity-alerts "
            "risk factor (requires a prior `audit report --ghas-alerts` run)"
        ),
    )
    parser.add_argument(
        "--portfolio-truth-allow-empty-notion",
        action="store_true",
        help=(
            "When live Notion context is unavailable, carry forward the previously "
            "published Notion context instead of refusing to publish. For headless or "
            "scheduled refreshes that update risk/activity signals without dropping "
            "advisory context to zero."
        ),
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
        "--tier-recalibration-report",
        action="store_true",
        help="Generate tier distribution report and flag bunching",
    )
    parser.add_argument(
        "--context-triage",
        action="store_true",
        help="Run context quality triage across the portfolio",
    )
    parser.add_argument(
        "--context-recovery-limit",
        type=int,
        default=None,
        help="Optional cap on how many eligible recovery targets to apply in one run",
    )
    parser.add_argument(
        "--allow-dirty-worktree",
        action="store_true",
        help="Allow context recovery to apply to repos with uncommitted changes",
    )
    _add_automation_proposal_flags(parser)
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
        "--no-analyzer-cache",
        action="store_true",
        help="Disable per-(repo, sha, analyzer) result cache for this run (reads and writes). "
        "Useful for reconcile gates that need fresh analyzer output.",
    )
    parser.add_argument(
        "--reconcile-cache",
        action="store_true",
        help="After audit, re-run analyzers without cache and diff against cached results. "
        "Exits non-zero on divergence. Intended for CI release gates.",
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
        help="Apply internal scorecard programs from config/scorecards.yaml",
    )
    parser.add_argument(
        "--ossf-scorecard",
        action="store_true",
        dest="ossf_scorecard",
        help=(
            "Fetch pre-computed OSSF Scorecard scores for public repos from "
            "api.securityscorecards.dev and write output/ossf-scorecard-<user>-<date>.json"
        ),
    )
    parser.add_argument(
        "--sbom-source",
        choices=["lockfile", "github"],
        default="lockfile",
        dest="sbom_source",
        help=(
            "Dependency count source.  'lockfile' (default) uses local manifest parsing. "
            "'github' fetches the SPDX SBOM from GitHub's dependency graph API, "
            "which catches transitive deps and works without a clone."
        ),
    )
    parser.add_argument(
        "--security-offline",
        action="store_true",
        help="Use local security analysis only and skip GitHub-native or external security enrichment",
    )
    parser.add_argument(
        "--analysis-workers",
        type=int,
        default=None,
        help=(
            "Number of repo-analysis workers. Defaults to 1 for reliable, visible full "
            "audits. Set GITHUB_REPO_AUDITOR_ANALYSIS_WORKERS or pass this flag to opt "
            "into parallel analysis."
        ),
    )
    parser.add_argument(
        "--fetch-mode",
        choices=["sync", "async"],
        default="sync",
        help=(
            "Per-repo enrichment fetch strategy.  'sync' (default) uses the existing "
            "sequential requests path.  'async' enables the httpx-based parallel fetcher "
            "which pre-fetches all enrichment endpoints concurrently before analysis."
        ),
    )
    parser.add_argument(
        "--fetch-workers",
        type=int,
        default=10,
        help=(
            "Max concurrent in-flight HTTP requests for the async enrichment fetcher "
            "(only used when --fetch-mode async is set).  Default: 10."
        ),
    )
    parser.add_argument(
        "--campaign",
        choices=[
            "security-review",
            "promotion-push",
            "archive-sweep",
            "showcase-publish",
            "maintenance-cleanup",
        ],
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
        "--campaign-from-ledger",
        action="store_true",
        help="When paired with --writeback-apply, execute approved campaign-plan packets from the ledger",
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
    # ── Narrative / briefing (mutually exclusive) ─────────────────────────────
    narrative_or_briefing = parser.add_mutually_exclusive_group()
    narrative_or_briefing.add_argument(
        "--narrative",
        action="store_true",
        help="Generate AI portfolio narrative (requires ANTHROPIC_API_KEY or GitHub token with models: read scope)",
    )
    narrative_or_briefing.add_argument(
        "--briefing",
        action="store_true",
        help=(
            "Generate a structured weekly operator briefing (Markdown + optional voice-readable). "
            "Includes: shipped-this-week, needs-attention top-5, portfolio health delta, "
            "and LLM-authored one-liner suggestions for top-3 repos."
        ),
    )
    parser.add_argument(
        "--briefing-voice",
        action="store_true",
        help="When used with --briefing, also write a voice-readable plain-text variant (.voice.txt).",
    )
    parser.add_argument(
        "--include-suggestions",
        action="store_true",
        default=False,
        dest="include_suggestions",
        help="When used with --briefing, run LLM-ranked tier-upgrade suggestions (Arc G S8.4). Off by default to keep briefings cheap.",
    )
    parser.add_argument(
        "--narrative-provider",
        choices=["anthropic", "github-models"],
        default=None,
        dest="narrative_provider",
        help=(
            "Narrative inference provider. Defaults to 'anthropic' when ANTHROPIC_API_KEY is set, "
            "'github-models' when a GitHub token is available, otherwise skipped. "
            "Also used by --briefing for LLM suggestions."
        ),
    )
    parser.add_argument(
        "--narrative-model",
        default=None,
        dest="narrative_model",
        help=(
            "Model name for narrative generation. "
            "Defaults: claude-sonnet-4-6 (anthropic), gpt-4o-mini (github-models). "
            "For --briefing, defaults to claude-haiku-4-5 / gpt-4o-mini (cheaper)."
        ),
    )
    parser.add_argument(
        "--max-llm-spend",
        type=float,
        default=None,
        metavar="USD",
        dest="max_llm_spend",
        help=(
            "Halt run if total LLM API spend would exceed this USD threshold. "
            "Default disabled. Telemetry is always written to output/run-telemetry.jsonl "
            "when --narrative or --briefing is used."
        ),
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
        "--reset-prefs",
        action="store_true",
        help="Delete output/operator_prefs.json and exit (clears all auto-detected suppression hints)",
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
        "--auto-apply-approved",
        action="store_true",
        help="Automatically apply approved campaign packets for repos that pass the automation trust bar",
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
        "--acknowledge-target",
        type=str,
        default=None,
        help="Repo name to acknowledge in the recurring-review queue (use with --acknowledge-kind)",
    )
    parser.add_argument(
        "--acknowledge-kind",
        type=str,
        default=None,
        choices=[
            "security-change",
            "lens-delta",
            "tier-change",
            "score-delta",
            "hotspot-change",
            "campaign-drift",
            "governance-drift",
            "rollback-exposure",
        ],
        help="Change type to acknowledge for the target repo",
    )
    parser.add_argument(
        "--acknowledge-reviewer",
        type=str,
        default=None,
        help="Reviewer name recorded on the acknowledgment (defaults to approval reviewer fallback)",
    )
    parser.add_argument(
        "--acknowledge-note",
        type=str,
        default="",
        help="Required free-text note explaining why the change has been acknowledged",
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
        "--ghas-alerts",
        action="store_true",
        help=(
            "Fetch open Dependabot/CodeQL/Secret-scanning alert counts from GitHub. "
            "Implied by --vuln-check."
        ),
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
    # ── Draft README authoring (Arc G S5.1-5.3) ──────────────────────
    parser.add_argument(
        "--draft-readmes",
        action="store_true",
        help="Draft README packets for qualifying repos via LLM",
    )
    parser.add_argument(
        "--draft-readmes-all",
        action="store_true",
        help="Apply --draft-readmes to every qualifying repo (stale/missing/short)",
    )
    parser.add_argument(
        "--draft-readmes-repo",
        action="append",
        default=None,
        dest="draft_readmes_repos",
        metavar="REPO",
        help="Explicit per-repo opt-in for --draft-readmes (repeatable)",
    )
    # ── Campaign planner (Arc G S6.1-6.2) ────────────────────────────────────
    parser.add_argument(
        "--plan-campaign",
        default=None,
        metavar="GOAL",
        dest="plan_campaign",
        help="Generate a goal-driven campaign plan via LLM (e.g. 'archive dead repos')",
    )
    parser.add_argument(
        "--max-repos",
        type=int,
        default=50,
        dest="max_repos",
        help="Max repos to consider when planning a campaign (default: 50)",
    )
    # ── Tier-gap export (Arc G S12.4) ─────────────────────────────────────────
    parser.add_argument(
        "--tier-gaps",
        action="store_true",
        help="Dump per-repo TierGap data (current tier + missing requirements + source) for external tooling",
    )
    parser.add_argument(
        "--tier-gaps-target",
        type=int,
        default=None,
        metavar="TIER",
        help="Override target tier for gap calculation (default: current+1 per repo). Valid: 2-4.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format for --tier-gaps (default: json)",
    )
    parser.add_argument(
        "--improvements-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a JSON file with generated improvements (descriptions, topics, READMEs)",
    )
    # ── Semantic index (Arc F S3.1) ────────────────────────────────────
    parser.add_argument(
        "--reindex",
        action="store_true",
        help=(
            "After audit completes, rebuild the portfolio semantic index. "
            "Only re-embeds repos whose doc content changed since last index. "
            "Requires VOYAGE_API_KEY (default) or --embedder local."
        ),
    )
    parser.add_argument(
        "--reindex-force",
        action="store_true",
        help="Re-embed all repos even if content unchanged (use after embedder model upgrade).",
    )
    parser.add_argument(
        "--semantic-search",
        default=None,
        metavar="QUERY",
        help=(
            "Run a semantic search against the existing portfolio index and print top-5 results. "
            "No audit is performed; the warehouse must have been indexed with --reindex first."
        ),
    )
    parser.add_argument(
        "--ask",
        default=None,
        metavar="QUERY",
        help="Alias for --semantic-search.",
    )
    parser.add_argument(
        "--embedder",
        choices=["voyage", "local"],
        default="voyage",
        help=(
            "Embedder backend for --reindex / --semantic-search. "
            "'voyage' uses Voyage AI voyage-code-3 (requires VOYAGE_API_KEY). "
            "'local' uses sentence-transformers/all-MiniLM-L6-v2 (requires [semantic] extra)."
        ),
    )
    # ── Serve mode ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start local web UI (FastAPI + HTMX) for portfolio artefacts. Requires [serve] extra.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for --serve (default: 8080)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for --serve (default: 127.0.0.1)",
    )
    # ── Initiative tracker (7A.3) — also registered here so legacy parser accepts them ──
    parser.add_argument(
        "--set-initiative",
        default=None,
        metavar="REPO",
        dest="set_initiative",
        help="Set or update a tier-upgrade initiative for REPO",
    )
    parser.add_argument(
        "--target-tier",
        type=int,
        choices=[2, 3, 4],
        default=None,
        dest="target_tier",
        help="Target maturity tier (2=Silver, 3=Gold, 4=Platinum); required with --set-initiative",
    )
    parser.add_argument(
        "--deadline",
        default=None,
        metavar="YYYY-MM-DD",
        help="Deadline for the initiative (YYYY-MM-DD); required with --set-initiative",
    )
    parser.add_argument(
        "--initiatives",
        action="store_true",
        help="List all initiatives with current status",
    )
    parser.add_argument(
        "--close-initiative",
        default=None,
        metavar="REPO",
        dest="close_initiative",
        help="Close the open initiative for REPO (marks as met)",
    )
    # ── LLM-suggested initiatives (8.4) — also registered here so legacy parser accepts them ──
    parser.add_argument(
        "--suggest-initiatives",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="TARGET_TIER",
        dest="suggest_initiatives",
        help="LLM-rank repos closest to qualifying for TARGET_TIER (default: next tier from current)",
    )
    parser.add_argument(
        "--llm-budget",
        type=float,
        default=None,
        metavar="USD",
        dest="llm_budget",
        help="Override default LLM cost ceiling for --suggest-initiatives (default $0.10)",
    )
    # ── Accept suggestion (9.1) — also registered here so legacy parser accepts it ──
    parser.add_argument(
        "--accept-suggestion",
        type=str,
        default=None,
        metavar="REPO",
        dest="accept_suggestion",
        help="Convert a suggestion into an initiative (creates an initiatives.json entry)",
    )
    # ── Dismiss suggestion (11.4) — also registered here so legacy parser accepts them ──
    parser.add_argument(
        "--dismiss-suggestion",
        type=str,
        default=None,
        metavar="REPO",
        help="Suppress repo from future LLM-suggested initiatives",
    )
    parser.add_argument(
        "--reason",
        type=str,
        default="",
        help="Reason for dismissal (used with --dismiss-suggestion)",
    )
    parser.add_argument(
        "--undo-dismiss",
        type=str,
        default=None,
        metavar="REPO",
        help="Restore a dismissed repo to the suggestion pool",
    )
    parser.add_argument(
        "--list-dismissed",
        action="store_true",
        help="List currently dismissed suggestion repos",
    )
    # ── Auto-expire + audit trail (12.1) — also registered here so legacy parser accepts them ──
    parser.add_argument(
        "--dismiss-expires-days",
        type=int,
        default=None,
        metavar="N",
        help="Auto-expire dismissal after N days (default: permanent)",
    )
    parser.add_argument(
        "--expire-dismissals",
        action="store_true",
        help="Run cleanup: remove dismissals whose expiry date has passed",
    )
    parser.add_argument(
        "--dismissal-history",
        action="store_true",
        help="Show audit trail of dismissal events",
    )
    return parser


def _build_security_burndown_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Subcommand: `audit security-burndown` — ranked fixable-vuln burndown."""
    p = subparsers.add_parser(
        "security-burndown",
        help="Ranked list of fixable prod-reachable critical/high Dependabot advisories",
        description=(
            "Load the latest GHAS alert file for a user and produce a ranked burndown\n"
            "of fixable runtime-scope critical/high Dependabot advisories.\n\n"
            "Requires a prior `audit report <username> --ghas-alerts` run that captured\n"
            "per-alert detail (fetch with an up-to-date version of this tool)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("username", help="GitHub username whose GHAS file to load")
    p.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing ghas-alerts-<username>-*.json (default: output/)",
    )


def _build_security_gate_subparser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Subcommand: `audit security-gate` — fail on portfolio high/critical drift."""
    p = subparsers.add_parser(
        "security-gate",
        help="Fail if portfolio truth has open high/critical Dependabot alerts",
        description=(
            "Read output/portfolio-truth-latest.json and fail if any scanned repo has\n"
            "open high/critical Dependabot alerts. Missing security overlay data is\n"
            "reported as unknown and exits nonzero."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing portfolio-truth-latest.json (default: output/)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of Markdown",
    )
    p.add_argument(
        "--max-age-hours",
        type=int,
        default=None,
        help="Fail as stale when portfolio-truth generated_at is older than this many hours",
    )


def build_subcommand_parser() -> argparse.ArgumentParser:
    """Return the subcommand-aware parser used by main().

    This parser is separate from build_parser() so that existing tests that
    call build_parser().parse_args(["testuser", ...]) continue to work
    unchanged.  main() uses this parser exclusively when sys.argv[1] is one of
    the known subcommands; otherwise it rewrites the legacy argv and then
    dispatches through this parser too (see _rewrite_legacy_argv).
    """
    parser = argparse.ArgumentParser(
        prog="audit",
        description=CLI_MODE_GUIDE,
        epilog=CLI_MODE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="_subcommand",
        metavar="SUBCOMMAND",
        title="subcommands",
        description=(
            "Use a subcommand for the preferred invocation form. "
            "Legacy flat-flag invocation still works but emits a DeprecationWarning."
        ),
    )
    _build_run_subparser(subparsers)
    _build_triage_subparser(subparsers)
    _build_report_subparser(subparsers)
    _build_serve_subparser(subparsers)
    _build_security_burndown_subparser(subparsers)
    _build_security_gate_subparser(subparsers)
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


def _legacy_report_from_dict(data: dict) -> AuditReport:
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
    report = _apply_portfolio_catalog(report, args)
    report = _enrich_report_with_operator_state(
        report,
        output_dir=output_dir,
        diff_dict=diff_dict,
        triage_view=getattr(args, "triage_view", "all"),
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    return report_path, diff_dict or {}, report


def _enrich_control_center_snapshot_from_report(
    report_data: dict,
    snapshot: dict,
    args,
) -> dict:
    from src.portfolio_catalog import (
        DEFAULT_CATALOG_PATH,
        build_catalog_line,
        catalog_entry_for_repo,
        evaluate_intent_alignment,
        load_portfolio_catalog,
    )
    from src.report_enrichment import build_operator_focus

    report = _report_from_dict(
        {
            **report_data,
            "operator_summary": snapshot.get("operator_summary", {}),
            "operator_queue": snapshot.get("operator_queue", []),
        }
    )
    catalog_path = getattr(args, "catalog", None) or DEFAULT_CATALOG_PATH
    catalog_data = load_portfolio_catalog(Path(catalog_path))
    queue_by_repo = {
        str(item.get("repo") or item.get("repo_name") or "").strip(): item
        for item in report.operator_queue
        if str(item.get("repo") or item.get("repo_name") or "").strip()
    }
    for audit in report.audits:
        if (audit.portfolio_catalog or {}).get("has_explicit_entry"):
            continue
        base_entry = catalog_entry_for_repo(audit.metadata.to_dict(), catalog_data)
        if not base_entry.get("has_explicit_entry"):
            continue
        operator_focus = build_operator_focus(queue_by_repo.get(audit.metadata.name, {}))
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
    if any(audit.portfolio_catalog for audit in report.audits):
        audit_lookup = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
        for item in report.operator_queue:
            repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
            catalog_entry = audit_lookup.get(repo_name, {})
            if catalog_entry:
                item["portfolio_catalog"] = dict(catalog_entry)
                item["catalog_line"] = catalog_entry.get("catalog_line", "")
                item["intent_alignment"] = catalog_entry.get("intent_alignment", "missing-contract")
                item["intent_alignment_reason"] = catalog_entry.get("intent_alignment_reason", "")
    else:
        report = _apply_portfolio_catalog(report, args)
    report = _apply_scorecards(report, args)
    report = _apply_operating_paths(report)
    snapshot["operator_summary"] = report.operator_summary
    snapshot["operator_queue"] = report.operator_queue
    return snapshot


def _refresh_shared_artifacts_from_report(
    report: AuditReport,
    output_dir: Path,
    args,
    *,
    diff_dict: dict | None = None,
) -> dict[str, Path]:
    from src.excel_export import export_excel
    from src.history import load_repo_score_history, load_trend_data
    from src.review_pack import export_review_pack
    from src.warehouse import write_warehouse_snapshot
    from src.web_export import export_html_dashboard

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
        truth_dir=output_dir,
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
    snapshot = {
        "operator_summary": report.operator_summary,
        "operator_queue": report.operator_queue,
    }
    control_json, control_md, weekly_json, weekly_md, _control_payload = (
        _write_control_center_artifacts(
            report.to_dict(),
            snapshot,
            output_dir,
            username=report.username,
            generated_at=artifact_generated_at,
            report_reference=str(json_path),
            diff_dict=diff_dict,
        )
    )
    report.operator_summary["control_center_reference"] = str(control_json)
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


def _run_control_center_mode(args, parser) -> None:
    from src.diff import diff_reports
    from src.governance_activation import build_governance_summary
    from src.history import find_previous
    from src.operator_control_center import build_operator_snapshot, normalize_review_state

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
    snapshot = _enrich_control_center_snapshot_from_report(normalized, snapshot, args)
    artifact_generated_at = _report_artifact_datetime(
        report_path,
        _parse_iso_dt(normalized.get("generated_at")) or datetime.now(timezone.utc),
    )
    json_artifact, md_artifact, weekly_json, weekly_md, payload = _write_control_center_artifacts(
        normalized,
        snapshot,
        output_dir,
        username=normalized.get("username", args.username),
        generated_at=artifact_generated_at,
        report_reference=str(report_path),
        diff_dict=diff_dict,
    )
    weekly_digest = payload.get("weekly_command_center_digest_v1", {})
    source_freshness = weekly_digest.get("source_freshness", {})
    if source_freshness.get("status") and source_freshness.get("status") != "current":
        print_info(weekly_digest.get("headline") or "Refresh the audit report before acting.")
        print_info(
            source_freshness.get("summary")
            or "Control-center source freshness could not be proven."
        )
        print_info(weekly_digest.get("decision") or "Refresh the audit report, then rerun.")
    else:
        _print_control_center_summary(snapshot)
    print_info(f"Control center JSON: {json_artifact}")
    print_info(f"Control center Markdown: {md_artifact}")
    print_info(f"Weekly command center JSON: {weekly_json}")
    print_info(f"Weekly command center Markdown: {weekly_md}")
    print_info(_control_center_next_step_hint())


def _run_approval_center_mode(args, parser) -> None:
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
    print_info(
        payload.get("approval_workflow_summary", {}).get(
            "summary", "No current approval needs review yet."
        )
    )
    print_info(
        payload.get("next_approval_review", {}).get(
            "summary", "Stay local for now; no current approval needs review."
        )
    )
    print_info(f"Approval center JSON: {approval_json}")
    print_info(f"Approval center Markdown: {approval_md}")

    # ── Post-process: update suppression hints ────────────────────────────────
    _post_process_approval_center_prefs(payload, report_output_dir)


def _post_process_approval_center_prefs(payload: dict, output_dir: Path) -> None:
    """Build rejection records from the approval ledger and update operator_prefs.json."""
    from src.operator_prefs import (
        load_rejection_events,
        post_process_approval_session,
    )

    try:
        rejection_records = load_rejection_events(output_dir)
        total, newly_added = post_process_approval_session(
            rejection_records,
            output_dir,
        )
        print_info(f"Suppressions: {total} action type(s) suppressed ({newly_added} newly added).")
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "operator_prefs post-process failed (non-fatal): %s", exc
        )


def _run_approval_capture_mode(args, parser) -> None:
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
    ledger = {
        str(item.get("approval_id") or ""): item for item in bundle.get("approval_ledger", [])
    }
    if args.approve_governance or args.review_governance:
        approval_id = f"governance:{args.governance_scope}"
    else:
        approval_id = f"campaign:{args.campaign}"
    ledger_record = ledger.get(approval_id)
    if not ledger_record:
        parser.error("No matching approval subject is surfaced in the latest report.")

    if args.approve_governance or args.approve_packet:
        if ledger_record.get("approval_state") == "blocked":
            parser.error(
                "That approval subject is blocked by non-approval prerequisites and cannot be approved yet."
            )
        if ledger_record.get("approval_state") == "not-applicable":
            parser.error("That approval subject is not part of the current approval workflow.")
        approval_record = build_approval_record(
            ledger_record,
            reviewer=args.approval_reviewer,
            note=args.approval_note or "",
        )
        save_approval_record(report_output_dir, approval_record)
    else:
        if ledger_record.get("approval_state") in {
            "ready-for-review",
            "needs-reapproval",
            "blocked",
            "not-applicable",
        }:
            parser.error(
                "That approval subject is not currently eligible for a recurring local follow-up review."
            )
        if str(ledger_record.get("follow_up_command") or "").strip() == "":
            parser.error(
                "That approval subject does not currently expose a follow-up review command."
            )
        followup_event = build_approval_followup_record(
            ledger_record,
            reviewer=args.approval_reviewer,
            note=args.approval_note or "",
        )
        save_approval_followup_event(report_output_dir, followup_event)

    _report_path, diff_dict, report = _refresh_latest_report_state(report_output_dir, args)
    _refresh_shared_artifacts_from_report(report, report_output_dir, args, diff_dict=diff_dict)
    approval_json, approval_md, _payload = _write_approval_center_artifacts(
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
        (
            item
            for item in updated_bundle.get("approval_ledger", [])
            if item.get("approval_id") == approval_id
        ),
        ledger_record,
    )
    if args.approve_governance or args.approve_packet:
        receipt_payload = {**updated_record, **approval_record}
        receipt_json, receipt_md = _write_approval_receipt(
            report_output_dir,
            report.username,
            generated_at=_utcnow(),
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
            generated_at=_utcnow(),
            receipt=receipt_payload,
        )
        print_info(receipt_payload.get("summary", "Local follow-up review captured."))
        print_info(f"Approval follow-up receipt JSON: {receipt_json}")
        print_info(f"Approval follow-up receipt Markdown: {receipt_md}")
    print_info(f"Approval center JSON: {approval_json}")
    print_info(f"Approval center Markdown: {approval_md}")


def _run_acknowledgment_capture_mode(args, parser) -> None:
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

    if not args.acknowledge_target:
        parser.error("--acknowledge-target is required for acknowledgment capture")
    if not args.acknowledge_kind:
        parser.error("--acknowledge-kind is required for acknowledgment capture")
    if not (args.acknowledge_note or "").strip():
        parser.error("--acknowledge-note is required and must explain the acknowledgment")

    output_dir = Path(args.output_dir)
    report_path, report_data = _load_latest_report(output_dir)
    if not report_path or not report_data:
        parser.error("No existing audit report found in output directory")

    diff_dict: dict | None = None
    previous_path = find_previous(report_path.name)
    if previous_path:
        diff_dict = diff_reports(
            previous_path,
            report_path,
            portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        ).to_dict()

    material_changes = evaluate_material_changes(
        report_data,
        diff_data=diff_dict,
        thresholds=MATERIALITY_THRESHOLDS["standard"],
    )
    acknowledgments = load_acknowledgments(output_dir, args.username)
    matched = find_matching_change(
        repo_name=args.acknowledge_target,
        change_kind=args.acknowledge_kind,
        material_changes=material_changes,
        acknowledgments=acknowledgments,
    )
    if not matched:
        parser.error(
            f"No open '{args.acknowledge_kind}' change found for "
            f"'{args.acknowledge_target}' in the latest report"
        )

    reviewer = args.acknowledge_reviewer or args.approval_reviewer
    record = build_acknowledgment_record(matched, reviewer=reviewer, note=args.acknowledge_note)
    saved_path = save_acknowledgment(output_dir, args.username, record)

    print_info(
        f"Acknowledged {args.acknowledge_kind} for {args.acknowledge_target} "
        f"(change_key={record['change_key'][:12]}…, reviewer={reviewer})"
    )

    for sibling in find_sibling_changes(matched, material_changes):
        sibling_record = build_acknowledgment_record(
            sibling, reviewer=reviewer, note=args.acknowledge_note
        )
        save_acknowledgment(output_dir, args.username, sibling_record)
        print_info(
            f"Acknowledged sibling {sibling.get('change_type')} for "
            f"{sibling.get('repo_name')} "
            f"(change_key={sibling_record['change_key'][:12]}…)"
        )

    print_info(f"Acknowledgment store: {saved_path}")
    print_info("Run --control-center to confirm the item is filtered from the queue.")


def _run_doctor_mode(args, config_inspection) -> None:
    from src.app.doctor import run_doctor_mode

    run_doctor_mode(args, config_inspection)


def _run_generate_manifest_mode(args, parser) -> None:
    from src.repo_improver import generate_manifest, write_manifest

    output_dir = Path(args.output_dir)
    _report_path, report_data = _load_latest_report(output_dir)
    if not report_data:
        parser.error("No existing audit report found in output directory")
    manifest = generate_manifest(report_data)
    manifest_path = write_manifest(manifest, output_dir)
    print_info(f"Improvement manifest: {manifest_path} ({len(manifest)} repos)")


def _run_campaign_from_ledger_mode(args) -> None:
    """Dispatch for --campaign-from-ledger [--writeback-apply] [--dry-run].

    Loads approved campaign-plan packets from the ledger and executes each
    action via the existing apply executor map.  Dry-run mode prints what would
    be executed without calling the GitHub API.
    """
    from src.cache import ResponseCache
    from src.github_client import GitHubClient
    from src.plan_campaign import (
        dispatch_action,
        load_approved_campaign_plans,
        mark_campaign_applied,
        record_campaign_apply_failure,
    )

    output_dir = Path(args.output_dir)
    dry_run = getattr(args, "dry_run", False)
    username = getattr(args, "username", "") or ""

    cache = None if args.no_cache else ResponseCache()
    client = GitHubClient(token=args.token, cache=cache)

    packets = load_approved_campaign_plans(output_dir)

    if not packets:
        print_info("campaign-from-ledger: 0 approved packets found — nothing to apply.")
        return

    verb = "preview" if dry_run else "apply"
    print_info(f"campaign-from-ledger: {len(packets)} approved packet(s) to {verb}.")

    for packet in packets:
        print_info(f"  packet goal: {packet.goal[:80]!r} ({len(packet.actions)} actions)")

        action_results: list[tuple[bool, str]] = []
        for action in packet.actions:
            # 7B.5 — only dispatch actions that have been explicitly approved;
            # skip pending and rejected actions.
            action_state = getattr(action, "state", "pending") or "pending"
            if action_state != "approved":
                skip_label = "rejected" if action_state == "rejected" else "pending"
                print_info(f"    [skip:{skip_label}] {action.action_type} {action.repo_name}")
                action_results.append((True, f"skipped ({skip_label})"))
                continue

            if dry_run:
                # Dry-run: print preview, record as success for state purposes
                msg = (
                    f"would execute: {action.action_type} {action.repo_name}"
                    f" (target={action.target!r}, rationale={action.rationale[:60]!r})"
                )
                print_info(f"    [dry-run] {msg}")
                action_results.append((True, msg))
            else:
                ok, msg = dispatch_action(
                    action,
                    client=client,
                    owner=username,
                    dry_run=False,
                )
                status = "ok" if ok else "FAIL"
                print_info(f"    [{status}] {action.action_type} {action.repo_name}: {msg}")
                action_results.append((ok, msg))

        if dry_run:
            # Do not mutate ledger state on dry-run
            continue

        # 7B.5 — only mark applied when every action is terminal (approved+applied or rejected).
        # If any action is still pending, leave as approved-manual for the operator to revisit.
        has_pending = any(
            (getattr(a, "state", "pending") or "pending") == "pending" for a in packet.actions
        )
        if has_pending:
            print_info(
                "  packet kept approved-manual — some actions still pending per-action review"
            )
            continue

        # Determine overall packet success:
        # "applied" only when every supported action succeeded AND every
        # unsupported/pending action is in the packet as pending_human_action.
        # Mixed-result packets (a supported action failed) stay approved-manual
        # with a failure event listing the failed actions.
        supported_results = [
            (ok, msg)
            for (ok, msg), action in zip(action_results, packet.actions)
            if action.action_type
            not in ("pending_human_action", "add_license", "add_codeowners", "enable_dependabot")
            and (getattr(action, "state", "pending") or "pending") != "rejected"
        ]
        unsupported_results = [
            (ok, msg)
            for (ok, msg), action in zip(action_results, packet.actions)
            if action.action_type in ("add_license", "add_codeowners", "enable_dependabot")
        ]

        # Unimplemented-handler actions are expected failures — don't penalise the packet
        # as long as no genuinely-supported action failed.
        failed_supported = [(ok, msg) for ok, msg in supported_results if not ok]

        if not failed_supported:
            mark_campaign_applied(packet, output_dir)
            print_info(
                f"  packet marked applied "
                f"(supported={len(supported_results)}, skipped={len(unsupported_results)})"
            )
        else:
            error_summary = "; ".join(msg for _, msg in failed_supported)
            record_campaign_apply_failure(packet, error_summary, output_dir)
            print_info(
                f"  packet kept approved-manual — {len(failed_supported)} failure(s): {error_summary[:120]}"
            )


def _run_plan_campaign_mode(args) -> None:
    """Dispatch for --plan-campaign: generate a goal-driven campaign plan packet."""
    from src.approval_ledger import default_approval_reviewer as _default_reviewer
    from src.llm_cost import BudgetExceededError, CostTracker
    from src.narrative import _resolve_provider
    from src.operator_prefs import load_prefs, prefs_path
    from src.plan_campaign import generate_plan, narrow_candidates, write_packet_to_ledger
    from src.warehouse import WAREHOUSE_FILENAME

    output_dir = Path(args.output_dir)
    goal: str = str(args.plan_campaign).strip()
    max_repos: int = int(getattr(args, "max_repos", 50) or 50)
    reviewer: str = getattr(args, "approval_reviewer", None) or _default_reviewer()

    # ── Load audit results from portfolio-truth-latest.json ───────────────────
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_info(
            f"portfolio-truth-latest.json not found in {output_dir}. "
            "Run `audit report --portfolio-truth` first to generate repo data. "
            "--plan-campaign requires a truth snapshot to select candidates."
        )
        return

    try:
        raw = json.loads(truth_path.read_text(encoding="utf-8"))
        audit_results: list[dict] = list(raw.get("repos", raw.get("results", [])))
    except (OSError, json.JSONDecodeError) as exc:
        print_info(f"Error reading portfolio-truth-latest.json: {exc}")
        return

    # ── Semantic index (optional — fallback to alphabetical if unavailable) ────
    semantic_index = None
    warehouse_path = output_dir / WAREHOUSE_FILENAME
    if warehouse_path.exists():
        try:
            from src.semantic_index import SemanticIndex

            semantic_index = SemanticIndex(output_dir)
        except Exception as exc:  # noqa: BLE001
            print_info(
                f"Warning: could not load SemanticIndex: {exc} — using alphabetical fallback."
            )

    # ── LLM provider ──────────────────────────────────────────────────────────
    provider_result = _resolve_provider(
        getattr(args, "narrative_provider", None),
        getattr(args, "narrative_model", None),
        getattr(args, "token", None),
    )
    if provider_result is None:
        print_info(
            "No LLM provider available for --plan-campaign. "
            "Set ANTHROPIC_API_KEY or GITHUB_TOKEN, or pass --narrative-provider."
        )
        return
    provider, model = provider_result

    # ── Cost tracker ──────────────────────────────────────────────────────────
    budget_usd = getattr(args, "max_llm_spend", None)
    cost_tracker: CostTracker = CostTracker(budget_usd=budget_usd, output_path=output_dir)

    # ── Operator prefs ────────────────────────────────────────────────────────
    pref_file = prefs_path(output_dir)
    prefs = load_prefs(pref_file)

    # ── Narrow candidates ─────────────────────────────────────────────────────
    candidates = narrow_candidates(
        audit_results,
        goal=goal,
        semantic_index=semantic_index,
        max_repos=max_repos,
    )
    if not candidates:
        print_info("No candidate repos found. Check that portfolio-truth-latest.json has data.")
        return

    # ── Generate plan ─────────────────────────────────────────────────────────
    import sys

    try:
        packet = generate_plan(
            candidates,
            goal=goal,
            provider=provider,
            model=model,
            cost_tracker=cost_tracker,
            prefs=prefs,
        )
    except BudgetExceededError as exc:
        print(f"\nERROR: LLM budget exceeded during campaign planning: {exc}", file=sys.stderr)
        return

    # ── Persist packet to ledger ──────────────────────────────────────────────
    record_id = write_packet_to_ledger(packet, output_dir=output_dir, reviewer=reviewer)

    cost_tracker.write_telemetry()

    pending_count = sum(1 for a in packet.actions if a.action_type == "pending_human_action")
    print_info(
        f"Goal: {goal}. "
        f"Considered {packet.candidate_count}. "
        f"Qualified {packet.qualified_count}. "
        f"{pending_count} pending human review. "
        f"LLM cost: ${packet.llm_cost_usd:.4f}. "
        f"Packet ID: {record_id}."
    )


def _run_draft_readmes_mode(args) -> None:
    """Dispatch for --draft-readmes: generate LLM-authored README draft packets."""
    import sys

    from src.approval_ledger import default_approval_reviewer as _default_reviewer
    from src.draft_readmes import (
        build_context,
        generate_draft,
        qualify_repos,
        write_packets_to_ledger,
    )
    from src.llm_cost import BudgetExceededError, CostTracker
    from src.narrative import _resolve_provider
    from src.operator_prefs import (
        is_suppressed,
        load_prefs,
        post_process_approval_session,
        prefs_path,
    )

    output_dir = Path(args.output_dir)
    opt_in_repos: list[str] = list(getattr(args, "draft_readmes_repos", None) or [])
    all_qualifying: bool = bool(getattr(args, "draft_readmes_all", False))
    reviewer: str = getattr(args, "approval_reviewer", None) or _default_reviewer()

    if not opt_in_repos and not all_qualifying:
        print_info(
            "--draft-readmes requires --draft-readmes-all or at least one --draft-readmes-repo. "
            "No repos selected."
        )
        return

    # ── Load audit results (portfolio-truth-latest.json or warehouse) ─────────
    audit_results: list[dict] = []
    truth_path = truth_latest_path(output_dir)
    if truth_path.exists():
        try:
            raw = json.loads(truth_path.read_text(encoding="utf-8"))
            audit_results = list(raw.get("repos", raw.get("results", [])))
        except (OSError, json.JSONDecodeError) as exc:
            print_info(f"Warning: could not read portfolio-truth-latest.json: {exc}")
    else:
        print_info(
            f"portfolio-truth-latest.json not found in {output_dir}. "
            "Run `audit report --portfolio-truth` first to populate repo data. "
            "Proceeding with empty repo list — only explicit --draft-readmes-repo repos will be drafted."
        )

    # ── Qualify repos ──────────────────────────────────────────────────────────
    repo_names = qualify_repos(
        audit_results, opt_in_repos=opt_in_repos, all_qualifying=all_qualifying
    )
    if not repo_names:
        print_info("No repos qualify for --draft-readmes with current flags.")
        return

    # Build a name → dict lookup for fast access
    repo_by_name: dict[str, dict] = {
        str(r.get("repo_name") or r.get("name") or ""): r for r in audit_results
    }
    # Repos requested via --draft-readmes-repo may not exist in audit_results — create stubs
    for name in repo_names:
        if name not in repo_by_name:
            repo_by_name[name] = {"repo_name": name, "name": name}

    # ── Semantic index (optional — proceed without neighbors if unavailable) ────
    semantic_index = None
    warehouse_path = output_dir / "portfolio-warehouse.db"
    if warehouse_path.exists():
        try:
            from src.semantic_index import SemanticIndex

            semantic_index = SemanticIndex(output_dir)
        except Exception as exc:  # noqa: BLE001
            print_info(
                f"Warning: could not load SemanticIndex: {exc} — proceeding without neighbors."
            )

    # ── LLM provider ──────────────────────────────────────────────────────────
    provider_result = _resolve_provider(
        getattr(args, "narrative_provider", None),
        getattr(args, "narrative_model", None),
        getattr(args, "token", None),
    )
    if provider_result is None:
        print_info(
            "No LLM provider available for --draft-readmes. "
            "Set ANTHROPIC_API_KEY or GITHUB_TOKEN, or pass --narrative-provider."
        )
        return
    provider, model = provider_result

    # ── Cost tracker ──────────────────────────────────────────────────────────
    cost_tracker: CostTracker | None = None
    budget_usd = getattr(args, "max_llm_spend", None)
    if budget_usd is not None or True:  # always track telemetry
        cost_tracker = CostTracker(budget_usd=budget_usd, output_path=output_dir)

    # ── Operator prefs ────────────────────────────────────────────────────────
    pref_file = prefs_path(output_dir)
    prefs = load_prefs(pref_file)

    # ── Main loop ─────────────────────────────────────────────────────────────
    packets = []
    skipped_suppressed = 0
    skipped_budget = 0
    errors = 0

    for repo_name in repo_names:
        # 5.3 — suppression check
        if is_suppressed(prefs, action_type="draft-readme", target_context=repo_name):
            print_info(f"  skip {repo_name}: suppressed by operator prefs")
            skipped_suppressed += 1
            continue

        repo = repo_by_name[repo_name]
        context = build_context(repo, semantic_index=semantic_index)

        try:
            packet = generate_draft(
                repo, context=context, provider=provider, model=model, cost_tracker=cost_tracker
            )
            packets.append(packet)
            print_info(f"  drafted {repo_name} ({packet.diff_summary})")
        except BudgetExceededError as exc:
            print(f"\nERROR: LLM budget exceeded at {repo_name}: {exc}", file=sys.stderr)
            skipped_budget = len(repo_names) - len(packets) - skipped_suppressed - 1
            break
        except Exception as exc:  # noqa: BLE001
            print_info(f"  error drafting {repo_name}: {exc}")
            errors += 1

    # ── Persist packets ────────────────────────────────────────────────────────
    if packets:
        write_packets_to_ledger(packets, output_dir, reviewer)

    # ── Refresh suppressions from rejection history ────────────────────────────
    # We pass an empty list here — newly-generated drafts have no decision yet,
    # so detect_suppressions would find zero consecutive rejections. The real
    # suppression update happens when the operator rejects via approval_request_reject.
    # Calling post_process_approval_session with [] is a no-op but keeps the prefs
    # file consistent and auto-prunes stale hints if any exist.
    if pref_file.parent.exists():
        try:
            post_process_approval_session([], output_dir)
        except Exception as exc:  # noqa: BLE001
            print_info(f"Warning: could not refresh suppression hints: {exc}")

    if cost_tracker is not None:
        cost_tracker.write_telemetry()

    total_cost = cost_tracker.total_usd() if cost_tracker is not None else 0.0
    print_info(
        f"Drafted {len(packets)} packet(s) for {len(packets)} repo(s). "
        f"{skipped_suppressed} skipped (prefs). "
        f"{skipped_budget} skipped (budget). "
        f"{errors} error(s). "
        f"LLM cost: ${total_cost:.4f}."
    )


def _run_set_initiative_mode(args) -> None:
    """Validate and persist a tier-upgrade initiative for a repo."""
    import sys
    from datetime import date

    from src.initiatives import (
        Initiative,
        initiatives_path,
        operator_identity,
        upsert_initiative,
    )
    from src.maturity_tiers import TIER_DEFINITIONS, compute_tier

    repo_name: str = args.set_initiative
    target_tier: int | None = getattr(args, "target_tier", None)
    deadline_str: str | None = getattr(args, "deadline", None)
    output_dir = Path(args.output_dir)

    # Validate required co-flags
    if target_tier is None:
        print_warning("--target-tier is required with --set-initiative (choices: 2, 3, 4)")
        sys.exit(2)
    if deadline_str is None:
        print_warning("--deadline YYYY-MM-DD is required with --set-initiative")
        sys.exit(2)

    # Validate deadline format and future-ness
    try:
        deadline_date = date.fromisoformat(deadline_str)
    except ValueError:
        print_warning(f"--deadline must be YYYY-MM-DD, got: {deadline_str!r}")
        sys.exit(2)
    if deadline_date < date.today():
        print_warning(f"--deadline {deadline_str} is in the past. Provide a future date.")
        sys.exit(2)

    # Load portfolio-truth to validate repo and check current tier
    import json as _json

    pt_candidates = sorted(output_dir.glob(TRUTH_LATEST_FILENAME))
    if not pt_candidates:
        pt_candidates = sorted(output_dir.glob("portfolio-truth-*.json"))
    if not pt_candidates:
        print_warning(
            f"Portfolio truth not found in {output_dir}. "
            "Run `audit report --portfolio-truth` first."
        )
        sys.exit(2)

    pt_path = truth_latest_path(output_dir)
    if not pt_path.exists():
        pt_path = pt_candidates[-1]

    try:
        pt_data = _json.loads(pt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print_warning(f"Could not read portfolio truth: {exc}")
        sys.exit(2)

    projects: list[dict] = pt_data.get("projects", [])
    repo_dict: dict | None = None
    for proj in projects:
        name = proj.get("identity", {}).get("display_name", "")
        if name.lower() == repo_name.lower():
            repo_dict = proj
            break

    if repo_dict is None:
        print_warning(
            f"Repo {repo_name!r} not found in portfolio truth. "
            "Run `audit report --portfolio-truth` first."
        )
        sys.exit(2)

    current_tier = compute_tier(repo_dict)
    if target_tier <= current_tier:
        tier_name_target = TIER_DEFINITIONS[target_tier].name
        tier_name_current = TIER_DEFINITIONS[current_tier].name if current_tier > 0 else "Untracked"
        print_warning(
            f"Target tier {target_tier} ({tier_name_target}) is not greater than "
            f"current tier {current_tier} ({tier_name_current}) for {repo_name!r}."
        )
        sys.exit(2)

    from datetime import datetime as _dt
    from datetime import timezone as _tz

    initiative = Initiative(
        repo_name=repo_name,
        target_tier=target_tier,
        deadline=deadline_str,
        set_at=_dt.now(tz=_tz.utc).isoformat(),
        set_by=operator_identity(),
    )
    upsert_initiative(initiatives_path(output_dir), initiative)
    tier_label = TIER_DEFINITIONS[target_tier].name
    print_info(f"Initiative set: {repo_name} → Tier {target_tier} ({tier_label}) by {deadline_str}")


def _run_list_initiatives_mode(args) -> None:
    """Print a status table for all initiatives."""
    import json as _json

    from src.initiatives import derive_status, initiatives_path, load_initiatives
    from src.maturity_tiers import TIER_DEFINITIONS, compute_tier, tier_name

    output_dir = Path(args.output_dir)
    path = initiatives_path(output_dir)
    initiatives = load_initiatives(path)

    # Load portfolio-truth for current-tier lookup (best-effort)
    projects_by_name: dict[str, dict] = {}
    pt_path = truth_latest_path(output_dir)
    if pt_path.exists():
        try:
            pt_data = _json.loads(pt_path.read_text(encoding="utf-8"))
            for proj in pt_data.get("projects", []):
                name = proj.get("identity", {}).get("display_name", "")
                if name:
                    projects_by_name[name.lower()] = proj
        except (OSError, ValueError):
            # Initiative listing can proceed without portfolio-truth tier context.
            pass

    open_initiatives = [i for i in initiatives if i.closed_at is None]
    closed_initiatives = [i for i in initiatives if i.closed_at is not None]

    print_info("Initiative Tracker")
    print_info("══════════════════")

    if not open_initiatives:
        print_info("No open initiatives.")
    else:
        header = f"{'REPO':<30} {'TARGET':<12} {'CURRENT':<12} {'DEADLINE':<12} {'STATUS'}"
        print_info(header)
        print_info("-" * len(header))
        for initiative in open_initiatives:
            repo_dict = projects_by_name.get(initiative.repo_name.lower(), {})
            current = compute_tier(repo_dict) if repo_dict else 0
            status = derive_status(initiative, repo_dict)
            target_label = (
                f"{TIER_DEFINITIONS[initiative.target_tier].name}({initiative.target_tier})"
                if initiative.target_tier in TIER_DEFINITIONS
                else str(initiative.target_tier)
            )
            current_label = f"{tier_name(current)}({current})" if current > 0 else "Untracked"
            status_detail = status
            if status == "at-risk":
                from datetime import date

                try:
                    days_left = (date.fromisoformat(initiative.deadline) - date.today()).days
                    status_detail = f"at-risk (deadline ≤ {days_left}d)"
                except ValueError:
                    # Malformed deadlines keep the generic at-risk label.
                    pass
            elif status == "on-track":
                status_detail = "on-track"
            row = (
                f"{initiative.repo_name:<30} "
                f"{target_label:<12} "
                f"{current_label:<12} "
                f"{initiative.deadline:<12} "
                f"{status_detail}"
            )
            print_info(row)

    if closed_initiatives:
        print_info(f"\nClosed: {len(closed_initiatives)}")


def _run_close_initiative_mode(args) -> None:
    """Close the open initiative for a repo."""
    import sys

    from src.initiatives import close_initiative, initiatives_path

    repo_name: str = args.close_initiative
    output_dir = Path(args.output_dir)
    closed = close_initiative(initiatives_path(output_dir), repo_name, reason="met")
    if closed is None:
        print_warning(f"No open initiative found for {repo_name!r}.")
        sys.exit(2)
    print_info(
        f"Initiative closed: {repo_name} → Tier {closed.target_tier} "
        f"(reason: {closed.closed_reason}, closed_at: {closed.closed_at})"
    )


def _run_suggest_initiatives_mode(args) -> None:
    """LLM-rank repos closest to qualifying for their next maturity tier (Arc G S8.4)."""
    from pathlib import Path as _Path

    from src.llm_cost import BudgetExceededError
    from src.maturity_tiers import tier_name
    from src.suggest_initiatives import generate_suggestions

    truth_path = truth_latest_path(_Path(args.output_dir))
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. "
            "Run `audit triage USERNAME --portfolio-truth` first."
        )
        return

    truth = json.loads(truth_path.read_text())
    projects = truth.get("projects", [])

    # 0 is the const sentinel meaning "use per-repo next tier"
    target = args.suggest_initiatives if args.suggest_initiatives else None
    budget = args.llm_budget if args.llm_budget is not None else 0.10

    try:
        suggestions, cost = generate_suggestions(projects, target_tier=target, budget_usd=budget)
    except BudgetExceededError as exc:
        print(f"\nERROR: LLM budget exceeded: {exc}", file=sys.stderr)
        return

    if not suggestions:
        print_info("No suggestions: no repos are close to qualifying for the next tier.")
        return

    print_info(f"Suggested Initiatives ({len(suggestions)} candidates, ${cost:.4f} spent)")
    print()
    for s in suggestions:
        print(
            f"  {s.repo_name:<30} {tier_name(s.current_tier)} → {tier_name(s.target_tier):<10} "
            f"[{s.estimated_effort}]"
        )
        print(f"    Missing: {', '.join(s.missing_requirements)}")
        print(f"    Rationale: {s.rationale}")
        print()


def _run_accept_suggestion_mode(args) -> None:
    """Accept a suggestion: convert it into a tier-upgrade initiative (Arc G S9.1)."""
    import sys

    from src.suggest_initiatives import accept_suggestion

    output_dir = Path(args.output_dir)
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first."
        )
        return

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print_warning(f"Failed to read portfolio-truth: {exc}")
        return

    projects = truth.get("projects", [])

    try:
        initiative = accept_suggestion(
            repo_name=args.accept_suggestion,
            projects=projects,
            output_dir=output_dir,
            deadline=getattr(args, "deadline", None),
            target_tier=getattr(args, "target_tier", None),
        )
    except ValueError as exc:
        print_warning(str(exc))
        sys.exit(2)

    print_info(
        f"Initiative accepted: {initiative.repo_name} → "
        f"Tier {initiative.target_tier} by {initiative.deadline}"
    )


def _run_dismiss_suggestion_mode(args) -> None:
    """Dismiss a repo from future LLM-suggested initiatives (Arc G S11.4)."""
    import sys
    from pathlib import Path

    from src.suggest_initiatives import dismiss_suggestion_record, dismissed_path

    output_dir = Path(args.output_dir)
    try:
        entry = dismiss_suggestion_record(
            dismissed_path(output_dir),
            repo_name=args.dismiss_suggestion,
            reason=getattr(args, "reason", "") or "",
            expires_days=getattr(args, "dismiss_expires_days", None),
        )
    except ValueError as exc:
        print_warning(str(exc))
        sys.exit(2)
    expiry_note = f" (expires {entry.expires_at})" if entry.expires_at else ""
    print_info(
        f"✗ Dismissed: {entry.repo_name}"
        + (f" — {entry.reason}" if entry.reason else "")
        + expiry_note
    )


def _run_undo_dismiss_mode(args) -> None:
    """Restore a dismissed repo to the suggestion pool (Arc G S11.4)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, undo_dismiss

    output_dir = Path(args.output_dir)
    removed = undo_dismiss(dismissed_path(output_dir), args.undo_dismiss)
    if removed:
        print_info(f"✓ Restored: {args.undo_dismiss}")
    else:
        print_warning(f"{args.undo_dismiss} was not dismissed; nothing to undo")


def _run_list_dismissed_mode(args) -> None:
    """List all currently dismissed suggestion repos (Arc G S11.4)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, load_dismissed

    output_dir = Path(args.output_dir)
    items = load_dismissed(dismissed_path(output_dir))
    if not items:
        print_info("No dismissed suggestions.")
        return
    print_info(f"Dismissed Suggestions ({len(items)})")
    for d in items:
        reason = f" — {d.reason}" if d.reason else ""
        print(f"  {d.repo_name:<30} dismissed {d.dismissed_at[:10]} by {d.dismissed_by}{reason}")


def _run_expire_dismissals_mode(args) -> None:
    """Remove dismissals whose expiry date has passed (Arc G S12.1)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, expire_dismissals

    output_dir = Path(args.output_dir)
    expired = expire_dismissals(dismissed_path(output_dir))
    if not expired:
        print_info("No dismissals to expire.")
        return
    print_info(f"Expired {len(expired)} dismissal(s):")
    for d in expired:
        print(f"  {d.repo_name:<30} (was set to expire {d.expires_at})")


def _run_dismissal_history_mode(args) -> None:
    """Show audit trail of dismissal events (Arc G S12.1)."""
    from pathlib import Path

    from src.suggest_initiatives import dismissed_path, load_dismissal_events

    output_dir = Path(args.output_dir)
    events = load_dismissal_events(dismissed_path(output_dir))
    if not events:
        print_info("No dismissal history.")
        return
    print_info(f"Dismissal History ({len(events)} event(s))")
    for e in events:
        reason = f" — {e.reason}" if e.reason else ""
        print(f"  {e.occurred_at[:19]} {e.event_type:<10} {e.repo_name:<30} by {e.actor}{reason}")


def _run_tier_gaps_export_mode(args) -> None:
    """Dump per-repo tier-gap data as JSON or markdown (Arc G S12.4)."""
    from datetime import datetime, timezone
    from pathlib import Path

    from src.maturity_tiers import compute_tier, tier_gap, tier_name

    output_dir = Path(args.output_dir)
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first."
        )
        return

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print_warning(f"Failed to read portfolio-truth: {exc}")
        sys.exit(2)

    projects = truth.get("projects", [])
    target_override = getattr(args, "tier_gaps_target", None)
    if target_override is not None and target_override not in (2, 3, 4):
        print_warning(f"Invalid --tier-gaps-target {target_override}; must be 2, 3, or 4.")
        sys.exit(2)

    gaps: list[dict] = []
    for project in projects:
        name = (project.get("identity") or {}).get("display_name") or ""
        if not name:
            continue
        current = compute_tier(project)
        if current == 0 or current == 4:
            continue  # no-git or already-Platinum: no next tier
        target = target_override if target_override is not None else (current + 1)
        if target <= current:
            continue  # operator's override is below or equal to current
        gap = tier_gap(project, target)
        gaps.append(
            {
                "repo_name": name,
                "current_tier": current,
                "current_tier_name": tier_name(current),
                "target_tier": target,
                "target_tier_name": tier_name(target),
                "missing_requirements": list(gap.missing_requirements),
                "requirement_sources": list(gap.requirement_sources),
            }
        )

    fmt = getattr(args, "format", "json")
    if fmt == "markdown":
        _print_tier_gaps_markdown(gaps)
    else:
        envelope = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "gaps": gaps,
        }
        print(json.dumps(envelope, indent=2))


def _print_tier_gaps_markdown(gaps: list[dict]) -> None:
    """Human-readable tier-gap table (Arc G S12.4)."""
    if not gaps:
        print_info("No tier gaps to report (all repos either at Platinum or no git).")
        return
    print_info(f"Tier Gaps ({len(gaps)} repo(s))")
    print()
    print("| REPO | CURRENT → TARGET | MISSING | SOURCE |")
    print("|------|------------------|---------|--------|")
    for g in gaps:
        missing = ", ".join(g["missing_requirements"]) if g["missing_requirements"] else "—"
        sources = ", ".join(g["requirement_sources"]) if g["requirement_sources"] else "—"
        print(
            f"| {g['repo_name']} | {g['current_tier_name']} → {g['target_tier_name']} | {missing} | {sources} |"
        )


def _run_apply_improvements_mode(args, parser) -> None:
    from src.repo_improver import (
        apply_metadata_updates,
        apply_readme_updates,
        generate_execution_report,
        load_improvements,
    )

    improvements_file = getattr(args, "improvements_file", None)
    apply_readmes = getattr(args, "apply_readmes", False)
    apply_metadata = getattr(args, "apply_metadata", False)

    # --apply-metadata always needs a file; --apply-readmes can read from ledger instead.
    if apply_metadata and not improvements_file:
        parser.error("--apply-metadata requires --improvements-file")
    if not apply_readmes and not apply_metadata:
        parser.error("--apply-metadata / --apply-readmes requires --improvements-file")

    cache = None if args.no_cache else ResponseCache()
    client = GitHubClient(token=args.token, cache=cache)
    output_dir = Path(args.output_dir)
    dry_run = getattr(args, "dry_run", False)

    # Load file-based updates (may be empty if no file supplied)
    file_updates: list[dict] = []
    if improvements_file:
        file_updates = list(load_improvements(improvements_file).values())

    all_results: list[dict] = []

    if apply_metadata:
        results = apply_metadata_updates(client, args.username, file_updates, dry_run=dry_run)
        all_results.extend(results)
        ok_count = sum(
            1 for r in results for a in r.get("actions", []) if a.get("ok") or a.get("dry_run")
        )
        print_info(f"Metadata updates: {ok_count} actions {'previewed' if dry_run else 'applied'}")

    if apply_readmes:
        # Build the merged update list:
        #   1) file-based packets (if --improvements-file provided)
        #   2) approved ledger packets (if any, de-duplicated by repo name)
        readme_updates: list[dict] = list(file_updates)
        ledger_packets_by_repo: dict[str, object] = {}

        from src.draft_readmes import (
            assemble_readme_from_approved_sections,
            load_approved_drafts,
            load_approved_sectioned_packets,
            mark_draft_applied,
            mark_section_packet_applied,
            record_draft_apply_failure,
        )

        # ── Path A: per-section sub-records (Sprint 8.5) ─────────────────────
        sectioned_packets = load_approved_sectioned_packets(output_dir)
        sectioned_updates_by_repo: dict[str, tuple[str, str]] = {}  # repo → (packet_id, readme)
        for pid, sections in sectioned_packets.items():
            repo_name_sec: str = str((sections[0].get("repo_name") or "") if sections else "")
            if not repo_name_sec:
                continue
            assembled = assemble_readme_from_approved_sections(sections)
            if assembled is None:
                print_info(f"sectioned packet {pid} has no approved sections; skipping")
                continue
            pending = [s for s in sections if s.get("state", "pending") == "pending"]
            if pending:
                print_info(f"sectioned packet {pid} has {len(pending)} pending sections; skipping")
                continue
            sectioned_updates_by_repo[repo_name_sec] = (pid, assembled)

        for repo_name_sec, (pid, assembled_readme) in sectioned_updates_by_repo.items():
            file_names = {(u.get("name") or u.get("repo", "").split("/")[-1]) for u in file_updates}
            if repo_name_sec not in file_names:
                readme_updates.append({"name": repo_name_sec, "readme": assembled_readme})
                if dry_run:
                    char_count = len(assembled_readme)
                    print_info(
                        f"  [dry-run] would push sectioned README to {repo_name_sec}: "
                        f"{char_count} chars"
                    )

        # ── Path B: legacy whole-packet records ───────────────────────────────
        ledger_packets = load_approved_drafts(output_dir, getattr(args, "username", None))
        for pkt in ledger_packets:
            # Convert DraftReadmePacket → shape expected by apply_readme_updates
            # apply_readme_updates expects: {name: str, readme: str}
            # De-duplicate: file-based takes precedence (already present in readme_updates).
            file_names = {(u.get("name") or u.get("repo", "").split("/")[-1]) for u in file_updates}
            if pkt.repo_name not in file_names:
                readme_updates.append({"name": pkt.repo_name, "readme": pkt.proposed_readme})
                ledger_packets_by_repo[pkt.repo_name] = pkt

        if not readme_updates:
            print_info("README updates: 0 repos to apply (no file and no approved ledger packets).")
        else:
            if dry_run:
                # Print per-repo preview lines for ledger-sourced packets so the operator
                # can see what would be pushed.  File-based packets are also covered because
                # apply_readme_updates returns {"dry_run": True} records when dry_run=True.
                for pkt_repo, _pkt in ledger_packets_by_repo.items():
                    upd = next(
                        (
                            u
                            for u in readme_updates
                            if (u.get("name") or u.get("repo", "").split("/")[-1]) == pkt_repo
                        ),
                        None,
                    )
                    if upd is not None:
                        char_count = len(upd.get("readme", ""))
                        print_info(
                            f"  [dry-run] would push README to {pkt_repo}: {char_count} chars"
                        )

            results = apply_readme_updates(client, args.username, readme_updates, dry_run=dry_run)
            all_results.extend(results)

            # State transitions for ledger-sourced packets (live apply only)
            if not dry_run:
                for result in results:
                    repo_name = result.get("repo", "")
                    # Path A: sectioned packets
                    if repo_name in sectioned_updates_by_repo:
                        pid, _assembled = sectioned_updates_by_repo[repo_name]
                        if result.get("ok"):
                            mark_section_packet_applied(pid, output_dir)
                    # Path B: legacy whole-packet records
                    elif repo_name in ledger_packets_by_repo:
                        pkt = ledger_packets_by_repo[repo_name]
                        if result.get("ok"):
                            mark_draft_applied(output_dir, pkt, apply_result=result)  # type: ignore[arg-type]
                        else:
                            error_msg = str(result.get("error") or "unknown error")
                            record_draft_apply_failure(output_dir, pkt, error=error_msg)  # type: ignore[arg-type]

            ok_count = sum(1 for r in results if r.get("ok") or r.get("dry_run"))
            verb = "previewed" if dry_run else "pushed"
            print_info(
                f"README updates: {ok_count} repos {verb}"
                + (
                    f" ({len(ledger_packets_by_repo)} from ledger)"
                    if ledger_packets_by_repo
                    else ""
                )
            )

    report_path = generate_execution_report(all_results, output_dir)
    print_info(f"Execution report: {report_path}")


def _run_main_audit_cycle(args, config_inspection) -> None:
    from src.diagnostics import format_preflight_summary, run_diagnostics, should_block_run

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

    all_repos, errors = _fetch_repo_metadata(args, client)
    total_fetched = len(all_repos)
    repos = _filter_repos(
        all_repos,
        skip_forks=args.skip_forks,
        skip_archived=args.skip_archived,
    )
    _print_filter_summary(all_repos, repos, args)

    if getattr(args, "dry_run", False):
        _print_dry_run_summary(repos)
        return

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
                    # Skip corrupt resume entries and continue with the rest.
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
        _print_output_summary(
            f"Audited {report.repos_audited} repos for {report.username}", report, outputs
        )

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

    raw_path = _write_json(
        args.username,
        repos,
        errors,
        total_fetched,
        output_dir,
    )
    print(
        f"\n✓ Fetched {total_fetched} repos for {args.username}\n"
        f"  Included: {len(repos)} | Errors: {len(errors)}\n"
        f"  Output: {raw_path}",
    )


def _run_watch_mode(args, config_inspection) -> None:
    from src.recurring_review import choose_watch_plan
    from src.watch import run_watch_loop

    def _run_watch_once() -> None:
        watch_plan = choose_watch_plan(
            Path(args.output_dir),
            args,
            scoring_profile=normalize_scoring_profile(args.scoring_profile),
        )
        print_info(f"Watch decision: {watch_plan.mode} ({watch_plan.reason})")
        original_incremental = args.incremental
        original_repos = args.repos
        setattr(args, "_watch_plan", watch_plan)
        setattr(args, "_latest_trusted_watch_baseline", watch_plan.latest_trusted_baseline)
        try:
            args.incremental = watch_plan.mode == "incremental"
            args.repos = None
            _run_main_audit_cycle(args, config_inspection)
        finally:
            args.incremental = original_incremental
            args.repos = original_repos

    run_watch_loop(_run_watch_once, interval=args.watch_interval)


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
    print(
        f"\nOperator Control Center\n  {summary.get('headline', 'No operator triage items are currently surfaced.')}"
    )
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
        print(
            f"  Closure forecast reweighting summary: {summary['closure_forecast_reweighting_summary']}"
        )
    if summary.get("primary_target_closure_forecast_momentum_status"):
        print(
            "  Closure forecast momentum: "
            f"{summary.get('primary_target_closure_forecast_momentum_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_momentum_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_momentum_summary"):
        print(
            f"  Closure forecast momentum summary: {summary['closure_forecast_momentum_summary']}"
        )
    if summary.get("primary_target_closure_forecast_freshness_status"):
        print(
            "  Closure forecast freshness: "
            f"{summary.get('primary_target_closure_forecast_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_freshness_summary"):
        print(
            f"  Closure forecast freshness summary: {summary['closure_forecast_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_stability_status"):
        print(
            "  Closure forecast hysteresis: "
            f"{summary.get('primary_target_closure_forecast_stability_status', 'watch')} "
            f"({summary.get('primary_target_closure_forecast_hysteresis_status', 'none')}: "
            f"{summary.get('primary_target_closure_forecast_hysteresis_reason', 'No closure-forecast hysteresis reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_hysteresis_summary"):
        print(
            f"  Closure forecast hysteresis summary: {summary['closure_forecast_hysteresis_summary']}"
        )
    if summary.get("primary_target_closure_forecast_decay_status") not in {None, "", "none"}:
        print(
            "  Hysteresis decay controls: "
            f"{summary.get('primary_target_closure_forecast_decay_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_decay_summary"):
        print(f"  Closure forecast decay summary: {summary['closure_forecast_decay_summary']}")
    if summary.get("primary_target_closure_forecast_refresh_recovery_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Closure forecast refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_refresh_recovery_summary"):
        print(
            f"  Closure forecast refresh recovery summary: {summary['closure_forecast_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reacquisition_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reacquisition controls: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reacquisition_summary"):
        print(
            f"  Closure forecast reacquisition summary: {summary['closure_forecast_reacquisition_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reacquisition_persistence_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reacquisition persistence: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reacquisition_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reacquisition_persistence_summary"):
        print(
            f"  Reacquisition persistence summary: {summary['closure_forecast_reacquisition_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_recovery_churn_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Recovery churn controls: "
            f"{summary.get('primary_target_closure_forecast_recovery_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_recovery_churn_summary"):
        print(f"  Recovery churn summary: {summary['closure_forecast_recovery_churn_summary']}")
    if summary.get("primary_target_closure_forecast_reacquisition_freshness_status") not in {
        None,
        "",
        "insufficient-data",
    }:
        print(
            "  Reacquisition freshness: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_freshness_reason', 'No reacquisition-freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reacquisition_freshness_summary"):
        print(
            f"  Reacquisition freshness summary: {summary['closure_forecast_reacquisition_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_persistence_reset_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Persistence reset controls: "
            f"{summary.get('primary_target_closure_forecast_persistence_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_persistence_reset_reason', 'No persistence-reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_persistence_reset_summary"):
        print(
            f"  Persistence reset summary: {summary['closure_forecast_persistence_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_refresh_recovery_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_refresh_recovery_summary"):
        print(
            f"  Reset refresh recovery summary: {summary['closure_forecast_reset_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_reason', 'No reset re-entry reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_summary"):
        print(f"  Reset re-entry summary: {summary['closure_forecast_reset_reentry_summary']}")
    if summary.get("primary_target_closure_forecast_reset_reentry_persistence_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_churn_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_freshness_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_reset_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_refresh_recovery_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"
    ) not in {None, "", "none"}:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reset_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"
    ) not in {None, "", "none"}:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_status") not in {
        None,
        "",
        "none",
    }:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary', 'No reset re-entry rebuild re-entry refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"
    ) not in {None, "", "insufficient-data"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs', 0)} run(s))"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-restore churn reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
    ) not in {None, "", "insufficient-data"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-restore freshness reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-restore reset reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs', 0)} run(s))"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-restore churn reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
    ) not in {None, "", "none"}:
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
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs', 0)} run(s))"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore churn reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"
    ) not in {None, "", "none"}:
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
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_churn_status") not in {
        None,
        "",
        "none",
    }:
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
        lane_items = [item for item in queue if item.get("lane") == lane]
        items = [item for item in lane_items if _should_print_control_center_item(item)]
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
        omitted_count = len(lane_items) - len(items)
        if omitted_count > 0:
            print(f"    ({omitted_count} experiment/manual-only item(s) hidden from default view.)")
    if recent_changes:
        print("\nRecently Changed")
        for item in recent_changes[:5]:
            subject = (
                item.get("repo") or item.get("repo_full_name") or item.get("item_id") or "portfolio"
            )
            print(
                f"  - {item.get('generated_at', '')[:10]} {subject}: {item.get('summary', item.get('kind', 'change'))}"
            )


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


def _analysis_worker_count(args) -> int:
    """Return the bounded repo-analysis worker count for this run."""
    raw_value = getattr(args, "analysis_workers", None)
    if raw_value is None:
        raw_value = os.environ.get("GITHUB_REPO_AUDITOR_ANALYSIS_WORKERS")

    if raw_value in {None, ""}:
        return DEFAULT_ANALYSIS_WORKERS

    try:
        requested = int(raw_value)
    except (TypeError, ValueError):
        print_warning("Invalid analysis worker count; using the reliable single-worker default.")
        return DEFAULT_ANALYSIS_WORKERS

    if requested < 1:
        print_warning(
            "Analysis worker count must be at least 1; using the reliable single-worker default."
        )
        return DEFAULT_ANALYSIS_WORKERS

    if requested > MAX_ANALYSIS_WORKERS:
        print_warning(
            f"Analysis worker count capped at {MAX_ANALYSIS_WORKERS} to avoid GitHub API stalls."
        )
        return MAX_ANALYSIS_WORKERS

    return requested


def _use_analysis_progress(workers: int) -> bool:
    """Use rich progress only when it can render visibly for the operator."""
    return workers > 1 and sys.stderr.isatty()


def _use_analyzer_cache(args, workers: int) -> bool:
    """Use the SQLite analyzer cache only for single-worker analysis."""
    return not getattr(args, "no_analyzer_cache", False) and workers == 1


def _select_target_repos(
    target_names: list[str], repos: list[RepoMetadata]
) -> tuple[list[RepoMetadata], list[str]]:
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
            print_info(
                f"Loaded {len(extra_analyzers)} custom analyzer(s) from {args.analyzers_dir}"
            )

    audits: list[RepoAudit] = []
    requested_workers = _analysis_worker_count(args)

    # Open a warehouse connection for the analyzer result cache unless disabled.
    _warehouse_conn = None
    if not _use_analyzer_cache(args, requested_workers):
        if requested_workers > 1 and not getattr(args, "no_analyzer_cache", False):
            print_warning(
                "Analyzer result cache disabled for parallel analysis; "
                "rerun with one analysis worker to use the SQLite cache."
            )
    else:
        import sqlite3 as _sqlite3

        from src.warehouse import WAREHOUSE_FILENAME
        from src.warehouse import _ensure_schema as _warehouse_ensure_schema

        _output_dir = Path(getattr(args, "output_dir", "output"))
        _db_path = _output_dir / WAREHOUSE_FILENAME
        try:
            _output_dir.mkdir(parents=True, exist_ok=True)
            _warehouse_conn = _sqlite3.connect(str(_db_path))
            _warehouse_ensure_schema(_warehouse_conn)
        except Exception as _cache_err:
            print_warning(f"Could not open warehouse for analyzer cache: {_cache_err}")
            _warehouse_conn = None

    def _analyze_one(repo_meta: RepoMetadata, repo_path: Path) -> RepoAudit:
        worker_client = GitHubClient(token=client.token, cache=client.cache)
        _commit_sha = repo_meta.pushed_at.isoformat() if repo_meta.pushed_at else ""
        results = run_all_analyzers(
            repo_path,
            repo_meta,
            worker_client,
            extra_analyzers=extra_analyzers,
            conn=_warehouse_conn,
            commit_sha=_commit_sha,
            sbom_source=getattr(args, "sbom_source", "lockfile"),
        )
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

    # ── Optional async enrichment prefetch ───────────────────────────────────
    _fetch_mode: str = getattr(args, "fetch_mode", "sync")
    if _fetch_mode == "async" and repos:
        from src.github_client_async import fetch_enrichment_sync as _async_prefetch

        _fetch_workers: int = max(1, getattr(args, "fetch_workers", 10))
        print_info(
            f"Pre-fetching enrichment for {len(repos)} repos "
            f"(async, concurrency={_fetch_workers})..."
        )
        _prefetch_start = perf_counter()
        try:
            _repo_pairs = [(r.full_name.split("/")[0], r.name) for r in repos if "/" in r.full_name]
            _async_prefetch(
                _repo_pairs,
                token=client.token,
                max_concurrency=_fetch_workers,
                cache=client.cache,
            )
            _prefetch_elapsed = perf_counter() - _prefetch_start
            print_info(f"Async enrichment prefetch complete in {_prefetch_elapsed:.1f}s.")
            if runtime_stats is not None:
                runtime_stats["async_prefetch_seconds"] = round(_prefetch_elapsed, 3)
        except Exception as _prefetch_err:
            print_warning(
                f"Async enrichment prefetch failed ({_prefetch_err!r}); "
                "falling back to per-repo sync fetch."
            )

    _reconcile_diverged: bool = False
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
        analyzable = [
            (index, repo_meta, cloned.get(repo_meta.name)) for index, repo_meta in enumerate(repos)
        ]
        analyzable = [
            (index, repo_meta, repo_path) for index, repo_meta, repo_path in analyzable if repo_path
        ]
        workers = min(requested_workers, max(1, len(analyzable)))
        if workers == 1:
            print_info("Analyzing with 1 worker for reliable full-audit progress.")
        else:
            print_info(f"Analyzing with {workers} workers.")
        progress = create_progress() if _use_analysis_progress(workers) else None
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
                            executor.submit(_analyze_one, repo_meta, repo_path): (
                                index,
                                repo_meta.name,
                            )
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
                    print(
                        f"  [{index + 1}/{len(repos)}] Analyzing {repo_meta.name}...",
                        file=sys.stderr,
                    )
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
                        print(
                            f"  [{finished}/{len(analyzable)}] Analyzing {repo_name}...",
                            file=sys.stderr,
                        )
                        completed[index] = future.result()
                        if args.verbose:
                            _print_verbose(completed[index])
            audits.extend(completed[index] for index in sorted(completed))
        if runtime_stats is not None:
            runtime_stats["analyzer_seconds"] = round(perf_counter() - analyze_start, 3)

        # ── Cache reconcile gate ──────────────────────────────────────────────
        _do_reconcile: bool = getattr(args, "reconcile_cache", False)
        if _do_reconcile and _warehouse_conn is not None and audits:
            from src.analyzer_cache import reconcile as _cache_reconcile
            from src.analyzers import run_all_analyzers as _run_all

            _repo_path_map: dict[str, object] = {
                repo_meta.name: cloned.get(repo_meta.name) for repo_meta in repos
            }
            _repo_meta_map: dict[str, object] = {repo_meta.name: repo_meta for repo_meta in repos}
            _sha_map: dict[str, str] = {
                repo_meta.name: (repo_meta.pushed_at.isoformat() if repo_meta.pushed_at else "")
                for repo_meta in repos
            }

            def _fresh_run(repo_path, meta, conn=None):
                return _run_all(
                    repo_path,
                    meta,
                    conn=None,
                    commit_sha="",
                    sbom_source=getattr(args, "sbom_source", "lockfile"),
                )

            _reconcile_report = _cache_reconcile(
                _repo_path_map,
                _repo_meta_map,
                _warehouse_conn,
                _fresh_run,
                commit_sha_map=_sha_map,
            )
            _checked = _reconcile_report["checked"]
            _matched = _reconcile_report["matched"]
            _divergent = _reconcile_report["divergent"]
            print_info(
                f"Cache reconcile: {_matched}/{_checked} matched, {len(_divergent)} divergent"
            )
            if _divergent:
                _reconcile_diverged = True
                for _entry in _divergent:
                    print_warning(
                        f"  DIVERGE {_entry['repo']} {_entry['analyzer']}: {_entry['diff_summary']}"
                    )
                _output_dir_r = Path(getattr(args, "output_dir", "output"))
                _output_dir_r.mkdir(parents=True, exist_ok=True)
                import datetime as _dt
                import json as _json

                _stamp = _dt.date.today().isoformat()
                _report_path = _output_dir_r / f"cache-reconcile-{args.username}-{_stamp}.json"
                try:
                    _report_path.write_text(
                        _json.dumps(_reconcile_report, indent=2), encoding="utf-8"
                    )
                    print_warning(f"  Full divergence report: {_report_path}")
                except Exception as _write_err:
                    print_warning(f"Could not write reconcile report: {_write_err}")

    print_info("Clones cleaned up")
    if _warehouse_conn is not None:
        try:
            _warehouse_conn.close()
        except Exception:
            # Warehouse close failures are non-actionable during final cleanup.
            pass
    if _reconcile_diverged:
        sys.exit(1)
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


def _run_auto_apply_approved_mode(args, output_dir: Path) -> None:
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
        _report_path, _diff_dict, report = _refresh_latest_report_state(output_dir, args)
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


def _run_portfolio_truth_mode(args) -> None:
    from src.app.portfolio_truth import run_portfolio_truth_mode

    run_portfolio_truth_mode(args)


def _run_portfolio_context_recovery_mode(args) -> None:
    from src.app.portfolio_truth import run_portfolio_context_recovery_mode

    run_portfolio_context_recovery_mode(args)


def _run_automation_proposals_mode(args) -> None:
    """Triage the durable bounded-automation proposal queue (Arc D phase 3b).

    Handles --propose-automation / --list-proposals / --approve-proposal /
    --reject-proposal / --execute-proposals. The approval gate and every git/gh
    safety rail live in the executor + proposal layers; this is thin dispatch.
    """
    from datetime import datetime, timezone

    from src.automation_proposals import (
        ACTION_CATALOG_SEED,
        ACTION_CONTEXT_PR,
        ProposalApprovalError,
        ProposalNotFoundError,
        approve_proposal,
        build_automation_proposals,
        load_proposals,
        reject_proposal,
        save_proposals,
    )
    from src.portfolio_automation import select_automation_candidates

    output_dir = Path(args.output_dir)
    proposals_path = output_dir / "pending-proposals.json"
    now = datetime.now(timezone.utc).isoformat()

    if getattr(args, "approve_proposal", None) or getattr(args, "reject_proposal", None):
        try:
            proposals = load_proposals(proposals_path)
            if getattr(args, "approve_proposal", None):
                updated = approve_proposal(
                    proposals,
                    args.approve_proposal,
                    approved_by="local-operator",
                    approved_at=now,
                )
                label = f"Approved proposal {args.approve_proposal!r}."
            else:
                updated = reject_proposal(proposals, args.reject_proposal, rejected_at=now)
                label = f"Rejected proposal {args.reject_proposal!r}."
        except (ProposalNotFoundError, ProposalApprovalError, ValueError) as exc:
            print_warning(str(exc))
            return
        save_proposals(proposals_path, updated)
        print_info(label)
        return

    if getattr(args, "list_proposals", False):
        proposals = load_proposals(proposals_path)
        if not proposals:
            print_info("No bounded-automation proposals in the queue.")
            return
        print_info(f"Bounded-automation proposal queue ({len(proposals)} total):")
        for proposal in proposals:
            print_info(f"  {proposal.status}: {proposal.proposal_id} — {proposal.description}")
        return

    if getattr(args, "propose_automation", False):
        from src.weekly_command_center import load_latest_portfolio_truth

        _truth_path, truth = load_latest_portfolio_truth(output_dir)
        if not truth:
            print_warning("No portfolio truth snapshot found. Run --portfolio-truth first.")
            return
        try:
            _report_path, _diff, report = _refresh_latest_report_state(output_dir, args)
            decision_quality_status = (
                (report.operator_summary or {})
                .get("decision_quality_v1", {})
                .get("decision_quality_status", "")
            )
        except FileNotFoundError:
            decision_quality_status = ""
        candidates = select_automation_candidates(
            truth, decision_quality_status=decision_quality_status
        )
        existing = load_proposals(proposals_path)
        merged = build_automation_proposals(
            candidates, action_type=ACTION_CONTEXT_PR, created_at=now, existing=existing
        )
        merged = build_automation_proposals(
            candidates, action_type=ACTION_CATALOG_SEED, created_at=now, existing=merged
        )
        save_proposals(proposals_path, merged)
        print_info(
            f"Proposal queue: {len(merged)} total ({len(merged) - len(existing)} new) "
            f"from {len(candidates)} eligible candidate(s)."
        )
        return

    if getattr(args, "execute_proposals", False):
        from src.automation_proposals import executable_proposals
        from src.automation_workflow import execute_approved_proposals
        from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot

        # Building a fresh portfolio snapshot scans the whole workspace (+ Notion);
        # skip that entirely when nothing is approved to execute.
        if not executable_proposals(load_proposals(proposals_path)):
            print_info("No approved bounded-automation proposals to execute.")
            return

        workspace_root = Path(getattr(args, "workspace_root", None) or DEFAULT_PORTFOLIO_WORKSPACE)
        catalog_path = (
            Path(args.catalog)
            if getattr(args, "catalog", None)
            else Path("config/portfolio-catalog.yaml")
        )
        registry_output = (
            Path(args.registry_output)
            if getattr(args, "registry_output", None)
            else workspace_root / "project-registry.md"
        )
        legacy_registry_path = (
            Path(args.registry) if getattr(args, "registry", None) else registry_output
        )
        build_result = build_portfolio_truth_snapshot(
            workspace_root=workspace_root,
            catalog_path=catalog_path if catalog_path.exists() else None,
            legacy_registry_path=legacy_registry_path,
            include_notion=True,
        )
        apply = bool(getattr(args, "apply", False))
        results = execute_approved_proposals(
            proposals_path=proposals_path,
            snapshot=build_result.snapshot,
            workspace_root=workspace_root,
            catalog_path=catalog_path,
            executed_at=now,
            dry_run=not apply,
        )
        if not results:
            print_info("No approved bounded-automation proposals to execute.")
            return
        for result in results:
            print_info(f"  {result.outcome}: {result.proposal_id} — {result.detail}")
        mode = "apply" if apply else "dry-run"
        print_info(f"Execute proposals ({mode}): {len(results)} approved proposal(s) processed.")
        return


def _run_tier_recalibration_report_mode(args) -> None:
    """Generate tier distribution report and flag bunching (Arc H A4)."""
    from datetime import date, datetime, timezone

    from src.tier_recalibration import tier_distribution_report

    output_dir = Path(args.output_dir)
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first."
        )
        return

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print_warning(f"Failed to read portfolio-truth: {exc}")
        sys.exit(2)

    projects = truth.get("projects", [])
    report = tier_distribution_report(projects)
    out_path = output_dir / f"tier-recalibration-{date.today()}.json"
    envelope = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }
    out_path.write_text(json.dumps(envelope, indent=2))
    print_info(f"Tier recalibration report written to {out_path}")
    if report["bunching_detected"]:
        print_warning(
            "Bunching detected: at least one tier holds >60% of repos. "
            "Consider adjusting tier thresholds."
        )
    else:
        print_info("No bunching detected — tier distribution looks healthy.")


def _run_context_triage_mode(args) -> None:
    """Run context quality triage across the portfolio (Arc H B1)."""
    from datetime import date, datetime, timezone

    from src.catalog_validator import validate_catalog
    from src.portfolio_context_triage import run_triage

    output_dir = Path(args.output_dir)
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_warning(
            "portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first."
        )
        return

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print_warning(f"Failed to read portfolio-truth: {exc}")
        sys.exit(2)

    projects = truth.get("projects", [])
    catalog_path = (
        Path(args.catalog)
        if getattr(args, "catalog", None)
        else Path("config/portfolio-catalog.yaml")
    )
    repo_keys: list[str] = []
    for project in projects:
        identity = project.get("identity") or {}
        project_key = identity.get("project_key") or ""
        name = identity.get("display_name") or project.get("name", "")
        repo_keys.extend(key for key in (project_key, name) if key)
    catalog_scores = (
        validate_catalog(catalog_path, sorted(set(repo_keys))) if catalog_path.exists() else {}
    )

    enriched: list[dict] = []
    for project in projects:
        identity = project.get("identity") or {}
        name = identity.get("display_name") or project.get("name", "")
        project_key = identity.get("project_key") or name
        row = dict(project)
        row["catalog_completeness"] = max(
            catalog_scores.get(project_key, 0.0),
            catalog_scores.get(name, 0.0),
        )
        enriched.append(row)

    entries = run_triage(enriched)
    out = [e.to_dict() for e in entries]
    out_path = output_dir / f"context-triage-{date.today()}.json"
    envelope = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_flagged": len(out),
        "triage": out,
    }
    out_path.write_text(json.dumps(envelope, indent=2))
    print_info(f"Context triage written to {out_path} — {len(out)} repos flagged")


def _apply_governance_view_filter(report: AuditReport, governance_view: str) -> None:
    if not isinstance(report.governance_preview, dict):
        report.governance_preview = {}
    report.governance_preview["selected_view"] = governance_view
    if governance_view == "all":
        return

    preview_actions = (
        report.governance_preview.get("actions", [])
        if isinstance(report.governance_preview, dict)
        else []
    )
    result_rows = (
        report.governance_results.get("results", [])
        if isinstance(report.governance_results, dict)
        else []
    )
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


def _apply_ops_writeback(
    report: AuditReport, args, client: GitHubClient | None, output_dir: Path
) -> None:
    if not args.campaign:
        return

    github_projects_config = None
    operator_context: dict[str, dict] = {}
    if getattr(args, "github_projects", False):
        from src.github_projects import load_github_projects_config, operator_context_by_repo
        from src.operator_control_center import build_operator_snapshot, normalize_review_state

        github_projects_config = load_github_projects_config(
            Path(args.github_projects_config)
            if getattr(args, "github_projects_config", None)
            else None
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
            github_results, github_refs, github_drift, _github_closure_events = (
                apply_github_writeback(
                    client,
                    actions,
                    previous_state=previous_state,
                    sync_mode=args.campaign_sync_mode,
                    campaign_summary=campaign_summary,
                    github_projects_config=github_projects_config,
                    operator_context=operator_context,
                )
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


def _legacy_enrich_report_with_operator_state(
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
        diff_md_path = (
            output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.md"
        )
        diff_md_path.write_text(format_diff_markdown(diff))
        diff_json_path = (
            output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.json"
        )
        diff_json_path.write_text(json.dumps(diff_dict, indent=2))
        print_info(
            f"Diff: {len(diff.tier_changes)} tier changes, "
            f"{len([c for c in diff.score_changes if abs(c['delta']) > 0.05])} significant score changes"
        )

    report = _apply_portfolio_catalog(report, args)
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
        truth_dir=output_dir,
    )
    report.runtime_breakdown["workbook_build_seconds"] = round(perf_counter() - workbook_start, 3)
    md_path = write_markdown_report(report, output_dir, diff_data=diff_dict)
    pcc_path = write_pcc_export(report, output_dir)
    raw_path = write_raw_metadata(report, output_dir)
    warehouse_path = write_warehouse_snapshot(report, output_dir, json_path)

    # ── Semantic reindex (Arc F S3.1) ──────────────────────────────────
    if getattr(args, "reindex", False) or getattr(args, "reindex_force", False):
        _maybe_run_reindex(report, warehouse_path, args)

    if archive and write_json:
        archive_report(json_path)
    if save_fingerprint_data:
        save_fingerprints(report_data["audits"], output_dir / ".audit-fingerprints.json")
    report.runtime_breakdown["report_output_seconds"] = round(perf_counter() - output_start, 3)

    badge_info = ""
    if args.badges:
        from src.badge_export import _write_badges_markdown, export_badges, upload_badge_gist

        badge_result = export_badges(report_data, output_dir)
        badge_info = (
            f"\n    {badge_result['badges_md']} ({badge_result['files_written']} badge files)"
        )
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
                    report_data.get("audits", []),
                    project_map,
                    sync_token,
                    sync_config,
                )
                patch_weekly_review(report_data, diff_dict, quick_wins, sync_token, sync_config)
                create_audit_history_entry(report_data, sync_token, sync_config)
                patch_project_completeness_cards(
                    report_data.get("audits", []),
                    project_map,
                    sync_token,
                    sync_config,
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
            print_info(
                f"Archive candidates: {archive_result['count']} repos → {archive_result['report_path']}"
            )

    if getattr(args, "vuln_check", False):
        from src.vuln_check import check_vulnerabilities, format_vuln_summary

        vulns = check_vulnerabilities(report_data.get("audits", []), cache=cache)
        print_info(format_vuln_summary(vulns))
        if vulns:
            vuln_path = (
                output_dir / f"vuln-report-{report.username}-{_date_str(report.generated_at)}.json"
            )
            vuln_path.write_text(json.dumps(vulns, indent=2, default=str))
            print_info(f"Vulnerability report: {vuln_path}")

    if getattr(args, "ghas_alerts", False) or getattr(args, "vuln_check", False):
        from src.ghas_alert_details import fetch_dependabot_details
        from src.ghas_alerts import fetch_ghas_alerts, format_ghas_summary

        ghas_token: str | None = getattr(args, "token", None) or None
        ghas_data = fetch_ghas_alerts(
            report_data.get("audits", []),
            token=ghas_token,
            cache=cache,
        )
        # Enrich each repo entry with per-alert detail for security-burndown.
        # fetch_dependabot_details paginates the same endpoint as fetch_ghas_alerts
        # but lives in a separate module to keep ghas_alerts.py byte-identical to
        # main (editing it triggers ruff-format reflows that CodeQL flags).
        dep_details = fetch_dependabot_details(
            report_data.get("audits", []),
            token=ghas_token,
            cache=cache,
        )
        for repo_name in ghas_data:
            ghas_data[repo_name]["dependabot_details"] = dep_details.get(repo_name, [])
        print_info(format_ghas_summary(ghas_data))
        if ghas_data:
            ghas_path = (
                output_dir / f"ghas-alerts-{report.username}-{_date_str(report.generated_at)}.json"
            )
            ghas_path.write_text(json.dumps(ghas_data, indent=2, default=str))
            print_info(f"GHAS alerts report: {ghas_path}")

    if getattr(args, "ossf_scorecard", False):
        from src.ossf_scorecard import fetch_ossf_scorecards, format_ossf_summary

        ossf_data = fetch_ossf_scorecards(
            report_data.get("audits", []),
            cache=cache,
        )
        # Wire per-repo data into audit JSON
        ossf_by_repo: dict[str, dict] = {}
        for full_name, scorecard in ossf_data.items():
            ossf_by_repo[full_name] = scorecard
        for audit in report.audits:
            fn = audit.metadata.full_name
            if fn in ossf_by_repo:
                audit.ossf_scorecard = ossf_by_repo[fn]
        # Re-serialize after mutation
        report_data = report.to_dict()

        print_info(format_ossf_summary(ossf_data))
        ossf_path = (
            output_dir / f"ossf-scorecard-{report.username}-{_date_str(report.generated_at)}.json"
        )
        ossf_path.write_text(json.dumps(ossf_data, indent=2, default=str))
        print_info(f"OSSF Scorecard report: {ossf_path}")

    # ── LLM cost tracking ────────────────────────────────────────────────────
    _uses_llm = args.narrative or getattr(args, "briefing", False)
    _cost_tracker = None
    if _uses_llm:
        from src.llm_cost import BudgetExceededError, CostTracker

        _cost_tracker = CostTracker(
            budget_usd=getattr(args, "max_llm_spend", None),
            output_path=output_dir,
        )

    if args.narrative:
        from src.narrative import generate_narrative

        try:
            generate_narrative(
                report_data,
                output_dir,
                provider_name=args.narrative_provider,
                model=args.narrative_model,
                github_token=args.token,
                cost_tracker=_cost_tracker,
            )
        except BudgetExceededError as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            if _cost_tracker is not None:
                _cost_tracker.write_telemetry()
            sys.exit(1)

    if getattr(args, "briefing", False):
        from src.briefing import generate_briefing

        try:
            generate_briefing(
                report_data,
                output_dir,
                provider_name=args.narrative_provider,
                model=args.narrative_model,
                github_token=args.token,
                write_voice=getattr(args, "briefing_voice", False),
                cost_tracker=_cost_tracker,
                include_suggestions=getattr(args, "include_suggestions", False),
            )
        except BudgetExceededError as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            if _cost_tracker is not None:
                _cost_tracker.write_telemetry()
            sys.exit(1)

    if _cost_tracker is not None:
        _cost_tracker.write_telemetry()

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


def _ensure_partial_run_baseline_compatible(
    existing_report_data: dict | None, current_context: dict
) -> bool:
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
        print_info(
            f"{ACTION_SYNC_CANONICAL_LABELS['next_tie_break_candidate']}: {report.next_tuned_campaign.get('summary')}"
        )
    if report.intervention_ledger_summary.get("summary"):
        print_info(
            f"Historical portfolio intelligence: {report.intervention_ledger_summary.get('summary')}"
        )
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
        run_errors.append(
            {"repo": f"{args.username}/{name}", "error": "Repo not found in fetched metadata"}
        )
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
        print_info(
            f"Merging into {existing_report_path.name} ({len(existing_audits)} existing repos)"
        )

    # Replace any existing audit entries for the re-analyzed repos
    new_names = {audit.metadata.name for audit in new_audits}
    kept_audits = [
        _audit_from_dict(audit_data)
        for audit_data in existing_audits
        if audit_data["metadata"]["name"] not in new_names
    ]
    # new_audits first so they appear at the top of the report
    merged_audits = list(new_audits) + kept_audits
    total_repos = (
        existing_report_data.get("total_repos", len(filtered_repos))
        if existing_report_data
        else len(filtered_repos)
    )

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


# ── Semantic index helpers (Arc F S3.1) ───────────────────────────────


def _maybe_run_reindex(report: "AuditReport", warehouse_path: Path, args: object) -> None:
    """Run semantic reindex after audit.  Skips gracefully if deps missing."""
    from src.semantic_index import SemanticIndex, _run_reindex

    embedder_name: str = getattr(args, "embedder", "voyage")
    force: bool = getattr(args, "reindex_force", False)

    idx = SemanticIndex.from_embedder_name(warehouse_path, embedder_name)
    if idx is None:
        print_warning(
            "Semantic reindex skipped — embedder unavailable. "
            "Set VOYAGE_API_KEY or use --embedder local with [semantic] extra installed."
        )
        return

    summary = _run_reindex(idx, report.audits, force=force)
    print_info(
        f"Semantic index: {summary['embedded']} embedded, "
        f"{summary['skipped']} skipped, "
        f"{summary['total']} total "
        f"({summary['duration_s']:.2f}s)"
    )


def _run_semantic_search_mode(args: object, query: str) -> None:
    """Run a standalone semantic search against the existing warehouse index."""
    from src.semantic_index import SemanticIndex, _run_search
    from src.warehouse import WAREHOUSE_FILENAME

    output_dir = Path(getattr(args, "output_dir", "output"))
    warehouse_path = output_dir / WAREHOUSE_FILENAME
    if not warehouse_path.exists():
        print_warning(
            f"Warehouse not found at {warehouse_path}. "
            "Run an audit with --reindex first to build the semantic index."
        )
        return

    embedder_name: str = getattr(args, "embedder", "voyage")
    idx = SemanticIndex.from_embedder_name(warehouse_path, embedder_name)
    if idx is None:
        print_warning(
            "Semantic search unavailable — embedder not configured. "
            "Set VOYAGE_API_KEY or use --embedder local."
        )
        return

    results = _run_search(idx, query, k=5)
    if not results:
        print_info("No results found in semantic index. Run --reindex first.")
        return

    print_info(f'Semantic search: "{query}"\n')
    for i, r in enumerate(results, 1):
        print_info(f"  {i}. {r.repo_name}  (distance={r.score:.4f})")
        print_info(f"     {r.snippet}")


# ── Serve mode ───────────────────────────────────────────────────────────────
def _run_serve_mode(args: object) -> None:
    from src.app.serve_mode import run_serve_mode

    run_serve_mode(args)


# ── Subcommand inference for legacy flat invocation ───────────────────
def _infer_subcommand_from_flags(args: argparse.Namespace) -> str:
    """Return the effective subcommand name for a legacy flat invocation."""
    # triage signals
    triage_flags = (
        "control_center",
        "approval_center",
        "triage_view",
        "approve_governance",
        "approve_packet",
        "review_governance",
        "review_packet",
        "auto_apply_approved",
        "reset_prefs",
        "acknowledge_target",
        "acknowledge_kind",
        "semantic_search",
        "ask",
        "set_initiative",
        "initiatives",
        "close_initiative",
    )
    for flag in triage_flags:
        val = getattr(args, flag, None)
        if val and val not in (False, "all", None, ""):
            return "triage"
    if getattr(args, "approval_center", False) or getattr(args, "control_center", False):
        return "triage"

    # report signals
    report_flags = (
        "portfolio_truth",
        "portfolio_context_recovery",
        "apply_context_recovery",
        "generate_manifest",
        "apply_metadata",
        "apply_readmes",
        "campaign_from_ledger",
        "draft_readmes",
        "upload_badges",
        "notion_sync",
        "tier_gaps",
        "tier_recalibration_report",
        "context_triage",
        "propose_automation",
        "list_proposals",
        "execute_proposals",
    )
    for flag in report_flags:
        if getattr(args, flag, False):
            return "report"
    if getattr(args, "campaign", None):
        return "report"
    if getattr(args, "writeback_target", None):
        return "report"
    if getattr(args, "approve_proposal", None) or getattr(args, "reject_proposal", None):
        return "report"

    return "run"


_KNOWN_SUBCOMMANDS: frozenset[str] = frozenset(
    {"run", "triage", "report", "serve", "security-burndown", "security-gate"}
)


def _emit_legacy_deprecation_warning(inferred: str) -> None:
    """Emit the deprecation warning at most once per process."""
    if "legacy-cli" in _LEGACY_WARNING_EVENTS:
        return
    _LEGACY_WARNING_EVENTS.add("legacy-cli")
    warnings.warn(
        f"Top-level CLI invocation is deprecated. "
        f"Use `audit {inferred} --flag` instead. "
        "Legacy form will be removed in a future major version.",
        DeprecationWarning,
        stacklevel=2,
    )


def _rewrite_legacy_argv(argv: list[str]) -> tuple[list[str], bool]:
    """Detect legacy flat invocation and rewrite to subcommand form.

    Legacy form: audit <username> [--flags...]
    Subcommand form: audit <subcommand> <username> [--flags...]

    Returns (rewritten_argv, is_legacy).  If the invocation already uses a
    known subcommand (or is --serve / --help), returns argv unchanged.

    Only rewrites when the first positional looks like a GitHub username
    (alphanumeric + hyphens only, no path separators or colons).  This
    prevents false-positive rewrites when main() is called during tests
    where sys.argv contains pytest args (file paths, test IDs, etc.).
    """
    if not argv:
        return argv, False

    # Skip if first arg is a known subcommand, a flag, or --help/-h
    first = argv[0]
    if first in _KNOWN_SUBCOMMANDS or first.startswith("-"):
        return argv, False

    # Only treat as legacy username if it looks like a GitHub username:
    # alphanumeric and hyphens only (no path separators, colons, dots).
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,38}", first):
        return argv, False

    # first arg looks like a username — legacy invocation detected.
    # Infer subcommand from the remaining flags (quick scan without full parse).
    rest = argv[1:]

    # triage signals
    if (
        any(
            f in rest
            for f in [
                "--control-center",
                "--approval-center",
                "--approve-governance",
                "--approve-packet",
                "--review-governance",
                "--review-packet",
                "--auto-apply-approved",
                "--reset-prefs",
                "--semantic-search",
                "--ask",
            ]
        )
        or "--acknowledge-target" in rest
        or "--acknowledge-kind" in rest
    ):
        inferred = "triage"
    # report signals
    elif (
        any(
            f in rest
            for f in [
                "--portfolio-truth",
                "--portfolio-context-recovery",
                "--apply-context-recovery",
                "--generate-manifest",
                "--apply-metadata",
                "--apply-readmes",
                "--upload-badges",
                "--notion-sync",
                "--propose-automation",
                "--list-proposals",
                "--execute-proposals",
            ]
        )
        or "--campaign" in rest
        or "--writeback-target" in rest
        or "--approve-proposal" in rest
        or "--reject-proposal" in rest
    ):
        inferred = "report"
    else:
        inferred = "run"

    # Rewrite: insert inferred subcommand before the username
    return [inferred, first] + rest, True


def _run_security_burndown_mode(args) -> None:
    from src.app.security_modes import run_security_burndown_mode

    run_security_burndown_mode(args)


def _run_security_gate_mode(args) -> None:
    from src.app.security_modes import run_security_gate_mode

    run_security_gate_mode(args)


# ── Main entry point ──────────────────────────────────────────────────
def main() -> None:
    raw_argv = sys.argv[1:]

    # ── Choose parser based on invocation form ───────────────────────
    # Subcommand form:  audit run|triage|report|serve [args...]
    # Legacy flat form: audit username [--flags...]  (deprecated)
    # --serve / --help: handled by either parser path
    argv, is_legacy = _rewrite_legacy_argv(raw_argv)
    # After rewrite, argv[0] is always a known subcommand name (or a flag).

    subcommand_parser = build_subcommand_parser()
    legacy_parser = build_parser()

    # ── Subcommands with no legacy equivalent ───────────────────────────────
    if argv and argv[0] == "security-burndown":
        sb_args = subcommand_parser.parse_args(argv)
        _run_security_burndown_mode(sb_args)
        return
    if argv and argv[0] == "security-gate":
        sg_args = subcommand_parser.parse_args(argv)
        _run_security_gate_mode(sg_args)
        return

    if argv and argv[0] in _KNOWN_SUBCOMMANDS:
        # Subcommand form — detect the subcommand with the subcommand parser,
        # then re-parse the full flag set through the legacy parser so that ALL
        # flags (including advanced ones not listed in the subcommand help) are
        # accepted.  The subcommand parser's role is subcommand detection and
        # --help display only; the legacy parser handles full validation.
        sc_args, _ = subcommand_parser.parse_known_args(argv)
        detected_subcommand = sc_args._subcommand  # e.g. "run", "triage", …

        # Re-parse without the subcommand token through the legacy flat parser.
        # argv[1:] strips the subcommand name; legacy parser sees username + flags.
        flat_argv = argv[1:]  # e.g. ["myuser", "--html"]
        args = legacy_parser.parse_args(flat_argv)
        setattr(args, "_subcommand", detected_subcommand)
        parser = legacy_parser
    else:
        # Legacy flat form (--serve, --help, or no args) — use legacy parser.
        # Call with no argument so it reads sys.argv itself; this keeps
        # monkeypatched FakeParser objects in tests working unchanged.
        args = legacy_parser.parse_args()
        parser = legacy_parser
        is_legacy = False  # --serve / --help / empty: not a deprecated invocation

    from src.approval_ledger import default_approval_reviewer

    # ── Subcommand: serve ────────────────────────────────────────────
    subcommand = getattr(args, "_subcommand", None)
    if subcommand == "serve" or getattr(args, "serve", False):
        _run_serve_mode(args)
        return

    # Load config file and merge into args (CLI flags take precedence)
    from src.config import inspect_config, merge_config_with_args

    config_inspection = inspect_config(Path(args.config) if args.config else None)
    if config_inspection.data:
        merge_config_with_args(args, config_inspection.data)
    setattr(args, "_preflight_summary", {})
    if not getattr(args, "approval_reviewer", None):
        args.approval_reviewer = default_approval_reviewer()

    # ── Legacy flat invocation: emit deprecation warning ────────────
    if is_legacy:
        inferred = subcommand or "run"
        _emit_legacy_deprecation_warning(inferred)

    if getattr(args, "username", None) is None and subcommand != "serve":
        parser.error(
            "the following arguments are required: username "
            "(omit only when using `audit serve` or `--serve`)"
        )

    mode_state = validate_cli_mode_args(args, parser.error)
    portfolio_truth_mode = mode_state.portfolio_truth_mode
    portfolio_context_recovery_mode = mode_state.portfolio_context_recovery_mode

    if getattr(args, "reset_prefs", False):
        from src.operator_prefs import prefs_path, reset_prefs

        reset_prefs(prefs_path(Path(args.output_dir)))
        print_info("Operator prefs reset: suppression hints cleared.")
        return

    if args.approval_center:
        _run_approval_center_mode(args, parser)
        return

    if (
        args.approve_governance
        or args.approve_packet
        or args.review_governance
        or args.review_packet
    ):
        _run_approval_capture_mode(args, parser)
        return

    if getattr(args, "acknowledge_target", None) or getattr(args, "acknowledge_kind", None):
        _run_acknowledgment_capture_mode(args, parser)
        return

    if getattr(args, "auto_apply_approved", False):
        _run_auto_apply_approved_mode(args, Path(args.output_dir))
        return

    if portfolio_truth_mode:
        _run_portfolio_truth_mode(args)
        return
    if portfolio_context_recovery_mode:
        _run_portfolio_context_recovery_mode(args)
        return

    if (
        getattr(args, "propose_automation", False)
        or getattr(args, "list_proposals", False)
        or getattr(args, "execute_proposals", False)
        or getattr(args, "approve_proposal", None)
        or getattr(args, "reject_proposal", None)
    ):
        _run_automation_proposals_mode(args)
        return

    if args.doctor:
        _run_doctor_mode(args, config_inspection)
        return

    if args.control_center:
        _run_control_center_mode(args, parser)
        return

    # ── Improvement campaign workflow (standalone, no audit needed) ────
    if getattr(args, "generate_manifest", False):
        _run_generate_manifest_mode(args, parser)
        return

    if getattr(args, "apply_metadata", False) or getattr(args, "apply_readmes", False):
        _run_apply_improvements_mode(args, parser)
        return

    if getattr(args, "campaign_from_ledger", False):
        _run_campaign_from_ledger_mode(args)
        return

    if getattr(args, "plan_campaign", None):
        _run_plan_campaign_mode(args)
        return

    if getattr(args, "draft_readmes", False):
        _run_draft_readmes_mode(args)
        return

    # ── Initiative tracker (7A.3) ──────────────────────────────────────────
    if getattr(args, "set_initiative", None):
        _run_set_initiative_mode(args)
        return
    if getattr(args, "initiatives", False):
        _run_list_initiatives_mode(args)
        return
    if getattr(args, "close_initiative", None):
        _run_close_initiative_mode(args)
        return

    # ── LLM-suggested initiatives (8.4) ───────────────────────────────────
    if getattr(args, "suggest_initiatives", None) is not None:
        _run_suggest_initiatives_mode(args)
        return

    # ── Accept suggestion (9.1) ───────────────────────────────────────────
    if getattr(args, "accept_suggestion", None):
        _run_accept_suggestion_mode(args)
        return

    # ── Dismiss suggestion (11.4) ─────────────────────────────────────────
    if getattr(args, "dismiss_suggestion", None):
        _run_dismiss_suggestion_mode(args)
        return
    if getattr(args, "undo_dismiss", None):
        _run_undo_dismiss_mode(args)
        return
    if getattr(args, "list_dismissed", False):
        _run_list_dismissed_mode(args)
        return
    # ── Auto-expire + audit trail (12.1) ─────────────────────────────────────
    if getattr(args, "expire_dismissals", False):
        _run_expire_dismissals_mode(args)
        return
    if getattr(args, "dismissal_history", False):
        _run_dismissal_history_mode(args)
        return

    # ── Tier-gap export (Arc G S12.4) ─────────────────────────────────────
    if getattr(args, "tier_gaps", False):
        _run_tier_gaps_export_mode(args)
        return

    # ── Context quality tools (Arc H) ──────────────────────────────────────
    if getattr(args, "tier_recalibration_report", False):
        _run_tier_recalibration_report_mode(args)
        return

    if getattr(args, "context_triage", False):
        _run_context_triage_mode(args)
        return

    if getattr(args, "serve", False):
        _run_serve_mode(args)
        return

    if args.watch:
        _run_watch_mode(args, config_inspection)
        return

    # ── Semantic search standalone mode (no audit needed) ─────────────
    query = getattr(args, "semantic_search", None) or getattr(args, "ask", None)
    if query:
        _run_semantic_search_mode(args, query)
        return

    _run_main_audit_cycle(args, config_inspection)


if __name__ == "__main__":
    main()
