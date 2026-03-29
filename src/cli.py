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


def _resolve_repo_names(repos_arg: list[str]) -> list[str]:
    """Extract repo names from URLs or bare names."""
    names = []
    for r in repos_arg:
        r = r.strip().rstrip("/")
        if "/" in r:
            # URL like https://github.com/user/RepoName
            names.append(r.split("/")[-1])
        else:
            names.append(r)
    return names


def _run_targeted_audit(args, client, output_dir: Path) -> None:
    """Audit only specific repos and merge into the most recent full report."""
    import glob as _glob

    target_names = _resolve_repo_names(args.repos)
    print(f"  Targeted audit: {len(target_names)} repos", file=sys.stderr)

    # Fetch metadata only for targeted repos
    owner = args.username
    targeted_repos: list[RepoMetadata] = []
    errors: list[dict] = []

    for name in target_names:
        print(f"  Fetching {owner}/{name}...", file=sys.stderr)
        try:
            languages = client.get_languages(owner, name)
            # Fetch single repo metadata via API
            response = client._request(f"https://api.github.com/repos/{owner}/{name}")
            repo_data = response.json()
            meta = RepoMetadata.from_api_response(repo_data, languages=languages)
            targeted_repos.append(meta)
        except Exception as exc:
            errors.append({"repo": f"{owner}/{name}", "error": str(exc)})
            print(f"  ⚠ Failed to fetch {name}: {exc}", file=sys.stderr)

    if not targeted_repos:
        print("  No repos to audit.", file=sys.stderr)
        return

    # Clone and analyze only targeted repos
    new_audits: list[RepoAudit] = []
    with clone_workspace(targeted_repos, token=args.token) as cloned:
        print(f"  Cloned {len(cloned)}/{len(targeted_repos)} repos. Analyzing...", file=sys.stderr)
        for i, repo_meta in enumerate(targeted_repos, 1):
            repo_path = cloned.get(repo_meta.name)
            if not repo_path:
                continue
            print(f"  [{i}/{len(targeted_repos)}] Analyzing {repo_meta.name}...", file=sys.stderr)
            results = run_all_analyzers(repo_path, repo_meta, client)
            audit = score_repo(repo_meta, results)
            new_audits.append(audit)
            if args.verbose:
                _print_verbose(audit)
    print("  Clones cleaned up", file=sys.stderr)

    # Load the most recent existing report and merge
    existing_reports = sorted(output_dir.glob("audit-report-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    existing_audits: list[dict] = []
    if existing_reports:
        import json as _json
        existing_data = _json.loads(existing_reports[0].read_text())
        existing_audits = existing_data.get("audits", [])
        print(f"  Merging into {existing_reports[0].name} ({len(existing_audits)} existing repos)", file=sys.stderr)

    # Merge: replace existing entries for targeted repos, add new ones
    new_audit_names = {a.metadata.name for a in new_audits}
    # Keep all existing audits that aren't being replaced
    kept = [a for a in existing_audits if a["metadata"]["name"] not in new_audit_names]

    # Convert new audits to dicts and combine
    all_audit_dicts = kept + [a.to_dict() for a in new_audits]

    # Reconstruct RepoAudit objects for AuditReport.from_audits
    # We need the full objects, so rebuild from the new audits + reconstruct from existing dicts
    from src.models import AnalyzerResult
    all_audits_obj: list[RepoAudit] = list(new_audits)
    for ad in kept:
        m = ad["metadata"]
        meta = RepoMetadata(
            name=m["name"], full_name=m["full_name"], description=m.get("description"),
            language=m.get("language"), languages=m.get("languages", {}),
            private=m["private"], fork=m["fork"], archived=m["archived"],
            created_at=datetime.fromisoformat(m["created_at"]) if m.get("created_at") else None,
            updated_at=datetime.fromisoformat(m["updated_at"]) if m.get("updated_at") else None,
            pushed_at=datetime.fromisoformat(m["pushed_at"]) if m.get("pushed_at") else None,
            default_branch=m.get("default_branch", "main"),
            stars=m.get("stars", 0), forks=m.get("forks", 0),
            open_issues=m.get("open_issues", 0), size_kb=m.get("size_kb", 0),
            html_url=m.get("html_url", ""), clone_url=m.get("clone_url", ""),
            topics=m.get("topics", []),
        )
        results_obj = [
            AnalyzerResult(
                dimension=r["dimension"], score=r["score"],
                max_score=r["max_score"], findings=r["findings"],
                details=r.get("details", {}),
            )
            for r in ad.get("analyzer_results", [])
        ]
        audit_obj = RepoAudit(
            metadata=meta, analyzer_results=results_obj,
            overall_score=ad.get("overall_score", 0),
            completeness_tier=ad.get("completeness_tier", "abandoned"),
            interest_score=ad.get("interest_score", 0),
            interest_tier=ad.get("interest_tier", "mundane"),
            grade=ad.get("grade", "F"),
            interest_grade=ad.get("interest_grade", "F"),
            badges=ad.get("badges", []),
            next_badges=ad.get("next_badges", []),
            flags=ad.get("flags", []),
        )
        all_audits_obj.append(audit_obj)

    # Build report
    report = AuditReport.from_audits(
        args.username, all_audits_obj, errors, len(all_audits_obj),
    )

    # Registry reconciliation
    if args.registry:
        from src.registry_parser import parse_registry, reconcile, sync_new_repos
        registry = parse_registry(args.registry)
        report.reconciliation = reconcile(registry, all_audits_obj)
        if args.sync_registry and report.reconciliation.on_github_not_registry:
            sync_new_repos(args.registry, report.reconciliation.on_github_not_registry, all_audits_obj)

    # Generate all reports
    json_path = write_json_report(report, output_dir)
    from src.excel_export import export_excel
    from src.history import load_trend_data, archive_report
    trend_data = load_trend_data()
    excel_path = export_excel(
        json_path,
        output_dir / f"audit-dashboard-{args.username}-{_date_str(report.generated_at)}.xlsx",
        trend_data=trend_data,
    )
    md_path = write_markdown_report(report, output_dir)
    pcc_path = write_pcc_export(report, output_dir)
    raw_path = write_raw_metadata(report, output_dir)
    archive_report(json_path)
    from src.history import save_fingerprints
    save_fingerprints([a.to_dict() for a in all_audits_obj])

    print(
        f"\n✓ Targeted audit: {len(new_audits)} new/updated + {len(kept)} existing = {len(all_audits_obj)} total\n"
        f"  Average score: {report.average_score:.2f}\n"
        f"  Tiers: {report.tier_distribution}\n"
        f"  Reports:\n"
        f"    {json_path}\n"
        f"    {md_path}\n"
        f"    {excel_path}\n"
        f"    {pcc_path}\n"
        f"    {raw_path}",
    )


def _run_incremental_audit(args, client, output_dir: Path) -> None:
    """Only re-audit repos whose pushed_at changed since last run."""
    from src.history import load_fingerprints, save_fingerprints

    fingerprints = load_fingerprints()
    if not fingerprints:
        print("  No fingerprints found. Run a full audit first.", file=sys.stderr)
        print("  Usage: python -m src saagpatel", file=sys.stderr)
        return

    # Fetch metadata (fast, uses cache for list + languages)
    all_repos, errors = client.get_repo_metadata(args.username)
    repos = _filter_repos(all_repos, skip_forks=args.skip_forks, skip_archived=args.skip_archived)

    changed: list[str] = []
    new: list[str] = []
    for repo in repos:
        prev = fingerprints.get(repo.name)
        curr_pushed = repo.pushed_at.isoformat() if repo.pushed_at else None
        if prev is None:
            new.append(repo.name)
        elif prev.get("pushed_at") != curr_pushed:
            changed.append(repo.name)

    needs_audit = changed + new
    unchanged = len(repos) - len(needs_audit)

    print(
        f"  Incremental: {len(needs_audit)} need audit "
        f"({len(changed)} changed, {len(new)} new), {unchanged} unchanged",
        file=sys.stderr,
    )

    if not needs_audit:
        print("  No changes. Regenerating reports from last audit.", file=sys.stderr)
        existing = sorted(output_dir.glob("audit-report-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if existing:
            from src.excel_export import export_excel
            from src.history import load_trend_data
            excel_path = export_excel(
                existing[0],
                output_dir / f"audit-dashboard-{args.username}-{_date_str(datetime.now(timezone.utc))}.xlsx",
                trend_data=load_trend_data(),
            )
            print(f"  Regenerated: {excel_path}", file=sys.stderr)
        return

    # Use targeted audit machinery
    args.repos = needs_audit
    _run_targeted_audit(args, client, output_dir)

    # Save updated fingerprints
    latest = sorted(output_dir.glob("audit-report-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if latest:
        report_data = json.loads(latest[0].read_text())
        save_fingerprints(report_data.get("audits", []))
        print(f"  Fingerprints updated for {len(report_data.get('audits', []))} repos", file=sys.stderr)


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

    # Targeted or incremental audit
    output_dir = Path(args.output_dir)
    if args.repos:
        _run_targeted_audit(args, client, output_dir)
        return
    if args.incremental:
        _run_incremental_audit(args, client, output_dir)
        return

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

        # Compute diff BEFORE Excel so narrative can use it
        from src.history import archive_report, find_previous, load_trend_data, save_fingerprints
        from src.diff import diff_reports, format_diff_markdown

        previous = find_previous(json_path.name)
        diff_source = args.diff or previous
        diff_dict = None

        if diff_source:
            diff = diff_reports(diff_source, json_path)
            diff_dict = diff.to_dict()
            diff_md_path = output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.md"
            diff_md_path.write_text(format_diff_markdown(diff))
            diff_json_path = output_dir / f"audit-diff-{report.username}-{_date_str(report.generated_at)}.json"
            diff_json_path.write_text(json.dumps(diff_dict, indent=2))
            print(
                f"  Diff: {len(diff.tier_changes)} tier changes, "
                f"{len([c for c in diff.score_changes if abs(c['delta']) > 0.05])} significant score changes",
                file=sys.stderr,
            )

        # Excel dashboard (with trend + diff data for narrative)
        from src.excel_export import export_excel
        trend_data = load_trend_data()
        excel_path = export_excel(
            json_path,
            output_dir / f"audit-dashboard-{args.username}-{_date_str(report.generated_at)}.xlsx",
            trend_data=trend_data,
            diff_data=diff_dict,
        )
        md_path = write_markdown_report(report, output_dir)
        pcc_path = write_pcc_export(report, output_dir)
        raw_path = write_raw_metadata(report, output_dir)

        # Archive + fingerprints
        archive_report(json_path)
        save_fingerprints(report.to_dict()["audits"])

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
