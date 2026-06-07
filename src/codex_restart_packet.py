from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.portfolio_truth_types import TRUTH_LATEST_FILENAME

DEFAULT_WORKSPACE_ROOT = Path.home() / "Projects"
DEFAULT_OPERATING_REPOS = (
    Path.home() / ".local/share/personal-ops",
    Path.home() / ".codex/codexkit",
    Path.home() / "Projects/GithubRepoAuditor",
    Path.home() / "Projects/PortfolioCommandCenter",
    Path.home() / "Projects/Notion",
    Path.home() / "Projects/bridge-db",
    Path.home() / "Projects/notification-hub",
    Path.home() / "Projects/cross-system-smoke",
    Path.home() / "Projects/mcpforge",
    Path.home() / "Projects/portfolio-index",
    Path.home() / "Projects/portfolio-health",
)

EXCLUDED_DIR_NAMES = {
    ".build",
    ".cache",
    ".claude",
    ".codex-maintenance",
    ".cowork",
    ".derivedData",
    ".git",
    ".next",
    ".portfolio-noise-archive",
    ".ruff_cache",
    ".serena",
    ".venv",
    "__pycache__",
    "DerivedData",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}

PRIMARY_OPERATING_REPOS = {
    "personal-ops",
    "codexkit",
    "GithubRepoAuditor",
    "PortfolioCommandCenter",
    "Notion",
    "bridge-db",
    "notification-hub",
    "mcpforge",
}


@dataclass(frozen=True)
class GitRepoState:
    path: str
    label: str
    branch: str
    upstream: str
    dirty_count: int
    ahead: int
    behind: int
    remotes: list[str]
    last_commit: str
    operating_repo: bool = False

    @property
    def attention_score(self) -> int:
        score = 0
        if self.operating_repo:
            score += 15
        if self.dirty_count:
            score += 10 + min(self.dirty_count, 10)
        if not self.upstream:
            score += 5
        if self.branch not in {"main", "master"}:
            score += 4
        score += min(self.ahead, 8) + min(self.behind, 8)
        return score

    @property
    def drift_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.operating_repo:
            reasons.append("operating-repo")
        if self.dirty_count:
            reasons.append(f"dirty:{self.dirty_count}")
        if not self.upstream:
            reasons.append("no-upstream")
        if self.branch not in {"main", "master"}:
            reasons.append(f"branch:{self.branch or 'detached'}")
        if self.ahead:
            reasons.append(f"ahead:{self.ahead}")
        if self.behind:
            reasons.append(f"behind:{self.behind}")
        return reasons


def _run_git(repo: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_excluded_path(path: Path, workspace_root: Path) -> bool:
    try:
        relative = path.relative_to(workspace_root)
    except ValueError:
        relative = path
    parts = set(relative.parts)
    if parts & EXCLUDED_DIR_NAMES:
        return True
    return "evals" in parts and "fixtures" in parts


def discover_git_repos(workspace_root: Path) -> list[Path]:
    repos: list[Path] = []
    for current_raw, dirnames, filenames in os.walk(workspace_root):
        current = Path(current_raw)
        if _is_excluded_path(current, workspace_root):
            dirnames[:] = []
            continue
        if current != workspace_root and (".git" in dirnames or ".git" in filenames):
            repos.append(current)
            dirnames[:] = []
            continue
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIR_NAMES]
    return sorted(set(repos), key=lambda path: str(path).lower())


