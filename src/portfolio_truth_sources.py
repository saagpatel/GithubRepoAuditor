from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.notion_registry import load_notion_project_context
from src.portfolio_catalog import group_entry_for_path
from src.portfolio_context_contract import analyze_project_context
from src.registry_parser import _normalize

MAX_CONTEXT_DEPTH = 2
MAX_CONTEXT_BYTES = 32_000
SKIP_DIRS = frozenset({
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
})
TEXT_ALLOWLIST = frozenset({
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
})
MANIFEST_ALLOWLIST = frozenset({
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "requirements.txt",
    "Package.swift",
    "tauri.conf.json",
    "project.godot",
})
PROJECT_MARKERS = frozenset({
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
})
def discover_workspace_projects(
    workspace_root: Path,
    *,
    catalog_data: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    now = now or datetime.now(timezone.utc)

    for child in sorted(workspace_root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir() or child.is_symlink():
            continue
        if _is_project_dir(child):
            discovered.append(_inspect_project_dir(child, workspace_root, catalog_data=catalog_data, now=now))
            continue
        discovered.extend(_discover_nested_projects(child, workspace_root, catalog_data=catalog_data, now=now, depth=2))
    return discovered


def _discover_nested_projects(
    root: Path,
    workspace_root: Path,
    *,
    catalog_data: dict[str, Any],
    now: datetime,
    depth: int,
) -> list[dict[str, Any]]:
    if depth <= 0:
        return []

    discovered: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir() or child.is_symlink():
            continue
        if _is_project_dir(child):
            discovered.append(_inspect_project_dir(child, workspace_root, catalog_data=catalog_data, now=now))
            continue
        discovered.extend(_discover_nested_projects(child, workspace_root, catalog_data=catalog_data, now=now, depth=depth - 1))
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


def load_safe_notion_project_context(config_dir: Path = Path("config")) -> dict[str, dict[str, str]]:
    raw_context = load_notion_project_context(config_dir) or {}
    sanitized: dict[str, dict[str, str]] = {}
    for name, context in raw_context.items():
        sanitized[_normalize(name)] = {
            "portfolio_call": str(context.get("portfolio_call", "") or "").strip(),
            "momentum": str(context.get("momentum", "") or "").strip(),
            "current_state": str(context.get("current_state", "") or "").strip(),
        }
    return sanitized


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
        "inferred_tool_provenance": _infer_tool_provenance(project_path, group_entry, context_files),
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
    visible_files = [child for child in children if child.is_file() and not child.name.startswith(".")]
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


def read_context_text(project_path: Path, relative_file: str) -> str:
    path = project_path / relative_file
    if not path.is_file() or path.stat().st_size > MAX_CONTEXT_BYTES:
        return ""
    if path.name not in TEXT_ALLOWLIST:
        return ""
    return path.read_text(errors="replace")


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
        return {"has_git": False, "last_commit_at": None, "repo_full_name": ""}

    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"has_git": True, "last_commit_at": None, "repo_full_name": _git_remote_full_name(project_path)}

    if result.returncode != 0 or not result.stdout.strip():
        return {"has_git": True, "last_commit_at": None, "repo_full_name": _git_remote_full_name(project_path)}

    try:
        return {
            "has_git": True,
            "last_commit_at": datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00")),
            "repo_full_name": _git_remote_full_name(project_path),
        }
    except ValueError:
        return {"has_git": True, "last_commit_at": None, "repo_full_name": _git_remote_full_name(project_path)}


def _git_remote_full_name(project_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

    if result.returncode != 0:
        return ""
    return _extract_github_full_name(result.stdout.strip())


def _extract_github_full_name(remote_url: str) -> str:
    cleaned = remote_url.strip()
    if not cleaned:
        return ""
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.startswith("git@github.com:"):
        cleaned = cleaned.split("git@github.com:", 1)[1]
    elif "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/", 1)[1]
    else:
        return ""
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
        if path.name.startswith(".") and path.name not in TEXT_ALLOWLIST and path.name not in MANIFEST_ALLOWLIST:
            continue
        if path.name not in TEXT_ALLOWLIST and path.name not in MANIFEST_ALLOWLIST and path.suffix not in {".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".swift", ".gd"}:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        latest = mtime if latest is None else max(latest, mtime)
    if latest is None:
        return None
    return datetime.fromtimestamp(latest, tz=timezone.utc)


def _infer_tool_provenance(project_path: Path, group_entry: dict[str, Any], context_files: list[str]) -> str:
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
