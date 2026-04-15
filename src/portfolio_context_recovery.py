from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.portfolio_context_contract import (
    MANAGED_CONTEXT_END,
    MANAGED_CONTEXT_START,
    friendly_missing_fields,
    render_managed_context_block,
    temporary_project_reason,
    upsert_managed_context_block,
)
from src.portfolio_truth_types import PortfolioTruthProject, PortfolioTruthSnapshot

try:
    import yaml
except ImportError:  # pragma: no cover - repo already depends on PyYAML for catalog tests
    yaml = None


@dataclass(frozen=True)
class ContextRecoveryTarget:
    priority_rank: int
    project_key: str
    display_name: str
    relative_path: str
    registry_status: str
    context_quality: str
    primary_context_file: str
    target_path: str
    status: str
    missing_fields: list[str] = field(default_factory=list)
    reason: str = ""
    suggested_catalog_seed: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextRecoveryPlan:
    generated_at: datetime
    workspace_root: str
    target_project_count: int
    projects: list[ContextRecoveryTarget]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "workspace_root": self.workspace_root,
            "target_project_count": self.target_project_count,
            "projects": [asdict(project) for project in self.projects],
        }


@dataclass(frozen=True)
class ContextRecoveryApplyResult:
    updated_projects: list[str]
    skipped_projects: list[str]
    failed_projects: list[str]
    catalog_updated: bool


def build_context_recovery_plan(
    snapshot: PortfolioTruthSnapshot,
    *,
    workspace_root: Path,
) -> ContextRecoveryPlan:
    targets: list[ContextRecoveryTarget] = []
    target_projects = [
        project
        for project in snapshot.projects
        if project.derived.activity_status in {"active", "recent"}
        and project.derived.context_quality in {"boilerplate", "none"}
    ]
    target_projects.sort(key=_recovery_priority)

    for index, project in enumerate(target_projects, start=1):
        project_path = workspace_root / project.identity.path
        reason = temporary_project_reason(
            project.identity.project_key, project.identity.display_name
        )
        status = "eligible"
        if reason:
            status = "excluded"
        else:
            dirty_reason = _dirty_worktree_reason(project_path, project.identity.has_git)
            if dirty_reason:
                status = "skipped"
                reason = dirty_reason
            else:
                ambiguous_reason = _ambiguous_primary_context_reason(project_path)
                if ambiguous_reason:
                    status = "skipped"
                    reason = ambiguous_reason

        targets.append(
            ContextRecoveryTarget(
                priority_rank=index,
                project_key=project.identity.project_key,
                display_name=project.identity.display_name,
                relative_path=project.identity.path,
                registry_status=project.derived.registry_status,
                context_quality=project.derived.context_quality,
                primary_context_file=project.derived.primary_context_file,
                target_path=(project_path / project.derived.primary_context_file).as_posix(),
                status=status,
                missing_fields=_missing_fields_for_project(project),
                reason=reason,
                suggested_catalog_seed=_suggested_catalog_seed(project),
            )
        )

    return ContextRecoveryPlan(
        generated_at=datetime.now(timezone.utc),
        workspace_root=workspace_root.as_posix(),
        target_project_count=len(target_projects),
        projects=targets,
    )


