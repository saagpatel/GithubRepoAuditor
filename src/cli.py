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
from datetime import datetime, timezone
from pathlib import Path

from src.analyzers import run_all_analyzers
from src.cache import ResponseCache
from src.cli_output import create_progress, print_info, print_status, print_warning
from src.cloner import clone_workspace
from src.github_client import GitHubClient
from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.reporter import (
    write_json_report,
    write_markdown_report,
    write_pcc_export,
    write_raw_metadata,
)
from src.scorer import score_repo


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
        description="Audit all GitHub repos for a user and generate a structured report.",
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
        "--scoring-profile",
        type=str,
        default=None,
        metavar="NAME",
        help="Use a custom scoring profile from config/scoring-profiles/NAME.json",
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
        "--max-actions",
        type=int,
        default=20,
        help="Maximum managed actions to include in a campaign run (default: 20)",
    )
    parser.add_argument(
        "--campaign-sync-mode",
        choices=["reconcile", "append-only", "close-missing"],
        default="reconcile",
        help="How campaign apply should reconcile missing managed state (default: reconcile)",
    )
    parser.add_argument(
        "--campaign-rollback",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="Preview or apply rollback for a prior managed campaign run",
    )
    parser.add_argument(
        "--governance-approve",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="Approve one prior security-review campaign run for governed control activation",
    )
    parser.add_argument(
        "--governance-apply",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="Apply governed security controls for one previously approved campaign run",
    )
    parser.add_argument(
        "--governance-scope",
        choices=["all", "codeql", "secret-scanning", "push-protection", "code-security"],
        default="all",
        help="Limit governed security activation to one control family (default: all)",
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
        "--watch",
        action="store_true",
        help="Re-run audit on interval (use with --watch-interval)",
    )
    parser.add_argument(
        "--watch-strategy",
        choices=["adaptive", "incremental", "full"],
        default="adaptive",
        help="Choose how watch mode selects each run shape (default: adaptive)",
    )
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=3600,
        help="Seconds between watch runs (default: 3600)",
    )
    parser.add_argument(
        "--review-materiality",
        choices=["low", "standard", "high"],
        default="standard",
        help="Threshold used for recurring-review alerts (default: standard)",
    )
    parser.add_argument(
        "--review-sync",
        choices=["local", "mixed"],
        default=None,
        help="Mirror recurring review state locally only or into Notion when configured",
    )
    parser.add_argument(
        "--review-from-latest",
        action="store_true",
        help="Generate a recurring review bundle from the latest report without running a new audit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be audited without cloning or writing any files",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a colored terminal summary of diff changes (requires --diff or a previous report)",
    )
    parser.add_argument(
        "--create-issues",
        action="store_true",
        help="Create GitHub Issues from quick win actions (requires --token)",
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
    return profile_name or "default"


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
        schema_version=data.get("schema_version", "3.4"),
        lenses=data.get("lenses", {}),
        hotspots=data.get("hotspots", []),
        security_posture=data.get("security_posture", {}),
        security_governance_preview=data.get("security_governance_preview", []),
        collections=data.get("collections", {}),
        profiles=data.get("profiles", {}),
        scenario_summary=data.get("scenario_summary", {}),
        action_backlog=data.get("action_backlog", []),
        campaign_summary=data.get("campaign_summary", {}),
        campaign_lifecycle_summary=data.get("campaign_lifecycle_summary", {}),
        rollup_status=data.get("rollup_status", {}),
        writeback_preview=data.get("writeback_preview", {}),
        writeback_results=data.get("writeback_results", {}),
        rollback_preview=data.get("rollback_preview", {}),
        managed_state_drift=data.get("managed_state_drift", []),
        campaign_history=data.get("campaign_history", []),
        governance_preview=data.get("governance_preview", {}),
        governance_approval=data.get("governance_approval", {}),
        governance_results=data.get("governance_results", {}),
        governance_history=data.get("governance_history", []),
        governance_drift=data.get("governance_drift", []),
        review_summary=data.get("review_summary", {}),
        review_alerts=data.get("review_alerts", []),
        material_changes=data.get("material_changes", []),
        review_targets=data.get("review_targets", []),
        review_history=data.get("review_history", []),
        watch_state=data.get("watch_state", {}),
        action_runs=data.get("action_runs", []),
        external_refs=data.get("external_refs", {}),
        reconciliation=reconciliation,
    )


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


