from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.notion_registry import load_notion_project_context
from src.portfolio_catalog import group_entry_for_path
from src.portfolio_context_contract import analyze_project_context
from src.portfolio_truth_types import (
    CHECKOUT_COLLISION_SCHEMA_VERSION,
    CHECKOUT_COLLISION_SUMMARY_SCHEMA_VERSION,
)
from src.registry_parser import _normalize

MAX_CONTEXT_DEPTH = 2
MAX_CONTEXT_BYTES = 32_000
SKIP_DIRS = frozenset(
    {
        ".git",
        ".github",
        ".venv",
        ".tox",
        "__pycache__",
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".turbo",
        ".idea",
        ".vscode",
    }
)
TEXT_ALLOWLIST = frozenset(
    {
        "README.md",
        "README.txt",
        "AGENTS.md",
        "CLAUDE.md",
        "DISCOVERY-SUMMARY.md",
        "IMPLEMENTATION-ROADMAP.md",
        "RESUMPTION-PROMPT.md",
        "HANDOFF.md",
        "STATUS.md",
        "PROJECT.md",
        "PLAN.md",
        "ROADMAP.md",
        "NOTES.md",
    }
)
MANIFEST_ALLOWLIST = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "requirements.txt",
        "Package.swift",
        "tauri.conf.json",
        "project.godot",
    }
)
PROJECT_MARKERS = frozenset(
    {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "Package.swift",
        "project.godot",
        "tauri.conf.json",
        "src",
        "tests",
    }
)
# Directory-name substrings (case-insensitive) marking deliberate non-projects.
# A match skips the directory AND its subtree during discovery, so neither the
# container nor anything nested under it reaches the catalog-completeness gate.
#   nogoprjs     -> operator-flagged "no-go" projects, never pursued
#   smoke-export -> generated AuraForge signed-smoke-export bundles (no real repo)
IGNORE_PROJECT_DIR_TOKENS = frozenset({"nogoprjs", "smoke-export"})
IGNORE_PROJECT_DIR_NAMES = frozenset(
    {
        "codex backups",
        "scratch",
        "_backups",
        "_preserved-local-artifacts",
        "sweep-reports",
        "_fable-worktrees",
        "_codex-worktrees",
    }
)
IGNORE_NESTED_PROJECT_DIR_NAMES = frozenset({"packets", "prompts"})
# Transient / generated working directories matched by regex on the dir name —
# e.g. a `<repo>-tmp-<timestamp>` clone left behind by a tooling run.
IGNORE_PROJECT_DIR_PATTERNS: tuple[re.Pattern[str], ...] = (re.compile(r"-tmp-\d+$"),)
ARCHIVE_REMOTE_BASENAME_TOKENS = frozenset({"private-archive", "scrubbed-import"})


WORKSPACE_DISCOVERY_POLICY_VERSION = "workspace_discovery.v3"
MAX_NOTION_SNAPSHOT_AGE_HOURS = 30

_CANONICAL_PATHS_HEADING = re.compile(
    r"^(?P<marks>#{1,6})\s+canonical\s+paths?\s*$", re.IGNORECASE
)
_MARKDOWN_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+\S")
_ABSOLUTE_CODE_PATH = re.compile(r"`(?P<path>/[^`\r\n]+)`")


class NotionProjectContext(dict[str, dict[str, str]]):
    def __init__(
        self,
        *,
        source_mode: str,
        observed_at: str | None,
    ) -> None:
        super().__init__()
        self.source_mode = source_mode
        self.observed_at = observed_at


def workspace_exclusion_reason(name: str, *, nested: bool = False) -> str | None:
    """Return the stable policy reason for a non-project directory name."""
    lowered = name.lower()
    if lowered in {"codex backups", "_backups"}:
        return "backup-container"
    if lowered == "_preserved-local-artifacts":
        return "preserved-artifacts"
    if lowered == "scratch":
        return "scratch-container"
    if lowered == "sweep-reports":
        return "generated-reports"
    if lowered in {"_fable-worktrees", "_codex-worktrees"}:
        return "linked-worktree-container"
    if nested and lowered in IGNORE_NESTED_PROJECT_DIR_NAMES:
        return "nested-content"
    if any(token in lowered for token in IGNORE_PROJECT_DIR_TOKENS):
        return "operator-excluded" if "nogoprjs" in lowered else "generated-evidence"
    if any(pattern.search(name) for pattern in IGNORE_PROJECT_DIR_PATTERNS):
        return "temporary-checkout"
    return None


def _is_ignored_project_dir(name: str) -> bool:
    """True if a directory name is a transient/non-project artifact to skip."""
    return workspace_exclusion_reason(name) is not None


def _record_exclusion(counts: dict[str, int] | None, reason: str | None) -> None:
    if counts is not None and reason is not None:
        counts[reason] = counts.get(reason, 0) + 1


