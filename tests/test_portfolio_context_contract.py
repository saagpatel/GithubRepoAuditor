from pathlib import Path

from src.portfolio_context_contract import analyze_project_context

# A generic Codex-OS-style AGENTS.md stub: no Portfolio-Context sections, no run guidance.
_GENERIC_AGENTS = (
    "# codex-os-managed\n\n"
    "## Communication Contract\n\n"
    "Follow the global contract for all changes made in this repository.\n"
)
_RUN_SECTION = "## Usage\n\nRun the dev server with `npm run dev` to start the app.\n"


def _write(dir_path: Path, name: str, text: str) -> None:
    (dir_path / name).write_text(text)


def test_readme_fallback_marks_run_instructions_present(tmp_path):
    # Primary (AGENTS.md) lacks run instructions; README carries them → README fallback.
    _write(tmp_path, "AGENTS.md", _GENERIC_AGENTS)
    _write(tmp_path, "README.md", "# Proj\n\n" + _RUN_SECTION)
    result = analyze_project_context(tmp_path, ["AGENTS.md", "README.md"])
    assert result.run_instructions_present is True


def test_no_fallback_when_neither_documents_it(tmp_path):
    # Neither file documents how to run it → still absent (fallback must not hallucinate).
    _write(tmp_path, "AGENTS.md", _GENERIC_AGENTS)
    _write(tmp_path, "README.md", "# Proj\n\nA short blurb with no run guidance whatsoever.\n")
    result = analyze_project_context(tmp_path, ["AGENTS.md", "README.md"])
    assert result.run_instructions_present is False


def test_primary_still_detected_without_readme(tmp_path):
    # Existing behavior preserved: run instructions in the primary file are still found.
    _write(tmp_path, "AGENTS.md", "# Proj\n\n" + _RUN_SECTION)
    result = analyze_project_context(tmp_path, ["AGENTS.md"])
    assert result.run_instructions_present is True


def test_context_quality_not_none_for_readme_only_repo(tmp_path):
    # No CLAUDE.md/AGENTS.md, but a rich README documents all six sections.
    readme = (
        "# Proj\n\n"
        "## Overview\n\nThis project does a specific useful thing for its users.\n\n"
        "## Status\n\nCurrently in active development with the core features done.\n\n"
        "## Tech Stack\n\nBuilt with Python, FastAPI, and SQLite for storage.\n\n"
        "## Usage\n\nRun it locally with `uvicorn app:main` after installing deps.\n\n"
        "## Known Risks\n\nRate limits and no auth yet are the main known gaps.\n\n"
        "## Next Steps\n\nAdd authentication and ship the first tagged release.\n"
    )
    _write(tmp_path, "README.md", readme)
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.context_quality != "none"  # README content now counts
    assert result.run_instructions_present is True


def test_explicit_readme_text_override_is_honored(tmp_path):
    # The dormant readme_text param now works as an explicit override (no disk read needed).
    _write(tmp_path, "AGENTS.md", _GENERIC_AGENTS)
    result = analyze_project_context(
        tmp_path, ["AGENTS.md"], readme_text="# Proj\n\n" + _RUN_SECTION
    )
    assert result.run_instructions_present is True


# --- Layer-2: lead-paragraph project summaries (no "## Overview" heading) ---


def test_lead_paragraph_counts_as_project_summary(tmp_path):
    # Summary is the tagline under the title, with no Overview-style heading anywhere.
    _write(tmp_path, "AGENTS.md", _GENERIC_AGENTS)
    _write(
        tmp_path,
        "README.md",
        "# Proj\n\nA real-time strategy game where every decision happens at once.\n\n"
        "## Install\n\nRun npm install first to set things up.\n",
    )
    result = analyze_project_context(tmp_path, ["AGENTS.md", "README.md"])
    assert result.project_summary_present is True


def test_badge_only_lead_is_not_a_summary(tmp_path):
    # A wall of badges/links before the first section must NOT count as a summary.
    _write(tmp_path, "AGENTS.md", _GENERIC_AGENTS)
    _write(
        tmp_path,
        "README.md",
        "# Proj\n\n![CI](https://x/ci.svg) ![Coverage](https://x/cov.svg)\n\n"
        "## Install\n\nRun npm install first to set things up.\n",
    )
    result = analyze_project_context(tmp_path, ["AGENTS.md", "README.md"])
    assert result.project_summary_present is False