def _print_dry_run_summary(repos: list[RepoMetadata], args) -> None:
    """Print a rich table of repos that would be audited, then exit."""
    from datetime import datetime, timezone

    from rich.console import Console
    from rich.table import Table

    console = Console(stderr=True)

    table = Table(title=f"Dry Run: repos that would be audited for {args.username}", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Language")
    table.add_column("Size (KB)", justify="right")
    table.add_column("Days Since Push", justify="right")
    table.add_column("Stars", justify="right")

    now = datetime.now(timezone.utc)
    total_kb = 0
    for repo in repos:
        pushed_at = repo.pushed_at
        if pushed_at:
            days_since = (now - pushed_at).days
        else:
            days_since = -1
        total_kb += repo.size_kb
        table.add_row(
            repo.name,
            repo.language or "",
            str(repo.size_kb),
            str(days_since) if days_since >= 0 else "?",
            str(repo.stars),
        )

    console.print(table)
    est_mb = total_kb / 1024
    console.print(
        f"\n[bold]{len(repos)} repos would be audited, est. {est_mb:.1f} MB to clone[/bold]"
    )


def _compute_portfolio_lang_freq(repos: list[RepoMetadata]) -> dict[str, float]:
    lang_counts = Counter(repo.language for repo in repos if repo.language)
    return {lang: count / len(repos) for lang, count in lang_counts.items()} if repos else {}


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
) -> list[RepoAudit]:
    if args.skip_clone:
        print_warning("Audit modes that score repos do not support --skip-clone.")
        return []

    audits: list[RepoAudit] = []
    progress = create_progress()
    with clone_workspace(
        repos,
        token=args.token,
        on_progress=lambda i, t, n: None,
        on_error=lambda n, m: print_warning(f"Failed to clone {n}"),
    ) as cloned:
        print_info(f"Cloned {len(cloned)}/{len(repos)} repos. Analyzing...")
        if progress:
            with progress:
                task = progress.add_task("Analyzing", total=len(repos))
                for repo_meta in repos:
                    repo_path = cloned.get(repo_meta.name)
                    if not repo_path:
                        progress.advance(task)
                        continue
                    progress.update(task, description=f"Analyzing {repo_meta.name}")
                    results = run_all_analyzers(repo_path, repo_meta, client)
                    audit = score_repo(
                        repo_meta,
                        results,
                        portfolio_lang_freq=portfolio_lang_freq,
                        custom_weights=custom_weights,
                        github_client=client,
                        scorecard_enabled=args.scorecard,
                        security_offline=args.security_offline,
                    )
                    audits.append(audit)
                    if args.verbose:
                        _print_verbose(audit)
                    progress.advance(task)
        else:
            for index, repo_meta in enumerate(repos, 1):
                repo_path = cloned.get(repo_meta.name)
                if not repo_path:
                    continue
                print(f"  [{index}/{len(repos)}] Analyzing {repo_meta.name}...", file=sys.stderr)
                results = run_all_analyzers(repo_path, repo_meta, client)
                audit = score_repo(
                    repo_meta,
                    results,
                    portfolio_lang_freq=portfolio_lang_freq,
                    custom_weights=custom_weights,
                    github_client=client,
                    scorecard_enabled=args.scorecard,
                    security_offline=args.security_offline,
                )
                audits.append(audit)
                if args.verbose:
                    _print_verbose(audit)

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


