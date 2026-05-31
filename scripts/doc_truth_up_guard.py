#!/usr/bin/env python3
"""PreToolUse guard for `/doc-truth-up` batch runs — the hard edit-scope enforcement.

Loaded via `claude --settings` so it fires regardless of what the prompt says:

- Edit / Write / MultiEdit / NotebookEdit may target ONLY documentation:
  repo-root ``README.md`` / ``CLAUDE.md`` / ``AGENTS.md`` / ``DOC-RECONCILIATION.md``,
  or anything under a top-level ``docs/`` directory.
- Bash is limited to a safe ``git`` subcommand allowlist plus ``date`` — no app
  execution, no builds/installs/tests, no ``git push``/``reset``/``clean``.
- Read / Grep / Glob are never routed here (matcher excludes them), so investigation
  is unrestricted.

Blocking is done with exit code 2 (Claude Code feeds stderr back to the model and
skips the call). Parse failures fail OPEN — the runner's post-run doc-only diff check
is the certain backstop, so the hook only needs to stop most slips, not all.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

ALLOWED_DOC_FILES = {"README.md", "CLAUDE.md", "AGENTS.md", "DOC-RECONCILIATION.md"}
ALLOWED_GIT_SUBCMDS = {
    "checkout",
    "switch",
    "branch",
    "add",
    "commit",
    "status",
    "diff",
    "log",
    "rev-parse",
    "restore",
}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_SPLIT = re.compile(r"&&|\|\||[;|]")


def _block(reason: str) -> None:
    print(f"[doc-truth-up-guard] BLOCKED: {reason}", file=sys.stderr)
    sys.exit(2)


def _is_doc_path(path: str, cwd: str) -> bool:
    try:
        rel = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd))
    except ValueError:
        return False
    if rel.startswith(".."):  # outside the repo
        return False
    return rel in ALLOWED_DOC_FILES or rel == "docs" or rel.startswith("docs" + os.sep)


def _bash_is_safe(command: str) -> bool:
    # Every chained segment must be a git (allowed subcommand) or date invocation.
    for part in _SPLIT.split(command):
        part = part.strip()
        if not part:
            continue
        try:
            tokens = shlex.split(part)
        except ValueError:
            return False
        if not tokens:
            continue
        if tokens[0] == "date":
            continue
        if tokens[0] == "git" and len(tokens) >= 2 and tokens[1] in ALLOWED_GIT_SUBCMDS:
            continue
        return False
    return True


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail open; runner diff-check is the backstop
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    cwd = data.get("cwd") or os.getcwd()

    if tool in EDIT_TOOLS:
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if not path or not _is_doc_path(path, cwd):
            _block(f"{tool} targets non-documentation path: {path or '(none)'}")
    elif tool == "Bash":
        command = ti.get("command", "")
        if not _bash_is_safe(command):
            _block(f"Bash command outside the git/date allowlist: {command!r}")
    sys.exit(0)


if __name__ == "__main__":
    main()
