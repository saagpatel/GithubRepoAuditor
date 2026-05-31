#!/usr/bin/env python3
"""Collect every `/doc-truth-up` reconciliation into one scrollable review document.

For each Tier-1 target repo it finds either:
- a committed ``docs/truth-up-<date>`` branch  → diff that branch against its base, or
- staged doc changes on the current branch (a husky-blocked repo whose commit could
  not land, e.g. codex-os-managed) → show the staged diff, flagged for manual landing.

Each repo section carries the full ``DOC-RECONCILIATION.md`` sign-off (the per-claim
what/why/evidence + contradictions-for-manual-review) followed by the actual doc diff,
so the operator can review the whole sweep in one pass without opening 28 repos.

Output: ``output/doc-truth-up-review-<date>.md``. Prints only a compact index to stdout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = REPO_ROOT / "output" / "doc-truth-up-targets.json"
DOC_FILES = {"README.md", "CLAUDE.md", "AGENTS.md", "DOC-RECONCILIATION.md"}


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=60)


def _has_branch(repo: str, branch: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def _staged_doc_paths(repo: str) -> list[str]:
    out = _git(repo, "diff", "--cached", "--name-only").stdout.split()
    return [f for f in out if f in DOC_FILES or f.startswith("docs/")]


def _section(repo: str, key: str, *, branch: str | None, staged: bool) -> tuple[str, dict]:
    """Render one repo's review section; return (markdown, index_row).

    For a committed branch we diff the reconciliation commit itself (``branch~1..branch``),
    NOT ``main..branch`` — the branch may have been cut from a non-main branch, in which
    case diffing against main would fold in unrelated divergence.
    """
    rng = f"{branch}~1..{branch}" if branch else "--cached"
    stat = _git(repo, "diff", "--stat", rng).stdout.strip()
    # full DOC-RECONCILIATION.md (from the branch, or staged index)
    recon = (
        _git(repo, "show", f"{branch}:DOC-RECONCILIATION.md").stdout
        if branch
        else _git(repo, "show", ":DOC-RECONCILIATION.md").stdout
    )
    # diff of the doc changes, excluding the recon file (shown in full above)
    doc_diff = _git(repo, "diff", rng, "--", ".", ":!DOC-RECONCILIATION.md").stdout.strip()
    files = [ln for ln in stat.splitlines()]
    tag = f"branch `{branch}`" if branch else "**STAGED on main — husky-blocked, land manually**"
    md = [
        f"## {key}",
        f"- {tag}",
        "```",
        stat or "(no stat)",
        "```",
        "<details><summary>DOC-RECONCILIATION.md (sign-off)</summary>",
        "",
        recon.strip() or "(missing)",
        "",
        "</details>",
        "",
        "<details><summary>Doc diff</summary>",
        "",
        "```diff",
        doc_diff or "(no non-recon doc changes)",
        "```",
        "</details>",
        "",
        "---",
    ]
    row = {
        "repo": key,
        "mode": "branch" if branch else "staged",
        "stat": files[-1].strip() if files else "",
    }
    return "\n".join(md), row


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the /doc-truth-up review document.")
    ap.add_argument("--targets", default=str(DEFAULT_TARGETS))
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    branch = f"docs/truth-up-{args.date}"
    targets = json.loads(Path(args.targets).read_text())
    sections, index = [], []
    for t in targets:
        repo, key = t["abs_path"], t["project_key"]
        if not (Path(repo) / ".git").is_dir() or Path(repo).resolve() == REPO_ROOT:
            continue  # skip non-git and the auditor repo itself (self-audit confound)
        # A genuine reconciliation branch carries DOC-RECONCILIATION.md as its marker —
        # this excludes coincidentally-named pre-existing branches (e.g. SignalDecay).
        has_recon = (
            _has_branch(repo, branch)
            and _git(repo, "cat-file", "-e", f"{branch}:DOC-RECONCILIATION.md").returncode == 0
        )
        if has_recon:
            md, row = _section(repo, key, branch=branch, staged=False)
        elif "DOC-RECONCILIATION.md" in _staged_doc_paths(repo):
            md, row = _section(repo, key, branch=None, staged=True)
        else:
            continue
        sections.append(md)
        index.append(row)

    out = (
        Path(args.out) if args.out else REPO_ROOT / "output" / f"doc-truth-up-review-{args.date}.md"
    )
    header = [
        f"# /doc-truth-up review — {args.date}",
        f"{len(index)} repos with documentation reconciliations to review. "
        "Each section: the DOC-RECONCILIATION.md sign-off + the doc diff. Code untouched.",
        "",
    ]
    out.write_text("\n".join(header + sections))

    branches = sum(r["mode"] == "branch" for r in index)
    staged = sum(r["mode"] == "staged" for r in index)
    print(f"{len(index)} repos · {branches} committed branches · {staged} staged (manual)")
    for r in index:
        flag = "" if r["mode"] == "branch" else "  [STAGED/manual]"
        print(f"  {r['repo']:48} {r['stat']}{flag}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
