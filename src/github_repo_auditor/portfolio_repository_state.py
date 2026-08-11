from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_GIT_OID_RE = re.compile(r"^[0-9a-f]{40,64}$")


def observe_repository_state(
    path: Path,
    *,
    observed_at: datetime,
    remote_default_branch: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Read local Git/worktree state without changing refs or exposing file names."""
    remote = (
        dict(remote_default_branch)
        if remote_default_branch
        else {
            "state": "unknown",
            "reason_code": "not_requested",
            "reason": (
                "no independent live remote read was performed by portfolio generation"
            ),
        }
    )
    repository_kind = _repository_kind(path)
    if repository_kind is None:
        return {
            "state": "not_a_repository",
            "observed_at": observed_at.astimezone(UTC).isoformat(),
            "remote_default_branch": remote,
        }

    try:
        worktrees = _observe_worktrees(path, workspace_root=workspace_root)
        selection = _select_remote_default_worktree(worktrees, remote)
        topology = {
            "kind": repository_kind,
            "configured_path": str(path),
            "worktree_count": len(worktrees),
            "linked_worktree_count": sum(
                item.get("state") != "coordinator" for item in worktrees
            )
            - (0 if repository_kind == "bare_coordinator" else 1),
            "selection": selection,
        }

        if repository_kind == "bare_coordinator":
            topology["coordinator"] = _observe_bare_coordinator(path)
            return _bare_repository_result(
                observed_at=observed_at,
                remote=remote,
                worktrees=worktrees,
                topology=topology,
            )

        # `_observe_worktrees` already captured the configured worktree. Re-reading
        # it here creates two different snapshots when another owner is actively
        # editing that checkout: `worktrees` can contain the first dirty count while
        # `local` contains the second. Derive both views from the same observation so
        # the envelope remains internally consistent without hiding the dirty state.
        configured_local = _configured_local_from_worktrees(worktrees, path)
        if remote.get("state") == "observed":
            if selection["state"] != "selected":
                return _unknown_result(
                    observed_at=observed_at,
                    remote=remote,
                    worktrees=worktrees,
                    topology=topology,
                    local=configured_local,
                    reason_code=str(selection["reason_code"]),
                    reason=str(selection["reason"]),
                )
            selected_local = _local_from_worktree(
                _selected_worktree(worktrees, selection)
            )
            return _observed_result(
                observed_at=observed_at,
                remote=remote,
                worktrees=worktrees,
                topology=topology,
                local=selected_local,
            )

        if _tracks_nonmatching_branch(configured_local):
            return _unknown_result(
                observed_at=observed_at,
                remote=remote,
                worktrees=worktrees,
                topology=topology,
                local=configured_local,
                reason_code="nonstandard_upstream_requires_remote_default_evidence",
                reason=(
                    "the configured worktree tracks a differently named branch, "
                    "and independent remote-default evidence is unavailable"
                ),
            )

        return _observed_result(
            observed_at=observed_at,
            remote=remote,
            worktrees=worktrees,
            topology=topology,
            local=configured_local,
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        return {
            "state": "unknown",
            "observed_at": observed_at.astimezone(UTC).isoformat(),
            "reason_code": "repository_observation_failed",
            "reason": str(exc),
            "remote_default_branch": remote,
        }


def _repository_kind(path: Path) -> str | None:
    try:
        is_bare = _git(path, "rev-parse", "--is-bare-repository")
    except (OSError, subprocess.CalledProcessError):
        return None
    if is_bare == "true":
        return "bare_coordinator"
    if is_bare == "false":
        return "working_repository"
    raise ValueError("git returned an invalid repository kind")


def _observe_working_tree(path: Path) -> dict[str, Any]:
    head = _git(path, "rev-parse", "HEAD")
    branch = _git(path, "branch", "--show-current") or None
    dirty = _git(path, "status", "--porcelain", "--untracked-files=all")
    resolved_upstream = _git_optional(
        path, "rev-parse", "--abbrev-ref", "@{upstream}"
    )
    upstream_remote, upstream_branch = _upstream_identity(
        path, branch=branch, upstream=resolved_upstream
    )
    upstream = (
        upstream_branch
        if upstream_remote == "."
        else (
            f"{upstream_remote}/{upstream_branch}"
            if upstream_remote is not None and upstream_branch is not None
            else None
        )
    )
    ahead = behind = None
    if resolved_upstream:
        counts = _git(
            path,
            "rev-list",
            "--left-right",
            "--count",
            f"{resolved_upstream}...HEAD",
        )
        behind_text, ahead_text = counts.split()
        behind, ahead = int(behind_text), int(ahead_text)
    return {
        "path": str(path),
        "head": head,
        "branch": branch,
        "dirty": bool(dirty),
        "dirty_path_count": len(dirty.splitlines()) if dirty else 0,
        "upstream": upstream,
        "upstream_branch": upstream_branch,
        "upstream_remote": upstream_remote,
        "upstream_observation_source": (
            "local_tracking_ref" if upstream else "unavailable"
        ),
        "ahead": ahead,
        "behind": behind,
    }


def _upstream_identity(
    path: Path,
    *,
    branch: str | None,
    upstream: str | None,
) -> tuple[str | None, str | None]:
    if upstream is None:
        return None, None
    if branch is None:
        raise ValueError("detached worktree unexpectedly has an upstream")
    merge_ref = _git_optional(path, "config", "--get", f"branch.{branch}.merge")
    prefix = "refs/heads/"
    if not merge_ref or not merge_ref.startswith(prefix) or merge_ref == prefix:
        raise ValueError("tracked branch has no exact refs/heads merge target")
    upstream_remote = _git_optional(
        path, "config", "--get", f"branch.{branch}.remote"
    )
    if not upstream_remote:
        raise ValueError("tracked branch has no exact configured remote")
    return upstream_remote, merge_ref.removeprefix(prefix)


def _observe_bare_coordinator(path: Path) -> dict[str, Any]:
    head = _git_optional(path, "rev-parse", "--verify", "HEAD^{commit}")
    branch = _git_optional(path, "symbolic-ref", "--short", "HEAD")
    return {
        "path": str(path),
        "head": head,
        "head_state": "observed" if head else "dangling",
        "branch": branch,
    }


def _observe_worktrees(
    path: Path, *, workspace_root: Path | None = None
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    external_worktree_count = 0
    for item in _worktrees(path):
        worktree_path = Path(item["path"])
        if workspace_root is not None and not _path_is_within(
            worktree_path, workspace_root
        ):
            external_worktree_count += 1
            opaque_path = (
                "external-worktree"
                if external_worktree_count == 1
                else f"external-worktree-{external_worktree_count}"
            )
            observed.append(
                {
                    "state": "unknown",
                    "reason_code": "external_worktree_outside_workspace",
                    "reason": (
                        "the linked worktree is outside the observed workspace"
                    ),
                    "path": opaque_path,
                    "head": None,
                    "branch": None,
                    "detached": False,
                    "bare": bool(item.get("bare")),
                    "dirty": None,
                    "dirty_path_count": None,
                }
            )
            continue
        if item.get("bare"):
            observed.append(
                {
                    "state": "coordinator",
                    "path": str(worktree_path),
                    "head": item.get("head"),
                    "branch": item.get("branch"),
                    "detached": False,
                    "bare": True,
                    "dirty": None,
                    "dirty_path_count": None,
                }
            )
            continue
        try:
            local = _observe_working_tree(worktree_path)
        except (OSError, subprocess.CalledProcessError, ValueError):
            observed.append(
                {
                    "state": "unknown",
                    "reason_code": "worktree_observation_failed",
                    "reason": "git could not observe the linked worktree",
                    "path": str(worktree_path),
                    "head": item.get("head"),
                    "branch": item.get("branch"),
                    "detached": item.get("detached", False),
                    "bare": False,
                    "dirty": None,
                    "dirty_path_count": None,
                }
            )
            continue
        observed.append(
            {
                "state": "observed",
                **local,
                "detached": item.get("detached", False),
                "bare": False,
            }
        )
    return observed


def _path_is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _select_remote_default_worktree(
    worktrees: list[dict[str, Any]], remote: dict[str, Any]
) -> dict[str, Any]:
    remote_state = str(remote.get("state") or "unknown")
    source = str(remote.get("source") or "remote_default_branch")
    if remote_state != "observed":
        return {
            "source": source,
            "state": "unknown",
            "reason_code": "remote_default_branch_unavailable",
            "reason": (
                "independent remote-default evidence is not observed "
                f"(state={remote_state})"
            ),
            "candidate_count": 0,
        }

    default_branch = str(remote.get("default_branch") or "")
    head_sha = str(remote.get("head_sha") or "")
    if not default_branch or not _GIT_OID_RE.fullmatch(head_sha):
        return {
            "source": source,
            "state": "unknown",
            "reason_code": "remote_default_branch_malformed",
            "reason": "observed remote-default evidence lacks a valid branch and head",
            "candidate_count": 0,
        }

    head_matches = [
        item
        for item in worktrees
        if item.get("state") == "observed" and item.get("head") == head_sha
    ]
    branch_matches = [
        item for item in head_matches if item.get("branch") == default_branch
    ]
    if len(head_matches) == 1:
        return _selected_worktree_result(
            head_matches[0],
            source=source,
            reason_code="unique_remote_head_match",
            candidate_count=1,
        )
    if len(branch_matches) == 1:
        return _selected_worktree_result(
            branch_matches[0],
            source=source,
            reason_code="default_branch_tiebreak",
            candidate_count=len(head_matches),
        )
    if not head_matches:
        return {
            "source": source,
            "state": "unknown",
            "reason_code": "remote_default_worktree_not_found",
            "reason": "no observed worktree matches the remote default head",
            "candidate_count": 0,
        }
    return {
        "source": source,
        "state": "unknown",
        "reason_code": "ambiguous_remote_default_worktrees",
        "reason": (
            "multiple observed worktrees match the remote default head and no "
            "single default-branch worktree resolves the ambiguity"
        ),
        "candidate_count": len(head_matches),
    }


def _selected_worktree_result(
    worktree: dict[str, Any],
    *,
    source: str,
    reason_code: str,
    candidate_count: int,
) -> dict[str, Any]:
    return {
        "source": source,
        "state": "selected",
        "reason_code": reason_code,
        "reason": None,
        "candidate_count": candidate_count,
        "path": worktree["path"],
        "head": worktree["head"],
        "branch": worktree.get("branch"),
    }


def _selected_worktree(
    worktrees: list[dict[str, Any]], selection: dict[str, Any]
) -> dict[str, Any]:
    selected_path = selection.get("path")
    matches = [
        item
        for item in worktrees
        if item.get("state") == "observed" and item.get("path") == selected_path
    ]
    if len(matches) != 1:
        raise ValueError("selected worktree is no longer uniquely observable")
    return matches[0]


def _local_from_worktree(worktree: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "path",
        "head",
        "branch",
        "dirty",
        "dirty_path_count",
        "upstream",
        "upstream_branch",
        "upstream_remote",
        "upstream_observation_source",
        "ahead",
        "behind",
    )
    return {key: worktree.get(key) for key in keys}


def _configured_local_from_worktrees(
    worktrees: list[dict[str, Any]], path: Path
) -> dict[str, Any]:
    configured_path = path.resolve()
    matches = [
        item
        for item in worktrees
        if item.get("state") == "observed"
        and Path(str(item.get("path") or "")).resolve() == configured_path
    ]
    if len(matches) != 1:
        raise ValueError("configured worktree is not uniquely observable")
    return _local_from_worktree(matches[0])


def _tracks_nonmatching_branch(local: dict[str, Any]) -> bool:
    branch = str(local.get("branch") or "")
    upstream_branch = str(local.get("upstream_branch") or "")
    if not branch or not upstream_branch:
        return False
    return upstream_branch != branch


def _bare_repository_result(
    *,
    observed_at: datetime,
    remote: dict[str, Any],
    worktrees: list[dict[str, Any]],
    topology: dict[str, Any],
) -> dict[str, Any]:
    selection = topology["selection"]
    if selection["state"] != "selected":
        return _unknown_result(
            observed_at=observed_at,
            remote=remote,
            worktrees=worktrees,
            topology=topology,
            local=None,
            reason_code=str(selection["reason_code"]),
            reason=str(selection["reason"]),
        )
    return _observed_result(
        observed_at=observed_at,
        remote=remote,
        worktrees=worktrees,
        topology=topology,
        local=_local_from_worktree(_selected_worktree(worktrees, selection)),
    )


def _observed_result(
    *,
    observed_at: datetime,
    remote: dict[str, Any],
    worktrees: list[dict[str, Any]],
    topology: dict[str, Any],
    local: dict[str, Any],
) -> dict[str, Any]:
    return {
        "state": "observed",
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "local": local,
        "remote_default_branch": remote,
        "topology": topology,
        "worktrees": worktrees,
    }


def _unknown_result(
    *,
    observed_at: datetime,
    remote: dict[str, Any],
    worktrees: list[dict[str, Any]],
    topology: dict[str, Any],
    local: dict[str, Any] | None,
    reason_code: str,
    reason: str,
) -> dict[str, Any]:
    result = {
        "state": "unknown",
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "reason_code": reason_code,
        "reason": reason,
        "remote_default_branch": remote,
        "topology": topology,
        "worktrees": worktrees,
    }
    if local is not None:
        result["local"] = local
    return result


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _git_optional(path: Path, *args: str) -> str | None:
    try:
        return _git(path, *args) or None
    except (OSError, subprocess.CalledProcessError):
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
            current["head"] = (
                None
                if len(value) in {40, 64} and value and set(value) == {"0"}
                else value
            )
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
        elif key == "bare":
            current["bare"] = True
        elif key == "locked":
            current["locked"] = True
        elif key == "prunable":
            current["prunable"] = True
    return items