def test_overview_section_still_wins_without_lead(tmp_path):
    # Existing alias path is unaffected by the lead-paragraph fallback.
    _write(
        tmp_path,
        "README.md",
        "# Proj\n\n## Overview\n\nThis project does a specific, clearly described useful thing.\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.project_summary_present is True


def test_lead_paragraph_in_primary_file_counts(tmp_path):
    # Lead paragraph in the primary file (CLAUDE.md) also counts.
    _write(
        tmp_path,
        "CLAUDE.md",
        "# Proj\n\nA concise description of what this tool is and who it serves.\n\n"
        "## Setup\n\nInstall the dependencies to begin.\n",
    )
    result = analyze_project_context(tmp_path, ["CLAUDE.md"])
    assert result.project_summary_present is True


# --- Layer-3: hierarchy-aware + substring heading matching, relaxed threshold ---


def test_run_instructions_in_subsections_of_quick_start(tmp_path):
    # "## Quick Start" has an empty direct body; the run commands live one level
    # down in "### Installation" — content must roll up to the matched parent.
    _write(
        tmp_path,
        "README.md",
        "# Proj\n\nA tool that does a thing.\n\n"
        "## Quick Start\n\n### Installation\n\n```bash\nuv tool install proj\n```\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.run_instructions_present is True


def test_heading_containing_alias_term_matches(tmp_path):
    # "## Commands By Mode" contains the "commands" alias but is not an exact match.
    _write(
        tmp_path,
        "README.md",
        "# Proj\n\nA tool.\n\n"
        "## Commands By Mode\n\nRun `proj audit` to start the daily flow today.\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.run_instructions_present is True


def test_terse_managed_stack_value_counts(tmp_path):
    # The managed-context block writes a short-but-valid stack ("- Primary stack:
    # Python", 3 words) — the analyzer must not reject its own generated content.
    _write(
        tmp_path,
        "AGENTS.md",
        "# proj\n\n## Portfolio Context\n\n"
        "### What this project is\n\nA small useful local tool for the operator.\n\n"
        "### Stack\n\n- Primary stack: Python\n",
    )
    result = analyze_project_context(tmp_path, ["AGENTS.md"])
    assert result.stack_present is True


def test_badge_only_section_does_not_count(tmp_path):
    # A "## Status" section that is only a CI badge must NOT count as current state
    # (guards the relaxed threshold against badge false positives).
    _write(
        tmp_path,
        "README.md",
        "# Proj\n\nA tool that does a thing for people.\n\n## Status\n\n![CI](https://x/ci.svg)\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.current_state_present is False


# --- Guard against over-matching: a single-word alias as a non-leading word in
# an unrelated heading must NOT satisfy the section (prefix-anchored matching). ---


def test_single_word_alias_does_not_overmatch_unrelated_heading(tmp_path):
    # "## Memory Usage Statistics" contains "usage" but is not run guidance.
    _write(
        tmp_path,
        "README.md",
        "# P\n\nA tool that does a clear thing for people.\n\n"
        "## Memory Usage Statistics\n\nWe used 4GB of RAM during the load test run.\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.run_instructions_present is False


def test_status_codes_heading_is_not_current_state(tmp_path):
    # "## HTTP Status Codes" contains "status" but is not project state.
    _write(
        tmp_path,
        "README.md",
        "# P\n\nA tool that does a clear thing for people.\n\n"
        "## HTTP Status Codes\n\nThe API returns 200, 404, and 500 in these cases.\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.current_state_present is False


def test_h1_title_alias_does_not_eat_whole_document(tmp_path):
    # The H1 title is not a content section: an alias word in the title must not
    # roll up the entire document as that section's content.
    _write(
        tmp_path,
        "README.md",
        "# Technology Stack\n\nThis project is a thing for users.\n\n"
        "## Overview\n\nIt does stuff for people who need it done.\n",
    )
    result = analyze_project_context(tmp_path, ["README.md"])
    assert result.stack_present is False
