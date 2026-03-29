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
        "--scoring-profile",
        type=str,
        default=None,
        metavar="NAME",
        help="Use a custom scoring profile from config/scoring-profiles/NAME.json",
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
    print_status(f"Targeted audit: {len(target_names)} repos")

    # Fetch metadata only for targeted repos
    owner = args.username
    targeted_repos: list[RepoMetadata] = []
    errors: list[dict] = []

    progress = create_progress()
    if progress:
        with progress:
            task = progress.add_task("Fetching metadata", total=len(target_names))
            for name in target_names:
                progress.update(task, description=f"Fetching {owner}/{name}")
                try:
                    languages = client.get_languages(owner, name)
                    response = client._request(f"https://api.github.com/repos/{owner}/{name}")
                    repo_data = response.json()
                    meta = RepoMetadata.from_api_response(repo_data, languages=languages)
                    targeted_repos.append(meta)
                except Exception as exc:
                    errors.append({"repo": f"{owner}/{name}", "error": str(exc)})
                    print_warning(f"Failed to fetch {name}: {exc}")
                progress.advance(task)
    else:
        for name in target_names:
            print(f"  Fetching {owner}/{name}...", file=sys.stderr)
            try:
                languages = client.get_languages(owner, name)
                response = client._request(f"https://api.github.com/repos/{owner}/{name}")
                repo_data = response.json()
                meta = RepoMetadata.from_api_response(repo_data, languages=languages)
                targeted_repos.append(meta)
            except Exception as exc:
                errors.append({"repo": f"{owner}/{name}", "error": str(exc)})
                print_warning(f"Failed to fetch {name}: {exc}")

    if not targeted_repos:
        print_warning("No repos to audit.")
        return

    # Portfolio language frequency from targeted repos (best available for targeted mode)
    targeted_lang_counts = Counter(r.language for r in targeted_repos if r.language)
    targeted_lang_freq = (
        {lang: count / len(targeted_repos) for lang, count in targeted_lang_counts.items()}
        if targeted_repos else {}
    )

    # Clone and analyze only targeted repos
    new_audits: list[RepoAudit] = []
    progress = create_progress()
    with clone_workspace(targeted_repos, token=args.token,
                         on_progress=lambda i, t, n: None,
                         on_error=lambda n, m: print_warning(f"Failed to clone {n}")) as cloned:
        print_info(f"Cloned {len(cloned)}/{len(targeted_repos)} repos. Analyzing...")
        if progress:
            with progress:
                task = progress.add_task("Analyzing", total=len(targeted_repos))
                for i, repo_meta in enumerate(targeted_repos, 1):
                    repo_path = cloned.get(repo_meta.name)
                    if not repo_path:
                        progress.advance(task)
                        continue
                    progress.update(task, description=f"Analyzing {repo_meta.name}")
                    results = run_all_analyzers(repo_path, repo_meta, client)
                    audit = score_repo(repo_meta, results, portfolio_lang_freq=targeted_lang_freq)
                    new_audits.append(audit)
                    if args.verbose:
                        _print_verbose(audit)
                    progress.advance(task)
        else:
            for i, repo_meta in enumerate(targeted_repos, 1):
                repo_path = cloned.get(repo_meta.name)
                if not repo_path:
                    continue
                print(f"  [{i}/{len(targeted_repos)}] Analyzing {repo_meta.name}...", file=sys.stderr)
                results = run_all_analyzers(repo_path, repo_meta, client)
                audit = score_repo(repo_meta, results, portfolio_lang_freq=targeted_lang_freq)
                new_audits.append(audit)
                if args.verbose:
                    _print_verbose(audit)
    print_info("Clones cleaned up")

    # Load the most recent existing report and merge
    existing_reports = sorted(output_dir.glob("audit-report-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    existing_audits: list[dict] = []
    if existing_reports:
        import json as _json
        existing_data = _json.loads(existing_reports[0].read_text())
        existing_audits = existing_data.get("audits", [])
        print_info(f"Merging into {existing_reports[0].name} ({len(existing_audits)} existing repos)")

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
    from src.history import load_trend_data, archive_report, load_repo_score_history
    trend_data = load_trend_data()
    score_history = load_repo_score_history()
    excel_path = export_excel(
        json_path,
        output_dir / f"audit-dashboard-{args.username}-{_date_str(report.generated_at)}.xlsx",
        trend_data=trend_data,
        score_history=score_history,
    )
    md_path = write_markdown_report(report, output_dir)
    pcc_path = write_pcc_export(report, output_dir)
    raw_path = write_raw_metadata(report, output_dir)
    archive_report(json_path)
    from src.history import save_fingerprints
    save_fingerprints([a.to_dict() for a in all_audits_obj])

    badge_info = ""
    if args.badges:
        from src.badge_export import export_badges, upload_badge_gist, _write_badges_markdown
        badge_result = export_badges(report.to_dict(), output_dir)
        badge_info = f"\n    {badge_result['badges_md']} ({badge_result['files_written']} badge files)"
        if args.upload_badges:
            gist_urls = upload_badge_gist(output_dir / "badges", report.username)
            if gist_urls:
                _write_badges_markdown(report.to_dict(), output_dir / "badges", gist_urls)

    notion_info = ""
    if args.notion:
        from src.notion_export import export_notion_events, _load_project_map
        notion_result = export_notion_events(report.to_dict(), output_dir)
        notion_info = f"\n    {notion_result['events_path']} ({notion_result['event_count']} events, {len(notion_result['unmapped'])} unmapped)"
        if args.notion_sync:
            from src.notion_client import get_notion_token, load_notion_config
            from src.notion_sync import (
                sync_notion_events,
                create_recommendation_run,
                create_audit_action_requests,
                patch_weekly_review,
            )
            sync_notion_events(notion_result["events_path"], Path("config"))
            sync_token = get_notion_token()
            sync_config = load_notion_config(Path("config"))
            if sync_token and sync_config:
                from src.quick_wins import find_quick_wins as _find_qw
                qw = _find_qw(new_audits)
                project_map = _load_project_map(Path("config"))
                create_recommendation_run(report.to_dict(), qw, sync_token, sync_config)
                create_audit_action_requests(
                    report.to_dict().get("audits", []), project_map, sync_token, sync_config,
                )
                patch_weekly_review(report.to_dict(), None, qw, sync_token, sync_config)

    readme_info = ""
    if args.portfolio_readme:
        from src.portfolio_readme import export_portfolio_readme
        readme_result = export_portfolio_readme(report.to_dict(), output_dir)
        readme_info = f"\n    {readme_result['readme_path']}"

    suggestions_info = ""
    if args.readme_suggestions:
        from src.readme_suggestions import generate_readme_suggestions
        sug_result = generate_readme_suggestions(report.to_dict(), output_dir)
        suggestions_info = f"\n    {sug_result['suggestions_path']} ({sug_result['total_suggestions']} suggestions)"

    html_info = ""
    if args.html:
        from src.web_export import export_html_dashboard
        html_result = export_html_dashboard(report.to_dict(), output_dir)
        html_info = f"\n    {html_result['html_path']}"

    print(
        f"\n✓ Targeted audit: {len(new_audits)} new/updated + {len(kept)} existing = {len(all_audits_obj)} total\n"
        f"  Average score: {report.average_score:.2f}\n"
        f"  Tiers: {report.tier_distribution}\n"
        f"  Reports:\n"
        f"    {json_path}\n"
        f"    {md_path}\n"
        f"    {excel_path}\n"
        f"    {pcc_path}\n"
        f"    {raw_path}{badge_info}{notion_info}{readme_info}{suggestions_info}{html_info}",
    )


def _run_incremental_audit(args, client, output_dir: Path) -> None:
    """Only re-audit repos whose pushed_at changed since last run."""
    from src.history import load_fingerprints, save_fingerprints

    fingerprints = load_fingerprints()
    if not fingerprints:
        print_warning("No fingerprints found. Run a full audit first.")
        print_info("Usage: python -m src saagpatel")
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

    print_info(
        f"Incremental: {len(needs_audit)} need audit "
        f"({len(changed)} changed, {len(new)} new), {unchanged} unchanged"
    )

    if not needs_audit:
        print_info("No changes. Regenerating reports from last audit.")
        existing = sorted(output_dir.glob("audit-report-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if existing:
            from src.excel_export import export_excel
            from src.history import load_trend_data
            excel_path = export_excel(
                existing[0],
                output_dir / f"audit-dashboard-{args.username}-{_date_str(datetime.now(timezone.utc))}.xlsx",
                trend_data=load_trend_data(),
            )
            print_info(f"Regenerated: {excel_path}")
        return

    # Use targeted audit machinery
    args.repos = needs_audit
    _run_targeted_audit(args, client, output_dir)

    # Save updated fingerprints
    latest = sorted(output_dir.glob("audit-report-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if latest:
        report_data = json.loads(latest[0].read_text())
        save_fingerprints(report_data.get("audits", []))
        print_info(f"Fingerprints updated for {len(report_data.get('audits', []))} repos")


def main() -> None:
    args = build_parser().parse_args()

    if args.upload_badges:
        args.badges = True
    if args.notion_sync:
        args.notion = True

    # Load custom scoring profile
    custom_weights = None
    if args.scoring_profile:
        profile_path = Path(f"config/scoring-profiles/{args.scoring_profile}.json")
        if profile_path.is_file():
            custom_weights = json.loads(profile_path.read_text())
            print_info(f"Using scoring profile: {args.scoring_profile}")
        else:
            print_warning(f"Scoring profile not found: {profile_path}")

    if not args.token:
        print_warning(
            "No token provided. Only public repos will be fetched.\n"
            "  Set GITHUB_TOKEN or pass --token for private repo access."
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
        print_info("Using GraphQL bulk fetch...")
        raw_repos = bulk_fetch_repos(args.username, args.token)
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
        print_info(f"GraphQL: {len(all_repos)} repos fetched")
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
        print_info(f"Filtered out {skipped} repos ({', '.join(parts) or 'forks/archived'})")

    # Clone and analyze
    audits: list[RepoAudit] = []

    # Portfolio language frequency for relative novelty scoring
    lang_counts = Counter(r.language for r in repos if r.language)
    portfolio_lang_freq = {lang: count / len(repos) for lang, count in lang_counts.items()} if repos else {}

    if not args.skip_clone:
        progress = create_progress()
        with clone_workspace(repos, token=args.token,
                             on_progress=lambda i, t, n: None,
                             on_error=lambda n, m: print_warning(f"Failed to clone {n}")) as cloned:
            print_info(f"Cloned {len(cloned)}/{len(repos)} repos. Analyzing...")
            if progress:
                with progress:
                    task = progress.add_task("Analyzing", total=len(repos))
                    for i, repo_meta in enumerate(repos, 1):
                        repo_path = cloned.get(repo_meta.name)
                        if not repo_path:
                            progress.advance(task)
                            continue
                        progress.update(task, description=f"Analyzing {repo_meta.name}")
                        results = run_all_analyzers(repo_path, repo_meta, client)
                        audit = score_repo(repo_meta, results, portfolio_lang_freq=portfolio_lang_freq, custom_weights=custom_weights)
                        audits.append(audit)
                        if args.verbose:
                            _print_verbose(audit)
                        progress.advance(task)
            else:
                for i, repo_meta in enumerate(repos, 1):
                    repo_path = cloned.get(repo_meta.name)
                    if not repo_path:
                        continue
                    print(
                        f"  [{i}/{len(repos)}] Analyzing {repo_meta.name}...",
                        file=sys.stderr,
                    )
                    results = run_all_analyzers(repo_path, repo_meta, client)
                    audit = score_repo(repo_meta, results, portfolio_lang_freq=portfolio_lang_freq, custom_weights=custom_weights)
                    audits.append(audit)
                    if args.verbose:
                        _print_verbose(audit)

        print_info("Clones cleaned up")

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
            print_info(
                f"Registry: {report.reconciliation.registry_total} projects, "
                f"{len(report.reconciliation.matched)} matched"
            )

            # Auto-sync untracked repos
            if args.sync_registry and report.reconciliation.on_github_not_registry:
                added = sync_new_repos(
                    args.registry,
                    report.reconciliation.on_github_not_registry,
                    audits,
                )
                if added:
                    print_info(
                        f"Synced {len(added)} repos to registry: {', '.join(added[:5])}"
                        + (f"... (+{len(added)-5})" if len(added) > 5 else "")
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
            print_info(
                f"Diff: {len(diff.tier_changes)} tier changes, "
                f"{len([c for c in diff.score_changes if abs(c['delta']) > 0.05])} significant score changes"
            )

        # Excel dashboard (with trend + diff + sparkline data)
        from src.excel_export import export_excel
        from src.history import load_repo_score_history
        trend_data = load_trend_data()
        score_history = load_repo_score_history()
        excel_path = export_excel(
            json_path,
            output_dir / f"audit-dashboard-{args.username}-{_date_str(report.generated_at)}.xlsx",
            trend_data=trend_data,
            diff_data=diff_dict,
            score_history=score_history,
        )
        md_path = write_markdown_report(report, output_dir)
        pcc_path = write_pcc_export(report, output_dir)
        raw_path = write_raw_metadata(report, output_dir)

        # Archive + fingerprints
        archive_report(json_path)
        save_fingerprints(report.to_dict()["audits"])

        # Badge export
        badge_info = ""
        if args.badges:
            from src.badge_export import export_badges, upload_badge_gist, _write_badges_markdown
            badge_result = export_badges(report.to_dict(), output_dir)
            badge_info = f"\n    {badge_result['badges_md']} ({badge_result['files_written']} badge files)"
            if args.upload_badges:
                gist_urls = upload_badge_gist(output_dir / "badges", report.username)
                if gist_urls:
                    _write_badges_markdown(report.to_dict(), output_dir / "badges", gist_urls)

        # Notion export
        notion_info = ""
        if args.notion:
            from src.notion_export import export_notion_events, _load_project_map
            notion_result = export_notion_events(report.to_dict(), output_dir)
            notion_info = f"\n    {notion_result['events_path']} ({notion_result['event_count']} events, {len(notion_result['unmapped'])} unmapped)"
            if args.notion_sync:
                from src.notion_client import get_notion_token, load_notion_config
                from src.notion_sync import (
                    sync_notion_events,
                    create_recommendation_run,
                    create_audit_action_requests,
                    patch_weekly_review,
                )
                sync_notion_events(notion_result["events_path"], Path("config"))
                sync_token = get_notion_token()
                sync_config = load_notion_config(Path("config"))
                if sync_token and sync_config:
                    from src.quick_wins import find_quick_wins as _find_qw
                    qw = _find_qw(audits)
                    project_map = _load_project_map(Path("config"))
                    create_recommendation_run(report.to_dict(), qw, sync_token, sync_config)
                    create_audit_action_requests(
                        report.to_dict().get("audits", []), project_map, sync_token, sync_config,
                    )
                    patch_weekly_review(report.to_dict(), diff_dict, qw, sync_token, sync_config)

        # Notion registry reconciliation
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

        # Portfolio README
        readme_info = ""
        if args.portfolio_readme:
            from src.portfolio_readme import export_portfolio_readme
            readme_result = export_portfolio_readme(report.to_dict(), output_dir)
            readme_info = f"\n    {readme_result['readme_path']}"

        # README suggestions
        suggestions_info = ""
        if args.readme_suggestions:
            from src.readme_suggestions import generate_readme_suggestions
            sug_result = generate_readme_suggestions(report.to_dict(), output_dir)
            suggestions_info = f"\n    {sug_result['suggestions_path']} ({sug_result['total_suggestions']} suggestions)"

        # HTML dashboard
        html_info = ""
        if args.html:
            from src.web_export import export_html_dashboard
            html_result = export_html_dashboard(
                report.to_dict(), output_dir, trend_data, score_history,
            )
            html_info = f"\n    {html_result['html_path']}"

        # Archive candidates
        if args.auto_archive:
            from src.archive_candidates import find_archive_candidates, export_archive_report
            candidates = find_archive_candidates(score_history)
            if candidates:
                archive_result = export_archive_report(candidates, report.username, output_dir)
                print_info(f"Archive candidates: {archive_result['count']} repos → {archive_result['report_path']}")

        # AI narrative
        if args.narrative:
            from src.narrative import generate_narrative
            generate_narrative(report.to_dict(), output_dir)

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
            f"    {raw_path}{badge_info}{notion_info}{readme_info}{suggestions_info}{html_info}",
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
