#!/usr/bin/env python3
"""Headless batch runner for the `/doc-truth-up` documentation-reconciliation pass.

Reads the triage list (``output/doc-truth-up-targets.json``), and for each selected
repo runs Claude Code headlessly (``claude -p``) with:

- the canonical ``docs/commands/doc-truth-up.md`` prompt (frontmatter stripped),
- the hard edit-scope guard hook wired in via ``--settings`` (``doc_truth_up_guard.py``),
- ``--permission-mode acceptEdits`` so the unattended run applies doc edits itself.

Safety is layered:
1. Prompt says docs-only.                       (instruction)
2. Guard hook blocks non-doc writes / non-git-date Bash.  (hard, per-call)
3. This runner verifies the committed branch diff is doc-only and DISCARDS the
   branch if anything else changed.             (certain backstop)

It never pushes, never commits to main, skips repos with uncommitted tracked changes,
and returns each repo to its original branch — leaving a reviewable ``docs/truth-up-<date>``
branch behind for batch review.

DEFAULT IS DRY-RUN. Pass ``--execute`` to actually invoke Claude.

Usage:
    python scripts/doc_truth_up_batch.py                     # dry-run plan, tier 1
    python scripts/doc_truth_up_batch.py --repo SignalDecay --execute   # pilot one repo
    python scripts/doc_truth_up_batch.py --tier 1 --execute            # full tier-1 batch
    python scripts/doc_truth_up_batch.py --tier all --limit 5 --execute
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CMD_FILE = REPO_ROOT / "docs" / "commands" / "doc-truth-up.md"
GUARD = SCRIPT_DIR / "doc_truth_up_guard.py"
DEFAULT_TARGETS = REPO_ROOT / "output" / "doc-truth-up-targets.json"

ALLOWED_DOC_FILES = {"README.md", "CLAUDE.md", "AGENTS.md", "DOC-RECONCILIATION.md"}
ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


def _doc_only(changed: list[str]) -> list[str]:
    """Return the subset of changed paths that are NOT allowed documentation."""
    violations = []
    for f in changed:
        if f in ALLOWED_DOC_FILES or f == "docs" or f.startswith("docs/"):
            continue
        violations.append(f)
    return violations


def _extract_summary(stdout: str) -> str:
    """Pull the final assistant text out of `claude --output-format json` output.

    The CLI returns either a single result object or a JSON array of message
    objects (the final one carries ``result``). Be tolerant of both and never raise.
    """
    try:
        data = json.loads(stdout)
    except Exception:
        return ""
    candidates = data if isinstance(data, list) else [data]
    for item in reversed(candidates):
        if isinstance(item, dict):
            text = item.get("result") or item.get("text")
            if isinstance(text, str) and text.strip():
                return text[-800:].strip()
    return ""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30
    )


def _prompt_body() -> str:
    """The command file with its YAML frontmatter stripped."""
    text = CMD_FILE.read_text()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[text.find("\n", end + 1) + 1 :]
    return text.strip()


def _settings_file() -> str:
    """Write a temp settings JSON wiring the guard as a PreToolUse hook."""
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
                    "hooks": [{"type": "command", "command": f"python3 {GUARD}"}],
                }
            ]
        }
    }
    fd, path = tempfile.mkstemp(prefix="doc-truth-up-settings-", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(settings, fh)
    return path


def select_targets(args: argparse.Namespace) -> list[dict]:
    targets = json.loads(Path(args.targets).read_text())
    if args.repo:
        targets = [t for t in targets if t["project_key"] == args.repo]
    elif args.tier != "all":
        targets = [t for t in targets if t["tier"] == int(args.tier)]
    if args.limit:
        targets = targets[: args.limit]
    return targets


def run_one(t: dict, prompt: str, settings: str, model: str, timeout: int) -> dict:
    repo = Path(t["abs_path"])
    res = {"project_key": t["project_key"], "abs_path": str(repo)}
    if not (repo / ".git").is_dir():
        return {**res, "status": "skipped", "reason": "not a git repo"}
    porcelain = _git(repo, "status", "--porcelain").stdout.splitlines()
    if any(not line.startswith("??") for line in porcelain):
        return {**res, "status": "skipped", "reason": "uncommitted tracked changes"}

    orig = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    before = {
        b.strip(" *") for b in _git(repo, "branch", "--format=%(refname:short)").stdout.splitlines()
    }

    try:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--settings",
                settings,
                "--permission-mode",
                "acceptEdits",
                "--allowedTools",
                *ALLOWED_TOOLS,
                "--model",
                model,
                "--output-format",
                "json",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _git(repo, "checkout", orig)
        return {**res, "status": "error", "reason": f"timeout after {timeout}s"}

    after = {
        b.strip(" *") for b in _git(repo, "branch", "--format=%(refname:short)").stdout.splitlines()
    }
    new_branches = sorted(after - before)

    # Restore the repo FIRST — before any parsing that could fail — so a later
    # error can never strand the repo on the reconciliation branch.
    _git(repo, "checkout", orig)
    summary = _extract_summary(proc.stdout)

    if not new_branches:
        return {
            **res,
            "status": "no_change",
            "reason": "no branch created",
            "orig_branch": orig,
            "claude_summary": summary,
        }
    if len(new_branches) > 1:
        return {
            **res,
            "status": "error",
            "reason": f"multiple new branches: {new_branches}",
            "claude_summary": summary,
        }

    branch = new_branches[0]
    changed = _git(repo, "diff", "--name-only", f"{base}..{branch}").stdout.split()
    violations = _doc_only(changed)
    if violations:
        _git(repo, "branch", "-D", branch)  # discard non-doc work entirely
        return {
            **res,
            "status": "violation",
            "branch": branch,
            "reason": "non-doc files changed; branch discarded",
            "non_doc_files": violations,
            "claude_summary": summary,
        }
    return {
        **res,
        "status": "ran",
        "branch": branch,
        "changed_files": changed,
        "orig_branch": orig,
        "claude_summary": summary,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Headless /doc-truth-up batch runner.")
    ap.add_argument("--targets", default=str(DEFAULT_TARGETS))
    ap.add_argument("--tier", default="1", choices=["1", "2", "all"])
    ap.add_argument("--repo", default="", help="Run a single repo by project_key (pilot).")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=900, help="Per-repo timeout (seconds).")
    ap.add_argument(
        "--execute", action="store_true", help="Actually invoke Claude (default: dry-run)."
    )
    args = ap.parse_args()

    targets = select_targets(args)
    date = datetime.now().strftime("%Y-%m-%d")
    print(
        f"doc-truth-up batch · {len(targets)} repo(s) · tier={args.tier} · model={args.model}"
        f" · {'EXECUTE' if args.execute else 'DRY-RUN'}"
    )

    if not args.execute:
        for t in targets:
            flags = []
            if t.get("drifted"):
                flags.append("drifted")
            if t.get("disagreement_count"):
                flags.append(f"{t['disagreement_count']} audit-flag")
            print(f"  would run: {t['project_key']:50} {' | '.join(flags) or '—'}")
        print("\n(dry-run — pass --execute to run; --repo <key> to pilot one)")
        return

    prompt, settings = _prompt_body(), _settings_file()
    results = []
    try:
        for i, t in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] {t['project_key']} …", flush=True)
            r = run_one(t, prompt, settings, args.model, args.timeout)
            print(f"    → {r['status']}" + (f" ({r.get('reason')})" if r.get("reason") else ""))
            results.append(r)
    finally:
        os.unlink(settings)

    out = Path(REPO_ROOT) / "output" / f"doc-truth-up-run-{date}.json"
    out.write_text(json.dumps(results, indent=2))
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"\nDone. {by_status}")
    print(f"Results: {out}")
    print("Review each repo's docs/truth-up-* branch, then merge or delete. Nothing was pushed.")


if __name__ == "__main__":
    main()