def _apply_ops_writeback(report: AuditReport, args, client: GitHubClient | None, output_dir: Path) -> None:
    campaign_type = getattr(args, "campaign", None)
    campaign_rollback = getattr(args, "campaign_rollback", None)
    if not campaign_type and not campaign_rollback:
        return

    from src.ops_writeback import (
        apply_github_rollback,
        apply_github_writeback,
        build_action_runs,
        build_campaign_run,
        build_rollback_preview,
        build_writeback_preview,
        prepare_campaign_operation,
        summarize_writeback_results,
    )
    from src.notion_sync import rollback_campaign_actions, sync_campaign_actions
    from src.warehouse import load_campaign_history, load_campaign_run

    if campaign_rollback:
        source_run = load_campaign_run(output_dir, campaign_rollback)
        if not source_run:
            print_warning(f"Campaign rollback source not found: {campaign_rollback}")
            return
        report.campaign_summary = {
            "campaign_type": source_run.get("campaign_type", ""),
            "label": source_run.get("label", ""),
            "collection_name": source_run.get("collection_name"),
            "portfolio_profile": source_run.get("portfolio_profile", "default"),
            "sync_mode": "rollback",
            "action_count": len(source_run.get("action_runs", [])),
            "repo_count": len({row.get("repo_id", "") for row in source_run.get("action_runs", [])}),
        }
        report.campaign_history = load_campaign_history(output_dir, campaign_type=source_run.get("campaign_type"), limit=10)
        report.rollback_preview = build_rollback_preview(source_run, writeback_target=args.writeback_target)
        report.rollup_status = {
            "safe_to_apply": True,
            "needs_human_review": False,
            "what_changed": {"rollback_items": report.rollback_preview.get("item_count", 0)},
        }
        results: list[dict] = []
        drift_events: list[dict] = []
        external_refs: dict[str, dict] = {}
        if args.writeback_apply and args.writeback_target:
            if args.writeback_target in {"github", "all"} and client is not None:
                github_results, github_drifts = apply_github_rollback(client, source_run)
                results.extend(github_results)
                drift_events.extend(github_drifts)
            if args.writeback_target in {"notion", "all"}:
                notion_results, notion_refs = rollback_campaign_actions(
                    source_run,
                    config_dir=Path("config"),
                    apply=True,
                )
                results.extend(notion_results)
                external_refs.update(notion_refs)
        report.writeback_results = summarize_writeback_results(
            results,
            args.writeback_target or source_run.get("writeback_target"),
            args.writeback_apply,
            drift_events=drift_events,
        )
        report.writeback_results["rollback_run"] = {
            "rollback_run_id": f"{report.username}:{report.generated_at.isoformat()}:rollback",
            "source_run_id": source_run.get("run_id"),
            "generated_at": report.generated_at.isoformat(),
            "writeback_target": args.writeback_target or source_run.get("writeback_target", "preview-only"),
            "mode": "apply" if args.writeback_apply else "preview",
        }
        report.action_runs = [
            {
                "action_id": row.get("action_id", ""),
                "repo_full_name": row.get("repo_id", ""),
                "campaign_type": row.get("campaign_type", source_run.get("campaign_type", "")),
                "target": row.get("target", args.writeback_target or "preview-only"),
                "status": "rolled_back" if args.writeback_apply else "preview",
                "lifecycle_state": "rolled_back" if args.writeback_apply else row.get("lifecycle_state", "planned"),
                "managed_target_state": "rollback",
                "rollback_available": False,
            }
            for row in source_run.get("action_runs", [])
        ]
        report.external_refs = external_refs
        report.managed_state_drift = drift_events
        report.campaign_lifecycle_summary = {
            "open_actions": 0,
            "closed_this_run": 0,
            "drift_count": len(drift_events),
            "rollback_ready": 0,
            "history_runs": len(report.campaign_history),
        }
        return

    campaign_summary, actions, closures, drifts, history = prepare_campaign_operation(
        report.to_dict(),
        output_dir=output_dir,
        campaign_type=campaign_type,
        portfolio_profile=args.portfolio_profile,
        collection_name=args.collection,
        max_actions=args.max_actions,
        writeback_target=args.writeback_target,
        sync_mode=args.campaign_sync_mode,
    )
    report.campaign_summary = campaign_summary
    report.campaign_history = history
    report.managed_state_drift = drifts
    report.campaign_lifecycle_summary = {
        "open_actions": len(actions),
        "closed_this_run": len(closures),
        "drift_count": len(drifts),
        "rollback_ready": sum(1 for action in actions if action.get("rollback_available")),
        "history_runs": len(history),
    }
    report.rollup_status = {
        "safe_to_apply": len(drifts) == 0,
        "needs_human_review": len(drifts) > 0,
        "what_changed": {
            "opened": len(actions),
            "closed": len(closures),
            "drifted": len(drifts),
        },
    }
    report.writeback_preview = build_writeback_preview(
        campaign_summary,
        actions,
        writeback_target=args.writeback_target,
        apply=args.writeback_apply,
        closures=closures,
        drifts=drifts,
    )

    results: list[dict] = []
    external_refs: dict[str, dict] = {}
    drift_events: list[dict] = list(drifts)
    if args.writeback_apply and args.writeback_target:
        if args.writeback_target in {"github", "all"} and client is not None:
            from src.warehouse import load_latest_campaign_context

            prior_context = load_latest_campaign_context(output_dir, campaign_type)
            github_results, github_refs, github_drifts = apply_github_writeback(
                client,
                actions,
                prior_context=prior_context,
                sync_mode=args.campaign_sync_mode,
                apply=True,
            )
            results.extend(github_results)
            external_refs.update(github_refs)
            drift_events.extend(github_drifts)
        if args.writeback_target in {"notion", "all"}:
            notion_results, notion_refs = sync_campaign_actions(
                actions,
                campaign_summary,
                prior_context=load_latest_campaign_context(output_dir, campaign_type),
                sync_mode=args.campaign_sync_mode,
                config_dir=Path("config"),
                apply=True,
            )
            results.extend(notion_results)
            external_refs.update(notion_refs)

    report.writeback_results = summarize_writeback_results(
        results,
        args.writeback_target,
        args.writeback_apply,
        drift_events=drift_events,
    )
    report.writeback_results["campaign_run"] = build_campaign_run(
        campaign_summary,
        actions,
        writeback_target=args.writeback_target,
        apply=args.writeback_apply,
    )
    report.rollback_preview = {
        "available": any(action.get("rollback_available") for action in actions),
        "closures": closures,
    }
    report.action_runs = build_action_runs(
        actions,
        results,
        args.writeback_target,
        args.writeback_apply,
        closures=closures,
    )
    report.external_refs = external_refs