def discover_workspace_projects(
    workspace_root: Path,
    *,
    catalog_data: dict[str, Any],
    now: datetime | None = None,
    exclusion_counts: dict[str, int] | None = None,
    checkout_collisions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    now = now or datetime.now(timezone.utc)

    for child in sorted(workspace_root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir() or child.is_symlink():
            continue
        exclusion_reason = workspace_exclusion_reason(child.name)
        if exclusion_reason is not None:
            _record_exclusion(exclusion_counts, exclusion_reason)
            continue
        if _is_project_dir(child):
            discovered.append(
                _inspect_project_dir(child, workspace_root, catalog_data=catalog_data, now=now)
            )
            continue
        discovered.extend(
            _discover_nested_projects(
                child,
                workspace_root,
                catalog_data=catalog_data,
                now=now,
                depth=2,
                exclusion_counts=exclusion_counts,
            )
        )
    return _dedupe_checkouts_by_origin(
        discovered,
        checkout_collisions=checkout_collisions,
        workspace_root=workspace_root,
        catalog_data=catalog_data,
        now=now,
    )


def _dedupe_checkouts_by_origin(
    discovered: list[dict[str, Any]],
    *,
    checkout_collisions: list[dict[str, Any]] | None = None,
    workspace_root: Path | None = None,
    catalog_data: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Collapse multiple on-disk checkouts of the same repo to one canonical project.

    Linked git worktrees and stray duplicate clones (e.g. ``<repo>-security-fix``
    left behind by multi-repo sweeps) all resolve to the same origin
    (``repo_full_name``), so without this they each count as a distinct project —
    inflating the portfolio count and dragging catalog-completeness toward zero.

    Keep one compatibility representative per origin without claiming checkout
    authority when independent full clones disagree. Every non-representative
    checkout remains visible in ``CheckoutCollisionV1`` evidence. Projects without
    an origin are local-only and are never collapsed. Result is sorted by name
    (case-insensitive), matching the prior discovery ordering.
    """
    by_origin: dict[str, list[dict[str, Any]]] = {}
    canonical: list[dict[str, Any]] = []
    for project in discovered:
        origin = str(project.get("repo_full_name", "") or "").strip()
        if origin:
            by_origin.setdefault(origin.lower(), []).append(project)
        else:
            canonical.append(project)

    for origin_key, group in by_origin.items():
        identity_project = _checkout_representative(group, origin_key)
        authority_group = _checkout_topology_group(
            group,
            workspace_root=workspace_root,
            catalog_data=catalog_data,
            now=now,
        )
        representative = _checkout_representative(authority_group, origin_key)
        canonical_project = _canonical_checkout_project(
            identity_project=identity_project,
            representative=representative,
        )
        has_checkout_declarations = any(
            _checkout_observation(project).get("declared_paths")
            for project in authority_group
        )
        has_topology_failure = any(
            project.get("_worktree_enumeration_failed") is True
            for project in authority_group
        )
        if (
            len(authority_group) > 1
            or has_checkout_declarations
            or has_topology_failure
        ):
            collision = _checkout_collision_record(
                origin=str(representative.get("repo_full_name") or origin_key),
                origin_key=origin_key,
                group=authority_group,
                representative=representative,
                canonical_project_path=str(canonical_project.get("path") or ""),
            )
            canonical_project["checkout_authority"] = collision
            if checkout_collisions is not None:
                checkout_collisions.append(collision)
        canonical.append(canonical_project)

    canonical.sort(key=lambda p: str(p.get("name", "")).lower())
    return canonical


def _checkout_topology_group(
    group: list[dict[str, Any]],
    *,
    workspace_root: Path | None,
    catalog_data: dict[str, Any] | None,
    now: datetime | None,
) -> list[dict[str, Any]]:
    """Add linked worktrees to authority without duplicating logical projects."""
    if workspace_root is None:
        return list(group)
    if catalog_data is None or now is None:
        raise ValueError("topology expansion requires discovery inputs")

    resolved_root = workspace_root.resolve()
    expanded = list(group)
    known_paths = {
        Path(str(project["project_path"])).resolve() for project in group
    }
    published_paths = {str(project.get("path") or "") for project in group}
    external_worktree_count = 0
    for source_project in group:
        project_path = Path(str(source_project["project_path"]))
        try:
            worktree_paths = _git_worktree_paths(project_path)
        except (
            OSError,
            ValueError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            source_project["_worktree_enumeration_failed"] = True
            continue
        for worktree_path in worktree_paths:
            resolved_path = worktree_path.resolve()
            if resolved_path in known_paths:
                continue
            known_paths.add(resolved_path)
            if not _path_is_within(resolved_path, resolved_root):
                external_worktree_count += 1
                opaque_path = (
                    "external-worktree"
                    if external_worktree_count == 1
                    else f"external-worktree-{external_worktree_count}"
                )
                while opaque_path in published_paths:
                    external_worktree_count += 1
                    opaque_path = f"external-worktree-{external_worktree_count}"
                published_paths.add(opaque_path)
                source_observation = _checkout_observation(source_project)
                expanded.append(
                    {
                        "name": opaque_path,
                        "path": opaque_path,
                        "project_path": resolved_root / opaque_path,
                        "repo_full_name": source_project.get("repo_full_name", ""),
                        "_external_worktree": True,
                        "_checkout_observation": {
                            "state": "unknown",
                            "head": None,
                            "branch": None,
                            "dirty": None,
                            "dirty_path_count": None,
                            "git_common_dir": source_observation.get("git_common_dir"),
                            "bare": None,
                            "declared_paths": [],
                        },
                    }
                )
                continue
            try:
                linked_project = _inspect_project_dir(
                    resolved_path,
                    resolved_root,
                    catalog_data=catalog_data,
                    now=now,
                )
            except OSError:
                linked_project = {
                    "name": resolved_path.name,
                    "path": resolved_path.relative_to(resolved_root).as_posix(),
                    "project_path": resolved_path,
                    "_checkout_observation": _checkout_observation({}),
                }
            linked_project["repo_full_name"] = source_project.get("repo_full_name", "")
            expanded.append(linked_project)
    return expanded


def _git_worktree_paths(project_path: Path) -> list[Path]:
    output = _git_read(project_path, "worktree", "list", "--porcelain")
    paths = [
        Path(line.removeprefix("worktree "))
        for line in output.splitlines()
        if line.startswith("worktree ")
    ]
    if not paths:
        raise ValueError("git worktree list returned no worktrees")
    return paths


def checkout_collision_summary(
    collisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the stable portfolio-level collision summary without adding projects."""
    groups = sorted(collisions, key=lambda item: str(item["origin"]).lower())
    ambiguous_group_count = sum(
        item["selection"]["state"] == "unknown" for item in groups
    )
    return {
        "schema_version": CHECKOUT_COLLISION_SUMMARY_SCHEMA_VERSION,
        "state": "unknown" if ambiguous_group_count else "observed",
        "group_count": len(groups),
        "full_clone_group_count": sum(
            int(item["full_clone_count"] > 1) for item in groups
        ),
        "ambiguous_group_count": ambiguous_group_count,
        "discarded_checkout_count": sum(
            len(item["discarded_checkouts"]) for item in groups
        ),
        "groups": groups,
    }


def _checkout_representative(
    group: list[dict[str, Any]], origin_key: str
) -> dict[str, Any]:
    repo_base = origin_key.rsplit("/", 1)[-1]
    return min(
        group,
        key=lambda project: (
            _checkout_observation(project).get("state") != "observed",
            _checkout_observation(project).get("bare") is True,
            str(project.get("name", "")).lower() != repo_base,
            len(Path(str(project.get("path", ""))).parts),
            len(str(project.get("path", ""))),
            str(project.get("path", "")).lower(),
        ),
    )


def _canonical_checkout_project(
    *,
    identity_project: dict[str, Any],
    representative: dict[str, Any],
) -> dict[str, Any]:
    """Keep discovered identity while observing the selected healthy checkout."""
    if identity_project is representative:
        return representative
    canonical = dict(representative)
    for key in ("name", "path", "top_level_dir"):
        if key in identity_project:
            canonical[key] = identity_project[key]
    return canonical


def _checkout_collision_record(
    *,
    origin: str,
    origin_key: str,
    group: list[dict[str, Any]],
    representative: dict[str, Any],
    canonical_project_path: str,
) -> dict[str, Any]:
    clone_groups: dict[str, list[dict[str, Any]]] = {}
    for project in group:
        clone_groups.setdefault(_checkout_clone_key(project), []).append(project)

    representative_clone = _checkout_clone_key(representative)
    declarations, unresolved_declarations = _declared_checkout_evidence(group)
    declared_checkout_paths = sorted(
        {item["target_checkout_path"] for item in declarations}, key=str.lower
    )
    representative_path = str(representative.get("path") or "")

    clone_representatives = [
        _checkout_representative(members, origin_key)
        for members in clone_groups.values()
    ]
    clone_heads = {
        str(_checkout_observation(project).get("head") or "")
        for project in clone_representatives
    }
    observations_complete = all(
        _checkout_observation(project).get("state") == "observed"
        and _checkout_observation(project).get("git_common_dir")
        for project in group
    )
    has_external_worktree = any(
        project.get("_external_worktree") is True for project in group
    )
    has_topology_failure = any(
        project.get("_worktree_enumeration_failed") is True for project in group
    )
    conflicting_heads = len(clone_heads) > 1 or "" in clone_heads

    state = "selected"
    reason_code = "single_clone_topology"
    reason = "all discovered checkouts share one Git common directory"
    if has_topology_failure:
        state = "unknown"
        reason_code = "worktree_enumeration_failed"
        reason = "linked-worktree topology could not be enumerated"
    elif has_external_worktree:
        state = "unknown"
        reason_code = "external_linked_worktree_unobserved"
        reason = "one or more linked worktrees are outside the observed workspace"
    elif not observations_complete:
        state = "unknown"
        reason_code = "checkout_observation_failed"
        reason = "one or more same-origin checkouts could not be observed completely"
    elif len(declared_checkout_paths) > 1:
        state = "unknown"
        reason_code = "conflicting_declared_checkout_paths"
        reason = "canonical path declarations resolve to multiple checkouts"
    elif declared_checkout_paths and representative_path not in declared_checkout_paths:
        state = "unknown"
        reason_code = "declared_path_conflicts_with_representative"
        reason = (
            "canonical path declarations resolve to a different checkout than "
            "the compatibility representative"
        )
    elif unresolved_declarations:
        state = "unknown"
        reason_code = "declared_checkout_path_unresolved"
        reason = "one or more canonical path declarations do not resolve to a checkout"
    elif len(clone_groups) > 1:
        if conflicting_heads:
            state = "unknown"
            reason_code = "conflicting_full_clone_heads"
            reason = (
                "independent same-origin clones have different or unavailable heads"
            )
        elif any(
            _checkout_observation(project).get("dirty") is True
            for project in group
        ):
            state = "unknown"
            reason_code = "full_clone_local_work_present"
            reason = "an independent same-origin clone contains local work"
        else:
            reason_code = "equivalent_full_clones"
            reason = (
                "independent same-origin clones have equivalent observed heads; "
                "the deterministic compatibility representative is selected"
            )
    elif any(
        _checkout_observation(project).get("dirty") is True for project in group
    ):
        state = "unknown"
        reason_code = "linked_worktree_local_work_present"
        reason = "a linked same-origin worktree contains local work"

    checkouts = [
        _published_checkout(
            project,
            representative=representative,
            representative_clone=representative_clone,
        )
        for project in sorted(group, key=lambda item: str(item.get("path", "")).lower())
    ]
    discarded = [
        checkout for checkout in checkouts if checkout["path"] != representative_path
    ]
    return {
        "schema_version": CHECKOUT_COLLISION_SCHEMA_VERSION,
        "origin": origin,
        "canonical_project_path": canonical_project_path,
        "checkout_count": len(group),
        "full_clone_count": len(clone_groups),
        "declared_checkout_paths": declared_checkout_paths,
        "declared_path_evidence": declarations,
        "unresolved_declared_paths": unresolved_declarations,
        "selection": {
            "state": state,
            "reason_code": reason_code,
            "reason": reason,
            "representative_path": representative_path,
            "selected_path": representative_path if state == "selected" else None,
            "rationale": (
                "Compatibility representative prefers a fully observed non-bare "
                "checkout, then an origin-basename match, followed by the shallowest, "
                "shortest, alphabetic workspace-relative path."
            ),
        },
        "checkouts": checkouts,
        "discarded_checkouts": discarded,
    }


def _checkout_clone_key(project: dict[str, Any]) -> str:
    observation = _checkout_observation(project)
    common_dir = str(observation.get("git_common_dir") or "")
    if common_dir and (
        observation.get("state") == "observed"
        or project.get("_external_worktree") is True
    ):
        return f"observed:{common_dir}"
    return f"unknown:{project.get('path', '')}"


def _checkout_observation(project: dict[str, Any]) -> dict[str, Any]:
    value = project.get("_checkout_observation")
    if isinstance(value, dict):
        return value
    return {
        "state": "unknown",
        "head": None,
        "branch": None,
        "dirty": None,
        "dirty_path_count": None,
        "git_common_dir": None,
        "bare": None,
        "declared_paths": [],
    }


def _published_checkout(
    project: dict[str, Any],
    *,
    representative: dict[str, Any],
    representative_clone: str,
) -> dict[str, Any]:
    observation = _checkout_observation(project)
    path = str(project.get("path") or "")
    representative_path = str(representative.get("path") or "")
    if path == representative_path:
        relation = "representative"
    elif _checkout_clone_key(project) == representative_clone:
        relation = "linked_worktree"
    else:
        relation = "independent_full_clone"
    return {
        "path": path,
        "state": str(observation.get("state") or "unknown"),
        "relation": relation,
        "head": observation.get("head"),
        "branch": observation.get("branch"),
        "dirty": observation.get("dirty"),
        "dirty_path_count": observation.get("dirty_path_count"),
        "bare": observation.get("bare"),
    }


def _declared_checkout_evidence(
    group: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[str]]:
    evidence: list[dict[str, str]] = []
    unresolved: set[str] = set()
    for source_project in group:
        observation = _checkout_observation(source_project)
        for declaration in observation.get("declared_paths") or []:
            if declaration.get("scope") == "outside_workspace":
                unresolved.add(str(declaration["workspace_relative_path"]))
                continue
            target = Path(str(declaration["absolute_path"]))
            candidates = [
                project
                for project in group
                if _path_is_within(target, Path(str(project["project_path"])))
            ]
            if not candidates:
                unresolved.add(str(declaration["workspace_relative_path"]))
                continue
            target_project = max(
                candidates,
                key=lambda project: len(Path(str(project["project_path"])).parts),
            )
            evidence.append(
                {
                    "source_path": (
                        f"{source_project['path']}/{declaration['source_file']}"
                    ),
                    "target_checkout_path": str(target_project["path"]),
                }
            )
    unique_evidence = {
        (item["source_path"], item["target_checkout_path"]): item for item in evidence
    }
    return (
        sorted(
            unique_evidence.values(),
            key=lambda item: (
                item["source_path"].lower(),
                item["target_checkout_path"].lower(),
            ),
        ),
        sorted(unresolved, key=str.lower),
    )


def _discover_nested_projects(
    root: Path,
    workspace_root: Path,
    *,
    catalog_data: dict[str, Any],
    now: datetime,
    depth: int,
    exclusion_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if depth <= 0:
        return []

    discovered: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir() or child.is_symlink():
            continue
        exclusion_reason = workspace_exclusion_reason(child.name, nested=True)
        if exclusion_reason is not None:
            _record_exclusion(exclusion_counts, exclusion_reason)
            continue
        if _is_project_dir(child):
            discovered.append(
                _inspect_project_dir(child, workspace_root, catalog_data=catalog_data, now=now)
            )
            continue
        discovered.extend(
            _discover_nested_projects(
                child,
                workspace_root,
                catalog_data=catalog_data,
                now=now,
                depth=depth - 1,
                exclusion_counts=exclusion_counts,
            )
        )
    return discovered


def load_legacy_registry_rows(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.is_file():
        return {}

    rows: dict[str, dict[str, str]] = {}
    section = ""
    header: list[str] = []

    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            header = []
            continue
        if not line.startswith("|"):
            continue

        cols = [cell.strip() for cell in line.split("|")[1:-1]]
        if not cols:
            continue
        lowered = [col.lower() for col in cols]
        if "project" in lowered and "status" in lowered:
            header = lowered
            continue
        if set(line.replace("|", "").strip()) <= {"-", ":", " "}:
            continue
        if len(cols) != len(header) or not header:
            continue

        row = dict(zip(header, cols))
        status = row.get("status", "").lower()
        if status not in {"active", "recent", "parked", "archived"}:
            continue
        project = row.get("project", "").strip()
        if not project:
            continue
        rows[_normalize(project)] = {
            "section": section,
            "project": project,
            "status": status,
            "tool": row.get("tool", "").strip().lower(),
            "context_quality": row.get("context quality", "").strip().lower(),
            "context_files": row.get("context files", "").strip(),
            "stack": row.get("stack", "").strip(),
            "category": row.get("category", "").strip().lower(),
            "notes": row.get("notes", "").strip(),
        }

    return rows


def load_safe_notion_project_context(
    config_dir: Path = Path("config"),
    snapshot_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    raw_context = load_notion_project_context(config_dir)
    source_mode = "live"
    observed_at: str | None = None
    if not raw_context:
        configured_snapshot = snapshot_path or _notion_snapshot_path_from_environment()
        if configured_snapshot:
            raw_context, observed_at = _load_verified_notion_snapshot_context(
                configured_snapshot
            )
            source_mode = "verified-snapshot"
        else:
            raw_context = {}
    sanitized = NotionProjectContext(
        source_mode=source_mode,
        observed_at=observed_at,
    )
    for name, context in raw_context.items():
        sanitized[_normalize(name)] = {
            "portfolio_call": str(context.get("portfolio_call", "") or "").strip(),
            "momentum": str(context.get("momentum", "") or "").strip(),
            "current_state": str(context.get("current_state", "") or "").strip(),
        }
    for raw_alias, target in _load_notion_title_aliases(config_dir).items():
        alias_context = sanitized.get(_normalize(raw_alias))
        if alias_context:
            sanitized.setdefault(_normalize(target), alias_context)
    return sanitized


def _notion_snapshot_path_from_environment() -> Path | None:
    configured = os.environ.get("GHRA_NOTION_SNAPSHOT_PATH", "").strip()
    if not configured:
        return None
    return Path(configured).expanduser()


def _load_verified_notion_snapshot_context(
    snapshot_path: Path,
) -> tuple[dict[str, dict[str, str]], str | None]:
    try:
        payload = json.loads(snapshot_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}, None
    if not isinstance(payload, dict):
        return {}, None
    if payload.get("schema_version") != "2.0.0":
        return {}, None
    projects = payload.get("projects")
    if (
        not isinstance(projects, list)
        or payload.get("project_count") != len(projects)
        or not projects
    ):
        return {}, None
    live_receipt = payload.get("live_read_receipt")
    if (
        not isinstance(live_receipt, dict)
        or live_receipt.get("state") != "verified"
        or live_receipt.get("page_count") != len(projects)
    ):
        return {}, None
    authority_receipt = payload.get("attention_authority_receipt")
    if (
        not isinstance(authority_receipt, dict)
        or authority_receipt.get("state") != "verified"
    ):
        return {}, None
    try:
        generated_at = datetime.fromisoformat(
            str(payload.get("generated_at", "")).replace("Z", "+00:00")
        )
    except ValueError:
        return {}, None
    age_hours = (
        datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)
    ).total_seconds() / 3600
    if age_hours < -(5 / 60) or age_hours > MAX_NOTION_SNAPSHOT_AGE_HOURS:
        return {}, None
    content_bytes = json.dumps(
        projects, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if hashlib.sha256(content_bytes).hexdigest() != payload.get("content_sha256"):
        return {}, None

    context: dict[str, dict[str, str]] = {}
    for project in projects:
        if not isinstance(project, dict):
            continue
        title = str(project.get("title", "") or "").strip()
        if not title:
            continue
        context[title] = {
            "portfolio_call": str(project.get("portfolio_call", "") or "").strip(),
            "momentum": str(
                project.get("momentum") or project.get("operating_queue") or ""
            ).strip(),
            "current_state": str(project.get("current_state", "") or "").strip(),
        }
    return context, generated_at.isoformat()


def _load_notion_title_aliases(config_dir: Path) -> dict[str, str]:
    path = config_dir / "project-registry-overrides.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    aliases = data.get("notion_title_aliases", {})
    if not isinstance(aliases, dict):
        return {}
    return {str(raw): str(target) for raw, target in aliases.items() if raw and target}


def _inspect_project_dir(
    project_path: Path,
    workspace_root: Path,
    *,
    catalog_data: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    relative_path = project_path.relative_to(workspace_root).as_posix()
    group_entry = group_entry_for_path(relative_path, catalog_data)
    context_files = _collect_context_files(project_path)
    stack = _detect_stack(project_path)
    git_facts = _gather_git_facts(project_path)
    checkout_observation = (
        _observe_checkout(project_path, workspace_root=workspace_root)
        if git_facts.get("has_git")
        else {}
    )
    last_activity = git_facts.get("last_commit_at") or _latest_meaningful_mtime(project_path)
    context_analysis = analyze_project_context(project_path, context_files)

    return {
        "name": project_path.name.strip(),
        "project_path": project_path,
        "path": relative_path,
        "top_level_dir": relative_path.split("/", 1)[0],
        "group_entry": group_entry,
        "has_git": bool(git_facts.get("has_git")),
        "repo_full_name": str(git_facts.get("repo_full_name", "") or "").strip(),
        "default_branch": str(git_facts.get("default_branch", "") or "").strip(),
        "context_files": context_files,
        "context_quality": context_analysis.context_quality,
        "primary_context_file": context_analysis.primary_context_file,
        "project_summary_present": context_analysis.project_summary_present,
        "current_state_present": context_analysis.current_state_present,
        "stack_present": context_analysis.stack_present,
        "run_instructions_present": context_analysis.run_instructions_present,
        "known_risks_present": context_analysis.known_risks_present,
        "next_recommended_move_present": context_analysis.next_recommended_move_present,
        "missing_context_fields": context_analysis.missing_fields,
        "supporting_context_files": context_analysis.supporting_context_files,
        "stack": stack,
        "last_meaningful_activity_at": last_activity,
        "inferred_tool_provenance": _infer_tool_provenance(
            project_path, group_entry, context_files
        ),
        "_checkout_observation": checkout_observation,
        "now": now,
    }


def _is_project_dir(path: Path) -> bool:
    try:
        children = list(path.iterdir())
    except OSError:
        return False
    names = {child.name for child in children}
    if ".git" in names:
        return True
    if any(name in PROJECT_MARKERS for name in names):
        return True
    if any(name.endswith((".xcodeproj", ".xcworkspace")) for name in names):
        return True
    visible_files = [
        child for child in children if child.is_file() and not child.name.startswith(".")
    ]
    return bool(visible_files)


def _collect_context_files(project_path: Path) -> list[str]:
    found: list[str] = []
    for candidate in _walk_context_candidates(project_path, depth=MAX_CONTEXT_DEPTH):
        if candidate.name not in TEXT_ALLOWLIST:
            continue
        if candidate.stat().st_size > MAX_CONTEXT_BYTES:
            continue
        found.append(candidate.relative_to(project_path).as_posix())
    return sorted(found)


def _walk_context_candidates(root: Path, *, depth: int) -> list[Path]:
    results: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) > depth:
            continue
        if path.is_file():
            results.append(path)
    return results


def _classify_context_quality(project_path: Path, context_files: list[str]) -> str:
    return analyze_project_context(project_path, context_files).context_quality


# Utility: returns True if context quality is "boilerplate".
# Called indirectly via context analysis pipeline.
def detect_boilerplate_context(project_path: Path, context_files: list[str]) -> bool:
    return analyze_project_context(project_path, context_files).context_quality == "boilerplate"


def _detect_stack(project_path: Path) -> list[str]:
    stack: list[str] = []
    names = {child.name for child in project_path.iterdir() if not child.name.startswith(".")}
    if "Cargo.toml" in names:
        stack.append("Rust")
    if "pyproject.toml" in names or "requirements.txt" in names:
        stack.append("Python")
    if "Package.swift" in names or any(name.endswith(".xcodeproj") for name in names):
        stack.append("Swift")
    if "project.godot" in names:
        stack.append("Godot")
    package_json = project_path / "package.json"
    if package_json.is_file():
        package_data = _read_small_json(package_json)
        dependencies = {
            **(package_data.get("dependencies") or {}),
            **(package_data.get("devDependencies") or {}),
        }
        if "next" in dependencies:
            stack.append("Next.js")
        elif "react" in dependencies:
            stack.append("React")
        else:
            stack.append("Node.js")
        if "typescript" in dependencies or (project_path / "tsconfig.json").exists():
            stack.append("TypeScript")
    if (project_path / "src-tauri" / "tauri.conf.json").is_file() or "tauri.conf.json" in names:
        stack.append("Tauri 2")
    return _dedupe(stack) or ["Unknown"]


def _read_small_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_CONTEXT_BYTES:
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _gather_git_facts(project_path: Path) -> dict[str, Any]:
    git_dir = project_path / ".git"
    if not git_dir.exists() and not _is_bare_repository_root(project_path):
        return {
            "has_git": False,
            "last_commit_at": None,
            "repo_full_name": "",
            "default_branch": "",
        }

    # Computed once; ``last_commit_at`` is the only field the git-log probe below
    # can refine, so every error path returns this base unchanged.
    base = {
        "has_git": True,
        "last_commit_at": None,
        "repo_full_name": _git_remote_full_name(project_path),
        "default_branch": _git_default_branch(project_path),
    }

    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return base

    if result.returncode != 0 or not result.stdout.strip():
        return base

    try:
        return {
            **base,
            "last_commit_at": datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00")),
        }
    except ValueError:
        return base


def _observe_checkout(project_path: Path, *, workspace_root: Path) -> dict[str, Any]:
    """Observe one discovered checkout without fetching or exposing file names."""
    try:
        bare = _git_read(project_path, "rev-parse", "--is-bare-repository") == "true"
        common_dir = _git_read(
            project_path,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
        head_candidate = _git_read_optional(project_path, "rev-parse", "HEAD")
        head = (
            head_candidate
            if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head_candidate)
            else ""
        )
        branch = (
            _git_read_optional(project_path, "symbolic-ref", "--short", "HEAD")
            if bare
            else _git_read_optional(project_path, "branch", "--show-current")
        )
        if bare:
            dirty: bool | None = None
            dirty_path_count: int | None = None
        else:
            status = _git_read(
                project_path,
                "status",
                "--porcelain",
                "--untracked-files=all",
            )
            dirty = bool(status)
            dirty_path_count = len(status.splitlines()) if status else 0
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {
            "state": "unknown",
            "head": None,
            "branch": None,
            "dirty": None,
            "dirty_path_count": None,
            "git_common_dir": None,
            "bare": None,
            "declared_paths": _declared_canonical_paths(
                project_path, workspace_root=workspace_root
            ),
        }
    return {
        "state": "observed",
        "head": head or None,
        "branch": branch or None,
        "dirty": dirty,
        "dirty_path_count": dirty_path_count,
        "git_common_dir": common_dir or None,
        "bare": bare,
        "declared_paths": _declared_canonical_paths(
            project_path, workspace_root=workspace_root
        ),
    }


def _git_read(project_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(project_path), *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout.strip()


def _git_read_optional(project_path: Path, *args: str) -> str:
    try:
        return _git_read(project_path, *args)
    except subprocess.CalledProcessError:
        return ""


def _declared_canonical_paths(
    project_path: Path, *, workspace_root: Path
) -> list[dict[str, str]]:
    declarations: list[dict[str, str]] = []
    resolved_workspace = workspace_root.resolve()
    for source_file in ("AGENTS.md", "CLAUDE.md"):
        path = project_path / source_file
        try:
            if not path.is_file() or path.stat().st_size > MAX_CONTEXT_BYTES:
                continue
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue

        section_level: int | None = None
        for line in lines:
            heading = _MARKDOWN_HEADING.match(line.strip())
            canonical_heading = _CANONICAL_PATHS_HEADING.match(line.strip())
            if canonical_heading:
                section_level = len(canonical_heading.group("marks"))
                continue
            if heading and section_level is not None:
                if len(heading.group("marks")) <= section_level:
                    section_level = None
                continue
            if section_level is None:
                continue
            for match in _ABSOLUTE_CODE_PATH.finditer(line):
                candidate = Path(match.group("path")).resolve()
                if not _path_is_within(candidate, resolved_workspace):
                    declarations.append(
                        {
                            "source_file": source_file,
                            "absolute_path": "",
                            "workspace_relative_path": "external-checkout",
                            "scope": "outside_workspace",
                        }
                    )
                    continue
                declarations.append(
                    {
                        "source_file": source_file,
                        "absolute_path": str(candidate),
                        "workspace_relative_path": candidate.relative_to(
                            resolved_workspace
                        ).as_posix(),
                    }
                )

    unique = {
        (item["source_file"], item["absolute_path"]): item for item in declarations
    }
    return sorted(
        unique.values(),
        key=lambda item: (item["source_file"], item["absolute_path"].lower()),
    )


def _path_is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _is_bare_repository_root(project_path: Path) -> bool:
    """Recognize a conventional bare repository without climbing into parents."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(project_path),
                "rev-parse",
                "--is-bare-repository",
                "--absolute-git-dir",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 2 or lines[0].strip() != "true":
        return False
    try:
        return Path(lines[1].strip()).resolve() == project_path.resolve()
    except OSError:
        return False


def _git_default_branch(project_path: Path) -> str:
    """The repo's default branch from the local ``origin/HEAD`` ref, if set.

    Resolves only local refs (no network). Returns "" when ``origin/HEAD`` is
    not set locally (common for repos that were ``git init``'d rather than
    cloned) — callers fall back to the portfolio default.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

    if result.returncode != 0:
        return ""
    # e.g. "origin/main" -> "main"; partition keeps multi-segment branch names
    # like "origin/release/v1" -> "release/v1" intact.
    return result.stdout.strip().partition("/")[2].strip()


def _git_remote_full_name(project_path: Path) -> str:
    remotes = _git_github_remotes(project_path)
    if not remotes:
        return ""
    return _select_portfolio_identity_remote(project_path.name, remotes)


def _git_github_remotes(project_path: Path) -> list[tuple[str, str]]:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    seen: set[tuple[str, str]] = set()
    remotes: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2] != "(fetch)":
            continue
        remote_name = parts[0].strip()
        full_name = _extract_github_full_name(parts[1])
        if not remote_name or not full_name:
            continue
        key = (remote_name, full_name.lower())
        if key in seen:
            continue
        seen.add(key)
        remotes.append((remote_name, full_name))
    return remotes


def _select_portfolio_identity_remote(checkout_name: str, remotes: list[tuple[str, str]]) -> str:
    """Choose the GitHub repo identity used by portfolio truth.

    ``origin`` remains the normal source of truth. An explicit ``canonical``
    remote wins, and archive/import origins can yield to a remote whose repo
    basename matches the local checkout directory.
    """
    for remote_name, full_name in remotes:
        if remote_name == "canonical":
            return full_name

    origin = next((full_name for remote_name, full_name in remotes if remote_name == "origin"), "")
    if not origin:
        return remotes[0][1]
    if not _is_archive_repo_identity(origin):
        return origin

    checkout_key = checkout_name.lower()
    for remote_name, full_name in remotes:
        if remote_name == "origin" or _is_archive_repo_identity(full_name):
            continue
        if full_name.rsplit("/", 1)[-1].lower() == checkout_key:
            return full_name
    return origin


def _is_archive_repo_identity(full_name: str) -> bool:
    repo_name = full_name.rsplit("/", 1)[-1].lower()
    return any(token in repo_name for token in ARCHIVE_REMOTE_BASENAME_TOKENS)


def _extract_github_full_name(remote_url: str) -> str:
    cleaned = remote_url.strip()
    if not cleaned:
        return ""
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.startswith("git@github.com:"):
        cleaned = cleaned.split("git@github.com:", 1)[1]
    else:
        parsed = urlparse(cleaned)
        if parsed.hostname != "github.com":
            return ""
        cleaned = parsed.path.lstrip("/")
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) < 2:
        return ""
    return f"{parts[-2]}/{parts[-1]}"


def _latest_meaningful_mtime(project_path: Path) -> datetime | None:
    latest: float | None = None
    for path in project_path.rglob("*"):
        if path.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if (
            path.name.startswith(".")
            and path.name not in TEXT_ALLOWLIST
            and path.name not in MANIFEST_ALLOWLIST
        ):
            continue
        if (
            path.name not in TEXT_ALLOWLIST
            and path.name not in MANIFEST_ALLOWLIST
            and path.suffix not in {".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".swift", ".gd"}
        ):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        latest = mtime if latest is None else max(latest, mtime)
    if latest is None:
        return None
    return datetime.fromtimestamp(latest, tz=timezone.utc)


def _infer_tool_provenance(
    project_path: Path, group_entry: dict[str, Any], context_files: list[str]
) -> str:
    declared = str(group_entry.get("tool_provenance", "") or "").strip().lower()
    if declared:
        return declared
    names = {Path(item).name for item in context_files}
    if "AGENTS.md" in names:
        if detect_boilerplate_context(project_path, context_files):
            return "codex"
        return "codex"
    if "CLAUDE.md" in names:
        return "claude-code"
    top_level = project_path.parts[-2].lower() if len(project_path.parts) > 1 else ""
    if "grok" in top_level:
        return "grok"
    if "gpt" in top_level:
        return "gpt"
    return "unknown"


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
