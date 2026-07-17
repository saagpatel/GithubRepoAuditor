from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def observe_repository_state(path: Path, *, observed_at: datetime) -> dict[str, Any]:
    """Read local Git/worktree state without changing refs or exposing file names."""
    if not (path / ".git").exists():
        return {
            "state": "not_a_repository",
            "observed_at": observed_at.astimezone(UTC).isoformat(),
        }
    try:
        head = _git(path, "rev-parse", "HEAD")
        branch = _git(path, "branch", "--show-current") or None
        dirty = _git(path, "status", "--porcelain", "--untracked-files=all")
        upstream = _git_optional(path, "rev-parse", "--abbrev-ref", "@{upstream}")
        ahead = behind = None
        if upstream:
            counts = _git(path, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
            behind_text, ahead_text = counts.split()
            behind, ahead = int(behind_text), int(ahead_text)
        worktrees = []
        for item in _worktrees(path):
            worktree_path = Path(item["path"])
            worktree_dirty = _git(
                worktree_path, "status", "--porcelain", "--untracked-files=all"
            )
            worktrees.append(
                {
                    "path": str(worktree_path),
                    "head": item.get("head"),
                    "branch": item.get("branch"),
                    "detached": item.get("detached", False),
                    "dirty": bool(worktree_dirty),
                    "dirty_path_count": len(worktree_dirty.splitlines()) if worktree_dirty else 0,
                }
            )
        return {
            "state": "observed",
            "observed_at": observed_at.astimezone(UTC).isoformat(),
            "local": {
                "path": str(path),
                "head": head,
                "branch": branch,
                "dirty": bool(dirty),
                "dirty_path_count": len(dirty.splitlines()) if dirty else 0,
                "upstream": upstream,
                "upstream_observation_source": "local_tracking_ref" if upstream else "unavailable",
                "ahead": ahead,
                "behind": behind,
            },
            "remote_default_branch": {
                "state": "unknown",
                "reason": "no independent live remote read was performed by portfolio generation",
            },
            "worktrees": worktrees,
        }
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        return {
            "state": "unknown",
            "observed_at": observed_at.astimezone(UTC).isoformat(),
            "reason": str(exc),
        }


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _git_optional(path: Path, *args: str) -> str | None:
    try:
        return _git(path, *args) or None
    except subprocess.CalledProcessError:
        return None


def _worktrees(path: Path) -> list[dict[str, Any]]:
    output = _git(path, "worktree", "list", "--porcelain")
    items: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in output.splitlines() + [""]:
        if not line:
            if current:
                items.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
    return items
