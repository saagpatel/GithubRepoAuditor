"""Audit execution application flow.

Conditional imports inside this module preserve optional-feature behavior.
"""

from __future__ import annotations

import argparse
import json
import os
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
from src.control_center_presentation import (
    _normal_audit_next_step_hint,
)
from src.github_client import GitHubClient
from src.models import AuditReport, RepoAudit, RepoMetadata
from src.recurring_review import FULL_REFRESH_DAYS
from src.report_enrichment import build_run_change_counts, build_run_change_summary
from src.report_state import (
    audit_from_dict as _audit_from_dict,
    load_latest_report as _load_latest_report,
    report_from_dict as _report_from_dict,
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
DEFAULT_ANALYSIS_WORKERS = 1
MAX_ANALYSIS_WORKERS = 8
DEFAULT_PORTFOLIO_WORKSPACE = Path.home() / "Projects"
_SCORING_PROFILE_RESERVED_KEYS = frozenset(
    {"stale_threshold_days", "grade_thresholds", "completeness_tiers"}
)


class ScoringProfile(dict[str, float]):
    """Flat profile weights plus optional scoring-constant overrides."""

    def __init__(self, weights: dict[str, float], *, overrides: dict[str, object]) -> None:
        super().__init__(weights)
        self.overrides = overrides
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
            scoring_profile=getattr(custom_weights, "overrides", None),
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

def _load_scoring_profile(profile_name: str | None) -> tuple[dict[str, float] | None, str]:
    normalized = _normalize_profile_name(profile_name)
    if not profile_name:
        return None, normalized

    profile_path = Path(f"config/scoring-profiles/{profile_name}.json")
    if profile_path.is_file():
        print_info(f"Using scoring profile: {profile_name}")
        profile = json.loads(profile_path.read_text())
        overrides = {
            key: profile.pop(key)
            for key in _SCORING_PROFILE_RESERVED_KEYS
            if key in profile
        }
        return ScoringProfile(profile, overrides=overrides), normalized

    print_warning(f"Scoring profile not found: {profile_path}")
    return None, normalized

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