def write_context_recovery_plan_artifacts(
    plan: ContextRecoveryPlan,
    *,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = plan.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    json_path = output_dir / f"context-recovery-plan-{stamp}.json"
    markdown_path = output_dir / f"context-recovery-plan-{stamp}.md"
    json_path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n")
    markdown_path.write_text(render_context_recovery_plan_markdown(plan))
    return json_path, markdown_path


def apply_context_recovery_plan(
    snapshot: PortfolioTruthSnapshot,
    plan: ContextRecoveryPlan,
    *,
    workspace_root: Path,
    catalog_path: Path | None = None,
    limit: int | None = None,
) -> ContextRecoveryApplyResult:
    project_index = {project.identity.project_key: project for project in snapshot.projects}
    eligible_targets = [target for target in plan.projects if target.status == "eligible"]
    if limit is not None:
        eligible_targets = eligible_targets[:limit]

    updated: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    catalog_seeds: dict[str, dict[str, str]] = {}

    for target in eligible_targets:
        project = project_index[target.project_key]
        project_path = workspace_root / project.identity.path
        target_file = project_path / target.primary_context_file
        try:
            existing_text = target_file.read_text(errors="replace") if target_file.exists() else ""
            managed_block = render_managed_context_block(
                _build_context_sections(project, project_path)
            )
            target_file.write_text(upsert_managed_context_block(existing_text, managed_block))
            updated.append(target.project_key)
            if target.suggested_catalog_seed:
                catalog_seeds[_catalog_repo_key(project)] = target.suggested_catalog_seed
        except Exception:
            failed.append(target.project_key)

    if catalog_path and catalog_seeds:
        _merge_catalog_seeds(catalog_path, catalog_seeds)

    for target in plan.projects:
        if target.status in {"skipped", "excluded"}:
            skipped.append(target.project_key)

    return ContextRecoveryApplyResult(
        updated_projects=updated,
        skipped_projects=skipped,
        failed_projects=failed,
        catalog_updated=bool(catalog_path and catalog_seeds),
    )


# Utility: renders ContextRecoveryPlan as human-readable Markdown.
# Called by write_context_recovery_plan_artifacts() which is wired to CLI.
def render_context_recovery_plan_markdown(plan: ContextRecoveryPlan) -> str:
    eligible = [project for project in plan.projects if project.status == "eligible"]
    skipped = [project for project in plan.projects if project.status == "skipped"]
    excluded = [project for project in plan.projects if project.status == "excluded"]
    lines = [
        "# Context Recovery Plan",
        "",
        f"> Generated: {plan.generated_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"> Target cohort size: {plan.target_project_count}",
        "",
        "## Summary",
        "",
        f"- Eligible for automated recovery now: `{len(eligible)}`",
        f"- Skipped because of local safety rules: `{len(skipped)}`",
        f"- Excluded as temporary/generated: `{len(excluded)}`",
        "",
        "## Frozen Target Cohort",
        "",
        "| Rank | Project | Status | Current Context | Action | Missing Fields |",
        "|------|---------|--------|-----------------|--------|----------------|",
    ]
    for target in plan.projects:
        action = target.status
        if target.reason:
            action = f"{target.status} ({target.reason})"
        lines.append(
            f"| {target.priority_rank} | {target.display_name} | {target.registry_status} | {target.context_quality} | "
            f"{action} | {', '.join(target.missing_fields) or '—'} |"
        )
    return "\n".join(lines) + "\n"


def _recovery_priority(project: PortfolioTruthProject) -> tuple[int, int, str]:
    activity_rank = 0 if project.derived.activity_status == "active" else 1
    section_rank = 0 if project.identity.section_marker == "Standalone Projects" else 1
    return (activity_rank, section_rank, project.identity.display_name.lower())


def _dirty_worktree_reason(project_path: Path, has_git: bool) -> str:
    if not has_git:
        return ""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "git-status-unavailable"
    if result.returncode != 0:
        return "git-status-unavailable"
    return "dirty-worktree" if result.stdout.strip() else ""


def _ambiguous_primary_context_reason(project_path: Path) -> str:
    claude_path = project_path / "CLAUDE.md"
    agents_path = project_path / "AGENTS.md"
    if not claude_path.exists() or not agents_path.exists():
        return ""
    claude_text = claude_path.read_text(errors="replace").strip()
    if claude_text in {"", "@AGENTS.md"}:
        return ""
    if MANAGED_CONTEXT_START in claude_text:
        return ""
    agents_text = agents_path.read_text(errors="replace").strip()
    if not agents_text or MANAGED_CONTEXT_START in agents_text:
        return ""
    return "ambiguous-primary-context"


def _missing_fields_for_project(project: PortfolioTruthProject) -> list[str]:
    return friendly_missing_fields(
        type(
            "InlineAnalysis",
            (),
            {
                "missing_fields": [
                    label
                    for present, label in (
                        (project.derived.project_summary_present, "what the project is"),
                        (project.derived.current_state_present, "current state"),
                        (project.derived.stack_present, "stack"),
                        (project.derived.run_instructions_present, "how to run"),
                        (project.derived.known_risks_present, "known risks"),
                        (project.derived.next_recommended_move_present, "next recommended move"),
                    )
                    if not present
                ]
            },
        )()
    )


def _suggested_catalog_seed(project: PortfolioTruthProject) -> dict[str, str]:
    seed = {
        "owner": project.declared.owner or "d",
        "lifecycle_state": project.declared.lifecycle_state or "active",
        "review_cadence": project.declared.review_cadence
        or ("weekly" if project.derived.activity_status == "active" else "monthly"),
        "intended_disposition": project.declared.intended_disposition
        or _infer_disposition(project),
    }
    category = project.declared.category or ""
    tool_provenance = project.declared.tool_provenance or ""
    if category and category != "unknown":
        seed["category"] = category
    if tool_provenance and tool_provenance != "unknown":
        seed["tool_provenance"] = tool_provenance
    return {key: value for key, value in seed.items() if value}


def _infer_disposition(project: PortfolioTruthProject) -> str:
    lower_name = project.identity.display_name.lower()
    if any(token in lower_name for token in ("sandbox", "eval", "stress", "terrarium")):
        return "experiment"
    return "maintain"


def _catalog_repo_key(project: PortfolioTruthProject) -> str:
    return project.identity.display_name


def _merge_catalog_seeds(catalog_path: Path, seeds: dict[str, dict[str, str]]) -> None:
    if yaml is None:
        return
    data = yaml.safe_load(catalog_path.read_text()) if catalog_path.is_file() else {}
    if not isinstance(data, dict):
        data = {}
    repos = data.setdefault("repos", {})
    if not isinstance(repos, dict):
        repos = {}
        data["repos"] = repos
    for repo_key, seed in seeds.items():
        existing = repos.get(repo_key)
        if not isinstance(existing, dict):
            existing = {}
        for field_name, value in seed.items():
            if value and not existing.get(field_name):
                existing[field_name] = value
        repos[repo_key] = existing
    catalog_path.write_text(yaml.safe_dump(data, sort_keys=False))


def _build_context_sections(project: PortfolioTruthProject, project_path: Path) -> dict[str, str]:
    primary_sections = _read_markdown_sections(project_path / project.derived.primary_context_file)
    readme_sections = _read_markdown_sections(project_path / "README.md")
    summary = _first_nonempty(
        primary_sections.get("what this project is"),
        primary_sections.get("project summary"),
        primary_sections.get("overview"),
        primary_sections.get("purpose"),
        primary_sections.get("__preamble__"),
        readme_sections.get("project summary"),
        readme_sections.get("overview"),
        readme_sections.get("product goal"),
        readme_sections.get("__preamble__"),
        project.declared.purpose,
        f"{project.identity.display_name} is an active local project in the /Users/d/Projects portfolio.",
    )
    current_state = _first_nonempty(
        primary_sections.get("current state"),
        primary_sections.get("status"),
        primary_sections.get("current phase"),
        readme_sections.get("current state"),
        readme_sections.get("status"),
        readme_sections.get("current phase"),
        (
            f"Portfolio truth currently marks this project as `{project.derived.activity_status}` with "
            f"`{project.derived.context_quality}` context. Phase 104 recovered minimum-viable context so future "
            f"sessions can resume without rediscovery."
        ),
    )
    stack = _first_nonempty(
        primary_sections.get("stack"),
        primary_sections.get("tech stack"),
        readme_sections.get("stack"),
        readme_sections.get("tech stack"),
        _stack_fallback(project, project_path),
    )
    run_instructions = _first_nonempty(
        primary_sections.get("how to run"),
        primary_sections.get("quick start"),
        primary_sections.get("build run"),
        primary_sections.get("local setup"),
        primary_sections.get("local development"),
        primary_sections.get("commands"),
        primary_sections.get("usage"),
        primary_sections.get("development conventions"),
        readme_sections.get("how to run"),
        readme_sections.get("quick start"),
        readme_sections.get("local setup"),
        readme_sections.get("local development"),
        readme_sections.get("commands"),
        readme_sections.get("runner commands"),
        readme_sections.get("usage"),
        _run_fallback(project_path),
    )
    known_risks = _first_nonempty(
        primary_sections.get("known risks"),
        primary_sections.get("known issues"),
        primary_sections.get("intentional limits"),
        primary_sections.get("do not"),
        readme_sections.get("known risks"),
        readme_sections.get("intentional limits"),
        readme_sections.get("known issues"),
        _risk_fallback(project, project_path),
    )
    next_move = _first_nonempty(
        primary_sections.get("next recommended move"),
        primary_sections.get("next step"),
        primary_sections.get("next steps"),
        readme_sections.get("next recommended move"),
        readme_sections.get("next step"),
        readme_sections.get("next steps"),
        (
            "Use this context plus the README and supporting docs to resume the next active task, then promote the "
            "repo beyond minimum-viable by capturing a dedicated handoff, roadmap, or discovery artifact."
        ),
    )
    return {
        "project_summary": summary.strip(),
        "current_state": current_state.strip(),
        "stack": stack.strip(),
        "run_instructions": run_instructions.strip(),
        "known_risks": known_risks.strip(),
        "next_recommended_move": next_move.strip(),
    }


def _read_markdown_sections(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = _strip_managed_context_block(path.read_text(errors="replace"))
    return _split_markdown_sections(text)


def _split_markdown_sections(text: str) -> dict[str, str]:
    import re

    sections: dict[str, list[str]] = {"__preamble__": []}
    current = "__preamble__"
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            current = _normalize_heading(match.group(1))
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def _normalize_heading(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _stack_fallback(project: PortfolioTruthProject, project_path: Path) -> str:
    lines = []
    if project.derived.stack:
        lines.append(f"- Primary stack: {', '.join(project.derived.stack)}")
    package_json = project_path / "package.json"
    if package_json.is_file():
        lines.append("- JavaScript package manager: npm-compatible workflow")
    if (project_path / "Cargo.toml").is_file():
        lines.append("- Rust workspace contract is defined in `Cargo.toml`.")
    if (project_path / "runner.py").is_file():
        lines.append("- The repo includes a Python runner for task execution.")
    return (
        "\n".join(lines)
        or "- Stack still needs a deeper explicit handoff beyond this minimum context."
    )


def _run_fallback(project_path: Path) -> str:
    if (project_path / "package.json").is_file():
        return "- Install dependencies with `npm install`.\n- Start local development with `npm run dev`.\n- Review the repo README for any required verification commands before shipping."
    if (project_path / "Cargo.toml").is_file():
        return "- Use `cargo run` for the normal local app loop.\n- Run the repo verification commands from the README before calling the build healthy."
    if (project_path / "runner.py").is_file():
        return "- Use `python3 runner.py` for the main local entrypoint.\n- Review the README command examples before recording or comparing runs."
    return "- Review the README and top-level scripts before the next session; this repo does not yet expose one canonical run command inside the new context block."


def _risk_fallback(project: PortfolioTruthProject, project_path: Path) -> str:
    lines = [
        "- This repo only has minimum-viable recovery context today; deeper handoff details may still live in the README and supporting docs."
    ]
    if not project.identity.has_git:
        lines.append(
            "- This project is not tracked as a local git repository, so change detection and dirty-worktree safety checks are weaker."
        )
    if project_path.name != project_path.name.strip():
        lines.append(
            "- The on-disk folder name still carries whitespace drift that can make scripted paths easier to misread."
        )
    return "\n".join(lines)


def _first_nonempty(*values: str) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def _strip_managed_context_block(text: str) -> str:
    start = text.find(MANAGED_CONTEXT_START)
    end = text.find(MANAGED_CONTEXT_END)
    if start == -1 or end == -1 or end <= start:
        return text
    end += len(MANAGED_CONTEXT_END)
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    pieces = [piece for piece in (before, after) if piece]
    return "\n\n".join(pieces)
