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
from datetime import datetime, timezone
from pathlib import Path

from src.cache import ResponseCache
from src.cli_mode_validation import validate_cli_mode_args
from src.cli_output import print_info, print_warning
from src.github_client import GitHubClient
from src.portfolio_truth_types import TRUTH_LATEST_FILENAME, truth_latest_path
from src.app.run_audit import (
    _run_main_audit_cycle,
    _run_watch_mode,
)
from src.app.auto_apply import run_auto_apply_approved_mode
from src.app.automation_proposals import run_automation_proposals_mode


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




















def _run_control_center_mode(args, parser) -> None:
    from src.app.control_center import run_control_center_mode

    run_control_center_mode(args, parser)






def _run_approval_center_mode(args, parser) -> None:
    from src.app.approval_center import run_approval_center_mode

    run_approval_center_mode(args, parser)




def _run_approval_capture_mode(args, parser) -> None:
    from src.app.approval_center import run_approval_capture_mode

    run_approval_capture_mode(args, parser)




def _run_acknowledgment_capture_mode(args, parser) -> None:
    from src.app.acknowledgments import run_acknowledgment_capture_mode

    run_acknowledgment_capture_mode(args, parser)


def _run_doctor_mode(args, config_inspection) -> None:
    from src.app.doctor import run_doctor_mode

    run_doctor_mode(args, config_inspection)


def _run_generate_manifest_mode(args, parser) -> None:
    from src.app.report_only import run_generate_manifest_mode

    run_generate_manifest_mode(args, parser)


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






















# ── Core analysis pipeline ────────────────────────────────────────────





def _run_portfolio_truth_mode(args) -> None:
    from src.app.portfolio_truth import run_portfolio_truth_mode

    run_portfolio_truth_mode(args)


def _run_portfolio_context_recovery_mode(args) -> None:
    from src.app.portfolio_truth import run_portfolio_context_recovery_mode

    run_portfolio_context_recovery_mode(args)



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








# ── Report output orchestration ───────────────────────────────────────






# ── Partial run modes ─────────────────────────────────────────────────






# ── Scoring profile loader ─────────────────────────────────────────────


# ── Dry-run preview ───────────────────────────────────────────────────


# ── Semantic index helpers (Arc F S3.1) ───────────────────────────────




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
        run_auto_apply_approved_mode(args, Path(args.output_dir))
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
        run_automation_proposals_mode(args)
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
