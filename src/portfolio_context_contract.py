from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PRIMARY_CONTEXT_CANDIDATES = ("CLAUDE.md", "AGENTS.md")
SUPPORTING_CONTEXT_FILES = frozenset({
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
MANAGED_CONTEXT_START = "<!-- portfolio-context:start -->"
MANAGED_CONTEXT_END = "<!-- portfolio-context:end -->"
TEMPORARY_PROJECT_PATTERNS = (
    re.compile(r"(^|[-_])scaffold($|[-_])", re.IGNORECASE),
    re.compile(r"-tmp-\d+$", re.IGNORECASE),
)
CONTEXT_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "project_summary": (
        "what this project is",
        "project summary",
        "overview",
        "purpose",
        "product goal",
        "what it is",
    ),
    "current_state": (
        "current state",
        "status",
        "current phase",
        "current focus",
        "where things stand",
    ),
    "stack": (
        "stack",
        "tech stack",
        "technology",
        "technical stack",
    ),
    "run_instructions": (
        "how to run",
        "local setup",
        "local development",
        "commands",
        "run instructions",
        "development commands",
        "quick start",
        "build run",
        "getting started",
        "usage",
    ),
    "known_risks": (
        "known risks",
        "risks",
        "known issues",
        "intentional limits",
        "constraints",
    ),
    "next_recommended_move": (
        "next recommended move",
        "next step",
        "next steps",
        "next move",
        "recommended next step",
    ),
}

REQUIRED_FIELD_TO_DERIVED_KEY = {
    "project_summary": "project_summary_present",
    "current_state": "current_state_present",
    "stack": "stack_present",
    "run_instructions": "run_instructions_present",
    "known_risks": "known_risks_present",
    "next_recommended_move": "next_recommended_move_present",
}
DERIVED_KEY_TO_LABEL = {
    "project_summary_present": "what the project is",
    "current_state_present": "current state",
    "stack_present": "stack",
    "run_instructions_present": "how to run",
    "known_risks_present": "known risks",
    "next_recommended_move_present": "next recommended move",
}
STANDARD_SIGNAL_FILES = frozenset({
    "IMPLEMENTATION-ROADMAP.md",
    "RESUMPTION-PROMPT.md",
    "HANDOFF.md",
    "STATUS.md",
    "PROJECT.md",
    "PLAN.md",
})
FULL_SIGNAL_FILES = frozenset({
    "DISCOVERY-SUMMARY.md",
    "IMPLEMENTATION-ROADMAP.md",
    "RESUMPTION-PROMPT.md",
    "HANDOFF.md",
})


@dataclass(frozen=True)
class ContextAnalysis:
    context_quality: str
    primary_context_file: str
    project_summary_present: bool
    current_state_present: bool
    stack_present: bool
    run_instructions_present: bool
    known_risks_present: bool
    next_recommended_move_present: bool
    missing_fields: list[str]
    supporting_context_files: list[str]


def choose_primary_context_file(context_files: list[str]) -> str:
    normalized = {Path(item).name for item in context_files}
    if "CLAUDE.md" in normalized:
        return "CLAUDE.md"
    return "AGENTS.md"


def analyze_project_context(project_path: Path, context_files: list[str], *, readme_text: str = "") -> ContextAnalysis:
    primary_context_file = choose_primary_context_file(context_files)
    context_file_names = {Path(item).name for item in context_files}
    primary_exists = primary_context_file in context_file_names
    primary_text = ""
    if primary_exists:
        primary_text = _read_small_text(project_path / primary_context_file)

    sections = _split_markdown_sections(primary_text)
    section_presence = {
        field: _section_has_meaningful_content(sections, aliases)
        for field, aliases in CONTEXT_SECTION_ALIASES.items()
    }
    missing_fields = [
        DERIVED_KEY_TO_LABEL[REQUIRED_FIELD_TO_DERIVED_KEY[field]]
        for field, present in section_presence.items()
        if not present
    ]
    supporting_context_files = sorted(
        item
        for item in context_files
        if Path(item).name in SUPPORTING_CONTEXT_FILES and Path(item).name != primary_context_file
    )

    if not primary_exists:
        context_quality = "none"
    elif missing_fields:
        context_quality = "boilerplate"
    else:
        support_names = {Path(item).name for item in supporting_context_files}
        if len(support_names) >= 2 and (support_names & FULL_SIGNAL_FILES):
            context_quality = "full"
        elif support_names & STANDARD_SIGNAL_FILES:
            context_quality = "standard"
        else:
            context_quality = "minimum-viable"

    return ContextAnalysis(
        context_quality=context_quality,
        primary_context_file=primary_context_file,
        project_summary_present=section_presence["project_summary"],
        current_state_present=section_presence["current_state"],
        stack_present=section_presence["stack"],
        run_instructions_present=section_presence["run_instructions"],
        known_risks_present=section_presence["known_risks"],
        next_recommended_move_present=section_presence["next_recommended_move"],
        missing_fields=missing_fields,
        supporting_context_files=supporting_context_files,
    )


def upsert_managed_context_block(existing_text: str, managed_block: str) -> str:
    start_marker = MANAGED_CONTEXT_START
    end_marker = MANAGED_CONTEXT_END
    start = existing_text.find(start_marker)
    end = existing_text.find(end_marker)
    if start != -1 and end != -1 and end > start:
        end += len(end_marker)
        before = existing_text[:start].rstrip()
        after = existing_text[end:].lstrip()
        pieces = [piece for piece in (before, managed_block.strip(), after) if piece]
        return "\n\n".join(pieces).rstrip() + "\n"

    base = existing_text.rstrip()
    if not base:
        return managed_block.strip() + "\n"
    return f"{base}\n\n{managed_block.strip()}\n"


def render_managed_context_block(sections: dict[str, str]) -> str:
    ordered = [
        ("What This Project Is", sections["project_summary"]),
        ("Current State", sections["current_state"]),
        ("Stack", sections["stack"]),
        ("How To Run", sections["run_instructions"]),
        ("Known Risks", sections["known_risks"]),
        ("Next Recommended Move", sections["next_recommended_move"]),
    ]
    lines = [MANAGED_CONTEXT_START, "# Portfolio Context"]
    for heading, body in ordered:
        lines.extend(["", f"## {heading}", "", body.strip()])
    lines.extend(["", MANAGED_CONTEXT_END])
    return "\n".join(lines).strip() + "\n"


def temporary_project_reason(project_key: str, display_name: str) -> str:
    haystacks = (project_key, display_name)
    for value in haystacks:
        for pattern in TEMPORARY_PROJECT_PATTERNS:
            if pattern.search(value):
                return "temporary-or-generated"
    return ""


def friendly_missing_fields(analysis: ContextAnalysis) -> list[str]:
    return list(analysis.missing_fields)


def _read_small_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(errors="replace")


def _split_markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "__preamble__"
    sections[current] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            current = _normalize_heading(match.group(1))
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def _normalize_heading(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return normalized


def _section_has_meaningful_content(sections: dict[str, str], aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        content = sections.get(_normalize_heading(alias), "")
        if _is_nontrivial_text(content):
            return True
    return False


def _is_nontrivial_text(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+./:_-]*", compact)
    return len(words) >= 4 and len(compact) >= 24