def _apply_governance(report: AuditReport, args, client: GitHubClient | None, output_dir: Path) -> None:
    if not getattr(args, "governance_approve", None) and not getattr(args, "governance_apply", None):
        if report.campaign_summary.get("campaign_type") == "security-review":
            from src.governance_activation import build_governance_actions
            from src.warehouse import load_campaign_run

            source_run = None
            campaign_run = report.writeback_results.get("campaign_run", {}) if isinstance(report.writeback_results, dict) else {}
            if campaign_run.get("generated_at"):
                run_id = f"{report.username}:{report.generated_at.isoformat()}"
                source_run = load_campaign_run(output_dir, run_id) or {
                    "run_id": run_id,
                    "campaign_type": "security-review",
                    "action_runs": report.action_runs,
                }
            if source_run:
                report.governance_preview = build_governance_actions(report.to_dict(), source_run, scope=args.governance_scope)
        return

    from src.governance_activation import (
        apply_governance_actions,
        build_governance_actions,
        build_governance_approval,
        load_report_data_for_run,
        populate_report_with_governance_context,
    )
    from src.warehouse import load_campaign_run

    source_run_id = getattr(args, "governance_approve", None) or getattr(args, "governance_apply", None)
    if not source_run_id:
        return
    source_run = load_campaign_run(output_dir, source_run_id)
    if not source_run:
        print_warning(f"Governance source run not found: {source_run_id}")
        return
    if source_run.get("campaign_type") != "security-review":
        print_warning("Governed security activation is only supported for security-review campaign runs.")
        return
    source_report_data = load_report_data_for_run(output_dir, source_run_id)
    if source_report_data is None:
        print_warning(f"Source report for governance run not found: {source_run_id}")
        return

    governance_preview = build_governance_actions(source_report_data, source_run, scope=args.governance_scope)
    report.governance_preview = governance_preview
    populate_report_with_governance_context(report, output_dir=output_dir, source_run_id=source_run_id)

    if getattr(args, "governance_approve", None):
        report.governance_approval = build_governance_approval(source_run, governance_preview, scope=args.governance_scope)
        return

    approval = report.governance_approval
    if not approval:
        print_warning("Governance apply requires a prior approval for this source run.")
        report.governance_results = {
            "source_run_id": source_run_id,
            "scope": args.governance_scope,
            "mode": "apply",
            "results": [],
            "counts": {"applied": 0, "skipped": 0, "failed": 1, "drifted": 0},
            "error": "missing-approval",
        }
        return
    from src.governance_activation import SCOPE_TO_KEYS

    approved_scope = approval.get("scope", "all")
    approved_keys = SCOPE_TO_KEYS.get(approved_scope, set())
    requested_keys = SCOPE_TO_KEYS.get(args.governance_scope, set())
    if not requested_keys.issubset(approved_keys):
        print_warning("Governance apply scope is broader than the approved scope.")
        report.governance_results = {
            "source_run_id": source_run_id,
            "scope": args.governance_scope,
            "mode": "apply",
            "results": [],
            "counts": {"applied": 0, "skipped": 0, "failed": 1, "drifted": 0},
            "error": "scope-broader-than-approval",
        }
        return
    if approval.get("fingerprint") != governance_preview.get("fingerprint"):
        print_warning("Governance apply is blocked because the approved action set no longer matches the current preview.")
        report.governance_results = {
            "source_run_id": source_run_id,
            "scope": args.governance_scope,
            "mode": "apply",
            "results": [],
            "counts": {"applied": 0, "skipped": 0, "failed": 1, "drifted": 0},
            "error": "approval-fingerprint-mismatch",
        }
        return
    if client is None:
        print_warning("Governance apply requires a GitHub client with API access.")
        return

    governance_results, governance_drift = apply_governance_actions(
        client,
        governance_preview,
        approval,
        scope=args.governance_scope,
    )
    governance_results["run_id"] = f"{report.username}:{report.generated_at.isoformat()}:governance"
    report.governance_results = governance_results
    report.governance_drift = governance_drift


