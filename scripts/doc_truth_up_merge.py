#!/usr/bin/env python3
"""Fast-forward-merge each `/doc-truth-up` reconciliation branch into the branch it
was cut from, then delete the reconciliation branch. Never pushes.

A reconciliation is, by construction, ``base + exactly one doc-only commit``. This
merger re-establishes that contract independently of the runner before touching
anything, so a corrupt or hand-edited branch can never slip through:

1. The reconciliation branch exists and is exactly ONE commit ahead of ``branch~1``.
2. That commit is doc-only (re-verified here — defense in depth over the runner's
   own backstop).
3. The repo is currently on the branch the reconciliation was cut from, and that
   branch's tip still equals ``branch~1`` (i.e. the base has NOT moved). Otherwise a
   fast-forward would be unsafe / would fold in divergence — SKIP and report.

Only when all three hold does it ``git merge --ff-only`` (never a merge commit, never
loses history, fails closed if the base moved) and then ``git branch -d`` (safe delete,
refuses an unmerged branch). It NEVER pushes and NEVER force-anything.

DEFAULT IS DRY-RUN. Pass ``--execute`` to actually merge.

Usage:
    python scripts/doc_truth_up_merge.py                       # dry-run plan
    python scripts/doc_truth_up_merge.py --repo ArguMap        # dry-run one repo
    python scripts/doc_truth_up_merge.py --execute             # merge + delete all
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = REPO_ROOT / "output" / "doc-truth-up-targets.json"
ALLOWED_DOC_FILES = {"README.md", "CLAUDE.md", "AGENTS.md", "DOC-RECONCILIATION.md"}


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )


def _doc_only(changed: list[str]) -> list[str]:
    """Return the subset of changed paths that are NOT allowed documentation."""
    return [
        f for f in changed if not (f in ALLOWED_DOC_FILES or f == "docs" or f.startswith("docs/"))
    ]


def plan_merge(repo: str, branch: str) -> dict:
    """Decide — by inspection only, no mutation — whether ``branch`` can be safely
    fast-forwarded into the branch it was cut from.

    Returns a dict with ``action`` ∈ {merge, skip} plus the reason (skip) or the
    fast-forward target + verified facts (merge).
    """
    res: dict = {"branch": branch}
    if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode != 0:
        return {**res, "action": "skip", "reason": "no reconciliation branch"}

    cur = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if cur == "HEAD":
        return {**res, "action": "skip", "reason": "detached HEAD — cannot infer base branch"}

    # The base (current branch) must be an ANCESTOR of the reconciliation branch —
    # i.e. the branch was cut from here and `cur` has not diverged. Then a
    # fast-forward is provably clean (no merge commit, no lost history).
    cur_sha = _git(repo, "rev-parse", cur).stdout.strip()
    if _git(repo, "merge-base", cur, branch).stdout.strip() != cur_sha:
        return {
            **res,
            "action": "skip",
            "reason": f"base branch '{cur}' diverged from reconciliation (ff-only unsafe)",
        }

    # Exactly one commit ahead — a reconciliation is base + ONE doc-only commit.
    count = _git(repo, "rev-list", "--count", f"{cur}..{branch}").stdout.strip()
    if count != "1":
        return {
            **res,
            "action": "skip",
            "reason": f"expected exactly 1 commit ahead of '{cur}', found {count}",
        }

    changed = _git(repo, "diff", "--name-only", f"{cur}..{branch}").stdout.split()
    violations = _doc_only(changed)
    if violations:
        return {**res, "action": "skip", "reason": "non-doc files in commit", "non_doc": violations}

    return {**res, "action": "merge", "target": cur, "changed": changed}


def merge_one(repo: str, branch: str, execute: bool) -> dict:
    plan = plan_merge(repo, branch)
    if plan["action"] != "merge" or not execute:
        return plan
    # plan_merge verified the repo is on the target branch and it is an ancestor of
    # the reconciliation branch, so --ff-only is a guaranteed-clean fast-forward.
    m = _git(repo, "merge", "--ff-only", branch)
    if m.returncode != 0:
        return {**plan, "action": "error", "reason": f"ff-merge failed: {m.stderr.strip()[:200]}"}
    d = _git(repo, "branch", "-d", branch)
    if d.returncode != 0:
        return {
            **plan,
            "action": "merged_kept_branch",
            "reason": f"merged, but safe-delete failed: {d.stderr.strip()[:200]}",
        }
    return {**plan, "action": "merged"}


def main() -> None:
    ap = argparse.ArgumentParser(description="FF-merge /doc-truth-up reconciliation branches.")
    ap.add_argument("--targets", default=str(DEFAULT_TARGETS))
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--repo", default="", help="Merge a single repo by project_key.")
    ap.add_argument("--execute", action="store_true", help="Actually merge (default: dry-run).")
    args = ap.parse_args()

    branch = f"docs/truth-up-{args.date}"
    targets = json.loads(Path(args.targets).read_text())
    if args.repo:
        targets = [t for t in targets if t["project_key"] == args.repo]

    print(f"doc-truth-up merge · branch={branch} · {'EXECUTE' if args.execute else 'DRY-RUN'}\n")
    results = []
    for t in targets:
        repo = t["abs_path"]
        if not (Path(repo) / ".git").is_dir() or Path(repo).resolve() == REPO_ROOT:
            continue
        if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode != 0:
            continue  # no reconciliation here — silent, keeps the report focused
        r = merge_one(repo, branch, args.execute)
        r["project_key"] = t["project_key"]
        results.append(r)
        tail = f" → {r['target']}" if r.get("target") else ""
        reason = f"  ({r['reason']})" if r.get("reason") else ""
        verb = "would merge" if (r["action"] == "merge" and not args.execute) else r["action"]
        print(f"  {t['project_key']:46} {verb}{tail}{reason}")

    by_action: dict[str, int] = {}
    for r in results:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
    print(f"\n{by_action}")
    if not args.execute:
        print("(dry-run — pass --execute to merge + delete. Nothing is ever pushed.)")


if __name__ == "__main__":
    main()
