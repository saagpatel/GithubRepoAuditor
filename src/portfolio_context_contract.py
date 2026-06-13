from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PRIMARY_CONTEXT_CANDIDATES = ("CLAUDE.md", "AGENTS.md")
SUPPORTING_CONTEXT_FILES = frozenset(
    {
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
        "quickstart",
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
STANDARD_SIGNAL_FILES = frozenset(
    {
        "IMPLEMENTATION-ROADMAP.md",
        "RESUMPTION-PROMPT.md",
        "HANDOFF.md",
        "STATUS.md",
        "PROJECT.md",
        "PLAN.md",
    }
)
FULL_SIGNAL_FILES = frozenset(
    {
        "DISCOVERY-SUMMARY.md",
        "IMPLEMENTATION-ROADMAP.md",
        "RESUMPTION-PROMPT.md",
        "HANDOFF.md",
    }
)


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


# Utility: prefers CLAUDE.md over AGENTS.md when both present.
# Called internally by analyze_project_context() in this module.
def choose_primary_context_file(context_files: list[str]) -> str:
    normalized = {Path(item).name for item in context_files}
    if "CLAUDE.md" in normalized:
        return "CLAUDE.md"
    return "AGENTS.md"


def analyze_project_context(
    project_path: Path, context_files: list[str], *, readme_text: str = ""
) -> ContextAnalysis:
    primary_context_file = choose_primary_context_file(context_files)
    context_file_names = {Path(item).name for item in context_files}
    primary_exists = primary_context_file in context_file_names
    primary_text = ""
    if primary_exists:
        primary_text = _read_small_text(project_path / primary_context_file)

    # README fallback: a project's real docs often live in README.md, which is never chosen
    # as the primary context file. When the primary file lacks a required section, also look
    # in the top-level README so well-documented repos are not scored blind. An explicit
    # readme_text argument overrides the on-disk read (used in tests).
    if not readme_text:
        readme_path = project_path / "README.md"
        if readme_path.is_file():
            readme_text = _read_small_text(readme_path)
    has_readme = bool(readme_text.strip())

    primary_blocks = _section_blocks(primary_text)
    readme_blocks = _section_blocks(readme_text) if has_readme else []
    section_presence = {
        field: (
            _section_has_meaningful_content(primary_blocks, aliases)
            or _section_has_meaningful_content(readme_blocks, aliases)
        )
        for field, aliases in CONTEXT_SECTION_ALIASES.items()
    }
    # Lead-paragraph fallback: a project summary conventionally lives as the prose under the
    # title, not under an "## Overview" heading. If no summary heading matched, accept a
    # non-trivial lead paragraph from the primary file or the README.
    if not section_presence["project_summary"]:
        section_presence["project_summary"] = _has_lead_summary(primary_text) or _has_lead_summary(
            readme_text
        )
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

    if not primary_exists and not has_readme:
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


def _section_blocks(text: str) -> list[tuple[int, str, str]]:
    """Ordered (level, normalized_heading, direct_body) for each markdown heading.

    direct_body is the text under a heading up to the *next heading of any level*,
    so a parent's subsections are separate, deeper-level blocks. Callers roll
    descendant content up via the level (see _aggregated_block_text) — this keeps
    a parent like "## Quick Start" whose content lives entirely under
    "### Installation" from reading as empty.
    """
    blocks: list[tuple[int, str, list[str]]] = []
    in_fenced_code = False
    for line in text.splitlines():
        if re.match(r"^\s{0,3}```", line):
            in_fenced_code = not in_fenced_code
            if blocks:
                blocks[-1][2].append(line)
            continue
        match = None if in_fenced_code else re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if match:
            blocks.append((len(match.group(1)), _normalize_heading(match.group(2)), []))
            continue
        if blocks:
            blocks[-1][2].append(line)
    return [(level, heading, "\n".join(lines).strip()) for level, heading, lines in blocks]


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _heading_starts_with_alias(heading_words: list[str], alias_words: list[str]) -> bool:
    """True if the heading begins with the alias phrase (prefix-anchored match).

    Anchoring at the start keeps decorative trailing words ("Commands By Mode" ->
    "commands") while rejecting an alias buried mid-heading ("Memory Usage
    Statistics" must not match "usage").
    """
    return bool(alias_words) and heading_words[: len(alias_words)] == alias_words


def _aggregated_block_text(blocks: list[tuple[int, str, str]], index: int) -> str:
    """Body of blocks[index] plus all its descendant subsections (deeper level)."""
    level = blocks[index][0]
    parts = [blocks[index][2]]
    for sub_level, _heading, body in blocks[index + 1 :]:
        if sub_level <= level:
            break
        if body:
            parts.append(body)
    return _strip_badges_and_links("\n".join(part for part in parts if part)).strip()


def _section_has_meaningful_content(
    blocks: list[tuple[int, str, str]], aliases: tuple[str, ...]
) -> bool:
    """True if a content heading (level >= 2) starting with an alias phrase has
    non-trivial rolled-up content.

    Matching is prefix-anchored (see _heading_starts_with_alias), so "commands"
    matches "Commands By Mode" but not "Memory Usage Statistics". The H1 title
    (level 1) is skipped — it is the document title, not a content section, and
    matching it would roll the entire file up as that section's body.
    """
    alias_word_lists = [_normalize_heading(alias).split() for alias in aliases]
    for index, (level, heading, _body) in enumerate(blocks):
        if level < 2:
            continue
        heading_words = heading.split()
        matched = any(
            _heading_starts_with_alias(heading_words, words) for words in alias_word_lists
        )
        if matched and _is_nontrivial_text(_aggregated_block_text(blocks, index)):
            return True
    return False


def _is_nontrivial_text(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+./:_-]*", compact)
    return len(words) >= 2 and len(compact) >= 12


def _strip_badges_and_links(text: str) -> str:
    """Drop image/badge markdown and keep link text (dropping URLs)."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images/badges
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # keep link text, drop URLs


def _lead_paragraph_text(text: str) -> str:
    """Prose between the H1 title and the first level-2+ heading — a doc's lead/intro.

    Strips the title line and badge/image/link markdown so a wall of badges does not read as a
    summary. Project summaries conventionally live here rather than under an "## Overview".
    """
    lead_lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{2,}\s", line):  # first '## ...' (or deeper) heading ends the lead
            break
        if re.match(r"^#\s", line):  # the H1 title line itself
            continue
        lead_lines.append(line)
    return _strip_badges_and_links("\n".join(lead_lines))


def _has_lead_summary(text: str) -> bool:
    return _is_nontrivial_text(_lead_paragraph_text(text))
