from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.notion_registry import load_notion_project_context
from src.portfolio_catalog import group_entry_for_path
from src.portfolio_context_contract import analyze_project_context
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
IGNORE_PROJECT_DIR_NAMES = frozenset({"codex backups"})
# Transient / generated working directories matched by regex on the dir name —
# e.g. a `<repo>-tmp-<timestamp>` clone left behind by a tooling run.
IGNORE_PROJECT_DIR_PATTERNS: tuple[re.Pattern[str], ...] = (re.compile(r"-tmp-\d+$"),)
ARCHIVE_REMOTE_BASENAME_TOKENS = frozenset({"private-archive", "scrubbed-import"})


WORKSPACE_DISCOVERY_POLICY_VERSION = "workspace_discovery.v1"


def workspace_exclusion_reason(name: str) -> str | None:
    """Return the stable policy reason for a non-project directory name."""
    lowered = name.lower()
    if lowered in IGNORE_PROJECT_DIR_NAMES:
        return "backup-container"
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
    return _dedupe_checkouts_by_origin(discovered)


def _dedupe_checkouts_by_origin(
    discovered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse multiple on-disk checkouts of the same repo to one canonical project.

    Linked git worktrees and stray duplicate clones (e.g. ``<repo>-security-fix``
    left behind by multi-repo sweeps) all resolve to the same origin
    (``repo_full_name``), so without this they each count as a distinct project —
    inflating the portfolio count and dragging catalog-completeness toward zero.

    Keep one canonical checkout per origin, preferring the directory whose name
    matches the repo basename, then the shortest name, then alphabetical. Projects
    without an origin are local-only and are never collapsed. Result is sorted by
    name (case-insensitive), matching the prior discovery ordering.
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
        repo_base = origin_key.rsplit("/", 1)[-1]
        canonical.append(
            min(
                group,
                key=lambda p: (
                    str(p.get("name", "")).lower() != repo_base,
                    len(str(p.get("name", ""))),
                    str(p.get("name", "")).lower(),
                ),
            )
        )

    canonical.sort(key=lambda p: str(p.get("name", "")).lower())
    return canonical


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
) -> dict[str, dict[str, str]]:
    raw_context = load_notion_project_context(config_dir) or {}
    sanitized: dict[str, dict[str, str]] = {}
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
    if not git_dir.exists():
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