def _resolve_review_sync(args) -> str:
    if getattr(args, "review_sync", None):
        return args.review_sync
    from src.notion_client import load_notion_config

    config_path = Path("config") / "notion-config.json"
    if not config_path.is_file():
        return "local"
    config = load_notion_config(Path("config"))
    return "mixed" if config else "local"


def _apply_recurring_review(
    report: AuditReport,
    args,
    output_dir: Path,
    *,
    diff_data: dict | None,
) -> None:
    from src.recurring_review import build_review_bundle

    should_build = bool(getattr(args, "watch", False) or getattr(args, "review_pack", False) or getattr(args, "review_from_latest", False))
    if not should_build:
        return

    review_sync = _resolve_review_sync(args)
    watch_state = {
        "strategy": getattr(args, "watch_strategy", "manual") if getattr(args, "watch", False) else "manual",
        "planned_mode": report.run_mode,
        "review_sync": review_sync,
        "filter_signature": getattr(args, "_watch_filter_signature", ""),
        "reason": getattr(args, "_watch_reason", "manual-review") if getattr(args, "watch", False) else "manual-review",
    }
    bundle = build_review_bundle(
        report.to_dict(),
        output_dir=output_dir,
        diff_data=diff_data,
        materiality=getattr(args, "review_materiality", "standard"),
        portfolio_profile=args.portfolio_profile,
        collection_name=args.collection,
        watch_state=watch_state,
        emit_when_quiet=bool(getattr(args, "review_from_latest", False) or getattr(args, "review_pack", False)),
    )
    report.review_summary = bundle["review_summary"]
    report.review_alerts = bundle["review_alerts"]
    report.material_changes = bundle["material_changes"]
    report.review_targets = bundle["review_targets"]
    report.review_history = bundle["review_history"]
    report.watch_state = bundle["watch_state"]


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
    from src.diff import diff_reports, format_diff_markdown, print_diff_summary
    from src.excel_export import export_excel
    from src.history import (
        archive_report,
        find_previous,
        load_repo_score_history,
        load_trend_data,
        save_fingerprints,
    )
    from src.warehouse import write_warehouse_snapshot

    _apply_ops_writeback(report, args, client, output_dir)
    _apply_governance(report, args, client, output_dir)
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
        if getattr(args, "summary", False):
            print_diff_summary(diff)

    _apply_recurring_review(report, args, output_dir, diff_data=diff_dict)
    report_data = report.to_dict()
    if write_json:
        json_path = write_json_report(report, output_dir)

    trend_data = load_trend_data()
    score_history = load_repo_score_history()
    excel_path = export_excel(
        json_path,
        output_dir / f"audit-dashboard-{report.username}-{_date_str(report.generated_at)}.xlsx",
        trend_data=trend_data,
        diff_data=diff_dict,
        score_history=score_history,
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    md_path = write_markdown_report(report, output_dir, diff_data=diff_dict)
    pcc_path = write_pcc_export(report, output_dir)
    raw_path = write_raw_metadata(report, output_dir)
    warehouse_path = write_warehouse_snapshot(report, output_dir, json_path)

    if archive and write_json:
        archive_report(json_path)
    if save_fingerprint_data:
        save_fingerprints(report_data["audits"])

    badge_info = ""
    if args.badges:
        from src.badge_export import export_badges, upload_badge_gist, _write_badges_markdown

        badge_result = export_badges(report_data, output_dir)
        badge_info = f"\n    {badge_result['badges_md']} ({badge_result['files_written']} badge files)"
        if args.upload_badges:
            gist_urls = upload_badge_gist(output_dir / "badges", report.username)
            if gist_urls:
                _write_badges_markdown(report_data, output_dir / "badges", gist_urls)

    notion_info = ""
    if args.notion:
        from src.notion_export import export_notion_events, _load_project_map
        from src.notion_client import get_notion_token, load_notion_config
        from src.notion_sync import (
            check_recommendation_followup,
            create_audit_action_requests,
            create_audit_history_entry,
            create_recommendation_run,
            patch_project_completeness_cards,
            patch_weekly_review,
            sync_recurring_review,
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

    if report.review_summary and _resolve_review_sync(args) == "mixed":
        from src.notion_client import get_notion_token, load_notion_config
        from src.notion_sync import sync_recurring_review

        sync_token = get_notion_token()
        sync_config = load_notion_config(Path("config"))
        if sync_token and sync_config:
            review_sync_result = sync_recurring_review(report_data, config_dir=Path("config"))
            notion_info += f"\n    recurring-review: {review_sync_result.get('status', 'unknown')}"
        else:
            notion_info += "\n    recurring-review: skipped (notion unavailable)"

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


def _ensure_partial_run_profile_compatible(existing_report_data: dict | None, profile_name: str) -> bool:
    if not existing_report_data:
        return True
    existing_profile = _normalize_profile_name(existing_report_data.get("scoring_profile"))
    if existing_profile == profile_name:
        return True
    print_warning(
        "Latest report was generated with a different scoring profile.\n"
        f"  Existing: {existing_profile} | Requested: {profile_name}\n"
        "  Run a full audit with the desired scoring profile before doing a partial rerun."
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
) -> None:
    """Audit only specific repos and merge into the most recent full report."""
    target_names = _resolve_repo_names(args.repos)
    print_status(f"Targeted audit: {len(target_names)} repos")

    if existing_report_path is None and existing_report_data is None:
        existing_report_path, existing_report_data = _load_latest_report(output_dir)
    if not _ensure_partial_run_profile_compatible(existing_report_data, scoring_profile_name):
        return

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

    portfolio_lang_freq = _compute_portfolio_lang_freq(filtered_repos)
    new_audits = _analyze_repos(
        targeted_repos,
        args=args,
        client=client,
        portfolio_lang_freq=portfolio_lang_freq,
        custom_weights=custom_weights,
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
    )
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
) -> None:
    report = _report_from_dict(existing_report_data)
    needs_fresh_json = bool(
        args.campaign
        or getattr(args, "governance_approve", None)
        or getattr(args, "governance_apply", None)
        or getattr(args, "review_from_latest", False)
    )
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
) -> None:
    """Only re-audit repos whose pushed_at changed since last run."""
    from src.history import load_fingerprints

    existing_report_path, existing_report_data = _load_latest_report(output_dir)
    if not existing_report_path or not existing_report_data:
        print_warning("No previous audit report found. Run a full audit first.")
        return
    if not _ensure_partial_run_profile_compatible(existing_report_data, scoring_profile_name):
        return

    fingerprints = load_fingerprints()
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
        print_info("No changes. Regenerating outputs from latest report.")
        _regenerate_outputs_from_latest_report(
            args,
            output_dir,
            client=client,
            existing_report_path=existing_report_path,
            existing_report_data=existing_report_data,
        )
        return

    original_repos = args.repos
    args.repos = needs_audit
    try:
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
        )
    finally:
        args.repos = original_repos


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


