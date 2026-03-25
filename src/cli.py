from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.analyzers import run_all_analyzers
from src.cloner import clone_workspace
from src.github_client import GitHubClient
from src.models import RepoAudit, RepoMetadata
from src.scorer import score_repo


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
        "--verbose",
        action="store_true",
        help="Print detailed output",
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

    # Fetch metadata from GitHub API
    client = GitHubClient(token=args.token)
    all_repos, errors = client.get_repo_metadata(args.username)
    total_fetched = len(all_repos)

    # Apply filters
    repos = _filter_repos(
        all_repos,
        skip_forks=args.skip_forks,
        skip_archived=args.skip_archived,
    )

    skipped = total_fetched - len(repos)
    if skipped:
        print(f"  Filtered out {skipped} repos (forks/archived)", file=sys.stderr)

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

    # Write JSON output
    output_dir = Path(args.output_dir)
    output_path = _write_json(
        args.username, repos, errors, total_fetched, output_dir,
        audits=audits if audits else None,
    )

    # Summary
    if audits:
        tier_dist = {}
        for a in audits:
            tier_dist[a.completeness_tier] = tier_dist.get(a.completeness_tier, 0) + 1
        avg = sum(a.overall_score for a in audits) / len(audits)
        print(
            f"\n✓ Audited {len(audits)} repos for {args.username}\n"
            f"  Average score: {avg:.2f}\n"
            f"  Tiers: {tier_dist}\n"
            f"  Errors: {len(errors)}\n"
            f"  Output: {output_path}",
        )
    else:
        print(
            f"\n✓ Fetched {total_fetched} repos for {args.username}\n"
            f"  Included: {len(repos)} | Errors: {len(errors)}\n"
            f"  Output: {output_path}",
        )