def _parse_ahead_behind(repo: Path, upstream: str) -> tuple[int, int]:
    if not upstream:
        return 0, 0
    raw = _run_git(repo, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    parts = raw.split()
    if len(parts) != 2:
        return 0, 0
    try:
        behind, ahead = int(parts[0]), int(parts[1])
        return ahead, behind
    except ValueError:
        return 0, 0


def read_git_state(repo: Path, *, workspace_root: Path, operating_repo: bool = False) -> GitRepoState:
    dirty_count = len(
        [line for line in _run_git(repo, ["status", "--porcelain=v1"]).splitlines() if line]
    )
    branch = _run_git(repo, ["branch", "--show-current"]) or "DETACHED"
    upstream = _run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    ahead, behind = _parse_ahead_behind(repo, upstream)
    remotes = sorted({line.strip() for line in _run_git(repo, ["remote"]).splitlines() if line})
    last_commit = _run_git(repo, ["log", "-1", "--format=%cI %h %s"])
    try:
        label = str(repo.relative_to(workspace_root))
    except ValueError:
        label = repo.name
    return GitRepoState(
        path=str(repo),
        label=label,
        branch=branch,
        upstream=upstream,
        dirty_count=dirty_count,
        ahead=ahead,
        behind=behind,
        remotes=remotes,
        last_commit=last_commit,
        operating_repo=operating_repo,
    )


def _truth_counts(projects: list[dict[str, Any]], key_path: tuple[str, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for project in projects:
        value: Any = project
        for key in key_path:
            if not isinstance(value, dict):
                value = ""
                break
            value = value.get(key, "")
        counts[str(value or "unspecified")] += 1
    return dict(sorted(counts.items()))


def load_truth_summary(truth_path: Path) -> dict[str, Any]:
    if not truth_path.exists():
        return {
            "path": str(truth_path),
            "available": False,
            "generated_at": "",
            "project_count": 0,
            "warnings": [f"{TRUTH_LATEST_FILENAME} not found"],
        }
    data = json.loads(truth_path.read_text())
    projects = data.get("projects", [])
    return {
        "path": str(truth_path),
        "available": True,
        "schema_version": data.get("schema_version", ""),
        "generated_at": data.get("generated_at", ""),
        "project_count": len(projects),
        "warnings": data.get("warnings", []),
        "source_summary": data.get("source_summary", {}),
        "lifecycle_counts": _truth_counts(projects, ("declared", "lifecycle_state")),
        "operating_path_counts": _truth_counts(projects, ("declared", "operating_path")),
        "context_quality_counts": _truth_counts(projects, ("derived", "context_quality")),
        "risk_tier_counts": _truth_counts(projects, ("risk", "risk_tier")),
    }


def _state_counts(states: Iterable[GitRepoState]) -> dict[str, int]:
    repos = list(states)
    return {
        "total": len(repos),
        "dirty": sum(1 for repo in repos if repo.dirty_count),
        "non_main_or_detached": sum(1 for repo in repos if repo.branch not in {"main", "master"}),
        "no_upstream": sum(1 for repo in repos if not repo.upstream),
        "ahead_or_behind": sum(1 for repo in repos if repo.ahead or repo.behind),
    }


def _active_working_set(states: list[GitRepoState], limit: int = 12) -> list[GitRepoState]:
    selected: dict[str, GitRepoState] = {}
    for repo in states:
        if repo.operating_repo and (repo.label in PRIMARY_OPERATING_REPOS or repo.dirty_count):
            selected[repo.path] = repo
    for repo in sorted(states, key=lambda item: (-item.attention_score, item.label.lower())):
        if repo.attention_score <= 0:
            continue
        selected.setdefault(repo.path, repo)
        if len(selected) >= limit:
            break
    return sorted(selected.values(), key=lambda item: (-item.attention_score, item.label.lower()))[
        :limit
    ]


def build_restart_packet(
    *,
    workspace_root: Path = DEFAULT_WORKSPACE_ROOT,
    truth_path: Path | None = None,
    operating_repos: Iterable[Path] = DEFAULT_OPERATING_REPOS,
) -> dict[str, Any]:
    workspace_root = workspace_root.expanduser().resolve()
    truth_path = (truth_path or workspace_root / "GithubRepoAuditor/output" / TRUTH_LATEST_FILENAME)
    truth_path = truth_path.expanduser().resolve()
    operating_repo_paths = {
        repo.expanduser().resolve() for repo in operating_repos if repo.expanduser().exists()
    }
    discovered = set(discover_git_repos(workspace_root))
    discovered.update(path for path in operating_repo_paths if (path / ".git").exists())
    states = [
        read_git_state(
            repo,
            workspace_root=workspace_root,
            operating_repo=repo.resolve() in operating_repo_paths,
        )
        for repo in sorted(discovered, key=lambda path: str(path).lower())
    ]
    active_set = _active_working_set(states)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "archive_exclusions": sorted(EXCLUDED_DIR_NAMES),
        "truth": load_truth_summary(truth_path),
        "git_summary": _state_counts(states),
        "active_working_set": [
            {
                **asdict(repo),
                "attention_score": repo.attention_score,
                "drift_reasons": repo.drift_reasons,
            }
            for repo in active_set
        ],
        "next_commands": [
            "python -m src.codex_restart_packet --workspace-root /Users/d/Projects",
            "git -C /Users/d/.local/share/personal-ops status --short --branch",
            "git -C /Users/d/.codex/codexkit status --short --branch",
            "audit report saagpatel --portfolio-truth --portfolio-truth-include-security",
        ],
    }


def render_markdown(packet: dict[str, Any]) -> str:
    truth = packet["truth"]
    git_summary = packet["git_summary"]
    lines = [
        "# Codex Restart Packet",
        "",
        f"Generated: {packet['generated_at']}",
        f"Workspace root: `{packet['workspace_root']}`",
        "",
        "## Portfolio Truth",
        "",
    ]
    if truth.get("available"):
        lines.extend(
            [
                f"- Truth generated: `{truth.get('generated_at', '')}`",
                f"- Schema: `{truth.get('schema_version', '')}`",
                f"- Projects: `{truth.get('project_count', 0)}`",
                f"- Warnings: `{len(truth.get('warnings', []))}`",
            ]
        )
    else:
        lines.append(f"- Missing: `{truth.get('path', '')}`")
    lines.extend(
        [
            "",
            "## Git Attention",
            "",
            f"- Repos scanned: `{git_summary['total']}`",
            f"- Dirty repos: `{git_summary['dirty']}`",
            f"- Non-main or detached: `{git_summary['non_main_or_detached']}`",
            f"- No upstream: `{git_summary['no_upstream']}`",
            f"- Ahead or behind upstream: `{git_summary['ahead_or_behind']}`",
            "",
            "## Active Working Set",
            "",
            "| Repo | Score | Reasons | Branch | Upstream |",
            "|------|-------|---------|--------|----------|",
        ]
    )
    for repo in packet["active_working_set"]:
        reasons = ", ".join(repo["drift_reasons"]) or "clean"
        lines.append(
            f"| `{repo['label']}` | {repo['attention_score']} | {reasons} | "
            f"`{repo['branch']}` | `{repo['upstream'] or 'none'}` |"
        )
    lines.extend(["", "## Archive Exclusions", ""])
    lines.append(
        "Default restart scans exclude generated/archive/dependency surfaces including "
        "`" + "`, `".join(packet["archive_exclusions"]) + "`."
    )
    lines.extend(["", "## Next Commands", ""])
    lines.extend(f"- `{command}`" for command in packet["next_commands"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a compact, archive-aware Codex restart packet from live repo state."
    )
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--truth-path", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument("--output", type=Path, default=None, help="Optional file to write")
    args = parser.parse_args(argv)
    packet = build_restart_packet(workspace_root=args.workspace_root, truth_path=args.truth_path)
    rendered = json.dumps(packet, indent=2, sort_keys=True) + "\n" if args.json else render_markdown(packet)
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
