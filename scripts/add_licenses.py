#!/usr/bin/env python3
"""Batch-add MIT LICENSE to saagpatel repos missing one.

Reads the audit JSON to identify repos missing a LICENSE, then uses the
GitHub Contents API to create the file on a feature branch — no cloning needed.

Usage:
    python scripts/add_licenses.py [--dry-run] [--audit-file PATH] [--token TOKEN]

Environment:
    GITHUB_TOKEN  GitHub personal access token with repo scope (required)
"""

import argparse
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import requests

OWNER = "saagpatel"
CURRENT_YEAR = 2026
DEFAULT_AUDIT_FILE = Path(__file__).parent.parent / "output" / "audit-report-saagpatel-2026-03-29.json"

MIT_TEMPLATE = """\
MIT License

Copyright (c) {year_range} Saag Patel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


class RepoTarget(NamedTuple):
    name: str
    default_branch: str
    created_year: int


def build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_targets_from_audit(audit_path: Path) -> list[RepoTarget]:
    """Parse audit JSON and return repos missing a license (non-fork, non-archived)."""
    with open(audit_path) as f:
        data = json.load(f)

    targets: list[RepoTarget] = []
    for repo in data["audits"]:
        meta = repo["metadata"]
        name = meta["name"]

        # Skip forks and archived repos
        if meta.get("fork") or meta.get("archived"):
            continue

        # Check community_profile missing list
        community = next(
            (r for r in repo["analyzer_results"] if r["dimension"] == "community_profile"),
            None,
        )
        if community is None:
            continue

        missing = community.get("details", {}).get("missing", [])
        if "license" not in missing:
            continue

        created_year = datetime.fromisoformat(meta["created_at"].replace("Z", "+00:00")).year
        default_branch = meta.get("default_branch", "main")
        targets.append(RepoTarget(name=name, default_branch=default_branch, created_year=created_year))

    return targets


def build_mit_license(created_year: int) -> str:
    year_range = str(created_year) if created_year == CURRENT_YEAR else f"{created_year}-{CURRENT_YEAR}"
    return MIT_TEMPLATE.format(year_range=year_range)


def license_already_exists(name: str, headers: dict) -> bool:
    """Check if any common LICENSE variant already exists on the default branch."""
    for filename in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"):
        url = f"https://api.github.com/repos/{OWNER}/{name}/contents/{filename}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return True
    return False


def get_branch_sha(name: str, branch: str, headers: dict) -> str | None:
    url = f"https://api.github.com/repos/{OWNER}/{name}/git/ref/heads/{branch}"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()["object"]["sha"]


def create_branch(name: str, branch: str, sha: str, headers: dict) -> bool:
    url = f"https://api.github.com/repos/{OWNER}/{name}/git/refs"
    payload = {"ref": f"refs/heads/{branch}", "sha": sha}
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    if r.status_code == 422:
        # Branch already exists — that's fine, we can still push to it
        return True
    return r.status_code == 201


def create_license_file(name: str, branch: str, content: str, headers: dict) -> bool:
    url = f"https://api.github.com/repos/{OWNER}/{name}/contents/LICENSE"
    encoded = base64.b64encode(content.encode()).decode()
    payload = {
        "message": "chore: add MIT license",
        "content": encoded,
        "branch": branch,
    }
    r = requests.put(url, json=payload, headers=headers, timeout=10)
    return r.status_code in (200, 201)


def process_repo(target: RepoTarget, headers: dict, dry_run: bool) -> tuple[str, str]:
    """Process a single repo. Returns (name, status)."""
    name = target.name
    feature_branch = f"feat/{name}-license"

    try:
        # Double-check license doesn't exist (audit data could be stale)
        if license_already_exists(name, headers):
            return name, "skipped (license exists)"

        if dry_run:
            license_text = build_mit_license(target.created_year)
            year_range = str(target.created_year) if target.created_year == CURRENT_YEAR else f"{target.created_year}-{CURRENT_YEAR}"
            return name, f"dry-run (would add LICENSE, copyright {year_range})"

        # Get current HEAD SHA
        sha = get_branch_sha(name, target.default_branch, headers)
        if sha is None:
            return name, "failed (could not get branch SHA)"

        # Create feature branch
        if not create_branch(name, feature_branch, sha, headers):
            return name, "failed (could not create branch)"

        # Create LICENSE file
        license_text = build_mit_license(target.created_year)
        if not create_license_file(name, feature_branch, license_text, headers):
            return name, "failed (could not create LICENSE file)"

        return name, f"success (branch: {feature_branch})"

    except requests.RequestException as e:
        return name, f"failed (network error: {e})"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-add MIT LICENSE to repos missing one")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without making changes")
    parser.add_argument("--audit-file", type=Path, default=DEFAULT_AUDIT_FILE, help="Path to audit JSON file")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token (default: $GITHUB_TOKEN)")
    parser.add_argument("--workers", type=int, default=10, help="Parallel workers (default: 10)")
    args = parser.parse_args()

    if not args.token:
        print("Error: GITHUB_TOKEN not set. Pass --token or set the env var.", file=sys.stderr)
        sys.exit(1)

    if not args.audit_file.exists():
        print(f"Error: audit file not found: {args.audit_file}", file=sys.stderr)
        sys.exit(1)

    headers = build_headers(args.token)
    targets = get_targets_from_audit(args.audit_file)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Found {len(targets)} repos to process")
    print()

    results: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_repo, target, headers, args.dry_run): target.name
            for target in targets
        }
        for i, future in enumerate(as_completed(futures), 1):
            name, status = future.result()
            results[name] = status
            icon = "✓" if status.startswith("success") else ("~" if status.startswith(("skipped", "dry-run")) else "✗")
            print(f"[{i:3}/{len(targets)}] {icon} {name}: {status}")
            # Small pause to avoid hammering rate limits
            if not args.dry_run:
                time.sleep(0.05)

    # Summary
    succeeded = sum(1 for s in results.values() if s.startswith("success"))
    skipped = sum(1 for s in results.values() if s.startswith("skipped") or s.startswith("dry-run"))
    failed = sum(1 for s in results.values() if s.startswith("failed"))

    print()
    print("=" * 50)
    print(f"Results: {succeeded} succeeded · {skipped} skipped · {failed} failed")
    if failed:
        print("\nFailed repos:")
        for name, status in sorted(results.items()):
            if status.startswith("failed"):
                print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