# ── Main entry point ──────────────────────────────────────────────────
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Load config file and merge into args (CLI flags take precedence)
    from src.config import load_config, merge_config_with_args

    config = load_config(Path(args.config) if args.config else None)
    if config:
        merge_config_with_args(args, config)

    # Validate mutually exclusive registry flags
    if args.registry and args.notion_registry:
        parser.error("--registry and --notion-registry cannot be used together")

    # Implied flag dependencies
    if args.upload_badges:
        args.badges = True
    if args.notion_sync:
        args.notion = True
    if args.writeback_apply and not args.writeback_target:
        parser.error("--writeback-apply requires --writeback-target")
    if args.campaign and getattr(args, "campaign_rollback", None):
        parser.error("--campaign and --campaign-rollback cannot be used together")
    if args.writeback_target and not (args.campaign or getattr(args, "campaign_rollback", None)):
        parser.error("--writeback-target requires --campaign or --campaign-rollback")
    if getattr(args, "governance_approve", None) and getattr(args, "governance_apply", None):
        parser.error("--governance-approve and --governance-apply cannot be used together")
    if (getattr(args, "governance_approve", None) or getattr(args, "governance_apply", None)) and args.campaign:
        parser.error("--governance-approve/--governance-apply cannot be combined with --campaign")
    if args.review_from_latest and (args.repos or args.incremental or args.campaign or getattr(args, "campaign_rollback", None)):
        parser.error("--review-from-latest cannot be combined with repo selection, incremental, or campaign flags")
    if args.review_from_latest and args.watch:
        parser.error("--review-from-latest cannot be combined with --watch")
    if args.watch and (
        args.campaign
        or getattr(args, "campaign_rollback", None)
        or args.writeback_target
        or args.writeback_apply
        or getattr(args, "governance_approve", None)
        or getattr(args, "governance_apply", None)
    ):
        parser.error("--watch is recurring-review only and cannot be combined with campaign/governance apply flows")

    custom_weights, scoring_profile_name = _load_scoring_profile(args.scoring_profile)

    if args.review_from_latest:
        output_dir = Path(args.output_dir)
        existing_report_path, existing_report_data = _load_latest_report(output_dir)
        if not existing_report_path or not existing_report_data:
            print_warning("No previous audit report found. Run an audit first.")
            return
        _regenerate_outputs_from_latest_report(
            args,
            output_dir,
            client=None,
            existing_report_path=existing_report_path,
            existing_report_data=existing_report_data,
        )
        return

    def _run_once() -> None:
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

        if getattr(args, "dry_run", False):
            _print_dry_run_summary(repos, args)
            return

        run_repos = args.repos
        run_incremental = args.incremental
        if args.watch:
            from src.recurring_review import choose_watch_plan

            plan = choose_watch_plan(output_dir, args, scoring_profile=scoring_profile_name)
            args._watch_reason = plan.reason
            args._watch_filter_signature = plan.filter_signature
            args._watch_review_sync = _resolve_review_sync(args)
            run_incremental = plan.mode == "incremental"
            if plan.mode == "full":
                run_repos = None
            print_info(f"Watch planner: {plan.mode} ({plan.reason})")

        # Dispatch to partial run mode if requested
        if run_repos:
            original_repos = args.repos
            args.repos = run_repos
            try:
                _run_targeted_audit(
                    args,
                    client,
                    output_dir,
                    all_repos=all_repos,
                    errors=errors,
                    custom_weights=custom_weights,
                    scoring_profile_name=scoring_profile_name,
                )
            finally:
                args.repos = original_repos
            return

        if run_incremental:
            _run_incremental_audit(
                args,
                client,
                output_dir,
                all_repos=all_repos,
                errors=errors,
                custom_weights=custom_weights,
                scoring_profile_name=scoring_profile_name,
            )
            return

        audits = _analyze_repos(
            repos,
            args=args,
            client=client,
            portfolio_lang_freq=_compute_portfolio_lang_freq(repos),
            custom_weights=custom_weights,
        )

        # Full audit path: score every repo and write all output formats
        if audits:
            report = AuditReport.from_audits(
                args.username,
                audits,
                errors,
                total_fetched,
                scoring_profile=scoring_profile_name,
                run_mode="full",
                portfolio_baseline_size=len(repos),
            )
            _apply_requested_reconciliation(report, args, audits)
            outputs = _write_report_outputs(report, args, output_dir, client=client, cache=cache)
            _print_output_summary(f"Audited {report.repos_audited} repos for {report.username}", report, outputs)
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
        from src.watch import run_watch_loop

        args.incremental = True
        run_watch_loop(_run_once, interval=args.watch_interval)
        return

    _run_once()
