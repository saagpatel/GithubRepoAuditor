from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.analyzers import run_all_analyzers
from src.cache import ResponseCache
from src.cloner import clone_workspace
from src.github_client import GitHubClient
from src.models import AuditReport, RepoAudit, RepoMetadata
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
    return parser


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


def main() -> None:
    args = build_parser().parse_args()

    if not args.token:
        print(
            "⚠ No token provided. Only public repos will be fetched.\n"
            "  Set GITHUB_TOKEN or pass --token for private repo access.",
            file=sys.stderr,
        )

    # Set up cache
    cache = None if args.no_cache else ResponseCache()

    # Fetch metadata from GitHub API
    client = GitHubClient(token=args.token, cache=cache)

    if args.graphql and args.token:
        from src.graphql_client import bulk_fetch_repos
        print("  Using GraphQL bulk fetch...", file=sys.stderr)
        raw_repos = bulk_fetch_repos(args.username, args.token)
        # Build RepoMetadata from GraphQL results (languages included)
        all_repos = []
        errors = []
        for repo_data in raw_repos:
            try:
                langs = repo_data.pop("_languages", {})
                repo_data.pop("_releases", None)
                meta = RepoMetadata.from_api_response(repo_data, languages=langs)
                all_repos.append(meta)
            except Exception as exc:
                errors.append({"repo": repo_data.get("full_name", "?"), "error": str(exc)})
        print(f"  GraphQL: {len(all_repos)} repos fetched", file=sys.stderr)
    else:
        all_repos, errors = client.get_repo_metadata(args.username)
    total_fetched = len(all_repos)

    # Apply filters
    repos = _filter_repos(
        all_repos,
        skip_forks=args.skip_forks,
        skip_archived=args.skip_archived,
    )

    forks_excluded = sum(1 for r in all_repos if r.fork) if args.skip_forks else 0
    archived_excluded = sum(1 for r in all_repos if r.archived) if args.skip_archived else 0
    skipped = total_fetched - len(repos)
    if skipped:
        parts = []
        if forks_excluded:
            parts.append(f"{forks_excluded} forks")
        if archived_excluded:
            parts.append(f"{archived_excluded} archived")
        print(f"  Filtered out {skipped} repos ({', '.join(parts) or 'forks/archived'})", file=sys.stderr)

    # Clone and analyze
    audits: list[RepoAudit] = []

    if not args.skip_clone:
        with clone_workspace(repos, token=args.token) as cloned:
            print(
                f"  Cloned {len(cloned)}/{len(repos)} repos. Analyzing...",
                file=sys.stderr,
            )
            for i, repo_meta in enumerate(repos, 1):
                repo_path = cloned.get(repo_meta.name)
                if not repo_path:
                    continue
                print(
                    f"  [{i}/{len(repos)}] Analyzing {repo_meta.name}...",
                    file=sys.stderr,
                )
                results = run_all_analyzers(repo_path, repo_meta, client)
                audit = score_repo(repo_meta, results)
                audits.append(audit)
                if args.verbose:
                    _print_verbose(audit)

        print("  Clones cleaned up", file=sys.stderr)

    # Generate reports
    output_dir = Path(args.output_dir)

    if audits:
        report = AuditReport.from_audits(
            args.username, audits, errors, total_fetched,
        )

        # Registry reconciliation
        if args.registry:
            from src.registry_parser import parse_registry, reconcile, sync_new_repos
            registry = parse_registry(args.registry)
            report.reconciliation = reconcile(registry, audits)
            print(
                f"  Registry: {report.reconciliation.registry_total} projects, "
                f"{len(report.reconciliation.matched)} matched",
                file=sys.stderr,
            )

            # Auto-sync untracked repos
            if args.sync_registry and report.reconciliation.on_github_not_registry:
                added = sync_new_repos(
                    args.registry,
                    report.reconciliation.on_github_not_registry,
                    audits,
                )
                if added:
                    print(
                        f"  Synced {len(added)} repos to registry: {', '.join(added[:5])}"
                        + (f"... (+{len(added)-5})" if len(added) > 5 else ""),
                        file=sys.stderr,
                    )

        json_path = write_json_report(report, output_dir)

        # Excel dashboard (with trend data if history exists)
        from src.excel_export import export_excel
        from src.history import load_trend_data
        trend_data = load_trend_data()
        excel_path = export_excel(
            json_path,
            output_dir / f"audit-dashboard-{args.username}-{_date_str(report.generated_at)}.xlsx",
            trend_data=trend_data,
        )
        md_path = write_markdown_report(report, output_dir)
        pcc_path = write_pcc_export(report, output_dir)
        raw_path = write_raw_metadata(report, output_dir)

        # Auto-archive + auto-diff (historical tracking)
        from src.history import archive_report, find_previous
        from src.diff import diff_reports, format_diff_markdown

        # Find previous report before archiving the new one
        previous = find_previous(json_path.name)

        # If --diff is explicitly set, use that instead
        diff_source = args.diff or previous

        if diff_source:
            diff = diff_reports(diff_source, json_path)
            diff_md_path = output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.md"
            diff_md_path.write_text(format_diff_markdown(diff))
            diff_json_path = output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.json"
            diff_json_path.write_text(__import__("json").dumps(diff.to_dict(), indent=2))
            print(
                f"  Diff: {len(diff.tier_changes)} tier changes, "
                f"{len([c for c in diff.score_changes if abs(c['delta']) > 0.05])} significant score changes",
                file=sys.stderr,
            )

        # Archive the current report
        archive_report(json_path)

        cache_info = ""
        if cache:
            cache_info = f"\n  Cache: {cache.hits} hits, {cache.misses} misses"

        print(
            f"\n✓ Audited {report.repos_audited} repos for {report.username}\n"
            f"  Average score: {report.average_score:.2f}\n"
            f"  Tiers: {report.tier_distribution}\n"
            f"  Errors: {len(report.errors)}{cache_info}\n"
            f"  Reports:\n"
            f"    {json_path}\n"
            f"    {md_path}\n"
            f"    {excel_path}\n"
            f"    {pcc_path}\n"
            f"    {raw_path}",
        )
    else:
        raw_path = _write_json(
            args.username, repos, errors, total_fetched, output_dir,
        )
        print(
            f"\n✓ Fetched {total_fetched} repos for {args.username}\n"
            f"  Included: {len(repos)} | Errors: {len(errors)}\n"
            f"  Output: {raw_path}",
        )
