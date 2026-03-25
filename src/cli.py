from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.cloner import clone_workspace
from src.github_client import GitHubClient
from src.models import RepoMetadata


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
) -> Path:
    """Write raw_metadata.json and return the file path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "raw_metadata.json"

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

    # Clone repos to prove the mechanism (Phase 0 — no analysis yet)
    if not args.skip_clone:
        with clone_workspace(repos, token=args.token) as cloned:
            print(
                f"  Successfully cloned {len(cloned)}/{len(repos)} repos",
                file=sys.stderr,
            )
        print("  Clones cleaned up", file=sys.stderr)

    # Write JSON output
    output_dir = Path(args.output_dir)
    output_path = _write_json(args.username, repos, errors, total_fetched, output_dir)

    # Summary
    print(
        f"\n✓ Fetched {total_fetched} repos for {args.username}\n"
        f"  Included: {len(repos)} | Errors: {len(errors)}\n"
        f"  Output: {output_path}",
    )
