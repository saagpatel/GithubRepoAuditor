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
