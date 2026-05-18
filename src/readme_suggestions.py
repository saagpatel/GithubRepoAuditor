"""README improvement suggestions — generates specific actionable fixes per repo."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def _check_readme(repo_path: Path) -> tuple[str, list[str]]:
    """Read README content and generate suggestions."""
    suggestions: list[str] = []
    content = ""

    for name in ("README.md", "README", "README.rst", "readme.md"):
        readme = repo_path / name
        if readme.is_file():
            try:
                content = readme.read_text(errors="replace")
            except OSError:
                pass
            break

    if not content:
        return "", ["Create a README.md with project description, installation, and usage"]

    # Check for images/screenshots
    if "![" not in content or "](" not in content:
        suggestions.append("Add a screenshot or demo GIF to make the project visually appealing")

    # Check for installation instructions
    install_markers = ["## install", "## getting started", "## setup", "## quick start", "```bash", "pip install", "npm install", "cargo install"]
    has_install = any(m in content.lower() for m in install_markers)
    if not has_install:
        suggestions.append("Add installation instructions (## Installation section with commands)")

    # Check for usage examples
    code_block_count = content.count("```")
    if code_block_count < 2:
        suggestions.append("Add usage examples with code blocks showing how to use the project")

    # Check for badges
    if "img.shields.io" not in content and "badge" not in content.lower()[:500]:
        suggestions.append("Add status badges (build, test, coverage) to the top of the README")

    # Check description placement
    lines = content.strip().splitlines()
    if lines and not lines[0].startswith("#"):
        suggestions.append("Start README with a clear heading (# Project Name)")

    # Check for license mention
    if "license" not in content.lower():
        suggestions.append("Mention the license in the README or add a LICENSE file")

    # Check for contributing section
    if "contributing" not in content.lower():
        suggestions.append("Add a Contributing section or link to CONTRIBUTING.md")

    # Check length
    if len(content) < 500:
        suggestions.append("Expand the README — aim for at least 500 characters with clear sections")

    return content, suggestions


def generate_readme_suggestions(
    report_data: dict,
    output_dir: Path,
) -> dict:
    """Generate README suggestions for all audited repos.

    Returns {suggestions_path, total_suggestions, repos_with_suggestions}.
    Note: requires repo_paths to be available (only works during clone phase).
    This function works from audit data only — it analyzes README scores and flags.
    """
    date = report_data.get("generated_at", "")[:10]
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "# README Improvement Suggestions",
        "",
        f"Generated: {date} | {report_data.get('repos_audited', 0)} repos analyzed",
        "",
    ]

    total_suggestions = 0
    repos_with_suggestions = 0

    audits = sorted(
        report_data.get("audits", []),
        key=lambda a: a.get("overall_score", 0),
        reverse=True,
    )

    for audit in audits:
        meta = audit.get("metadata", {})
        name = meta.get("name", "")
        readme_score = 0.0
        readme_findings: list[str] = []

        for r in audit.get("analyzer_results", []):
            if r["dimension"] == "readme":
                readme_score = r["score"]
                readme_findings = r.get("findings", [])
                break

        # Generate suggestions based on score and findings
        suggestions: list[str] = []

        if readme_score == 0.0:
            suggestions.append("Create a README.md with project description, installation, and usage")
        elif readme_score < 0.5:
            if not any("image" in f.lower() or "screenshot" in f.lower() for f in readme_findings):
                suggestions.append("Add a screenshot or demo GIF")
            if not any("badge" in f.lower() for f in readme_findings):
                suggestions.append("Add status badges to the top")
            if readme_score < 0.3:
                suggestions.append("Expand README with installation and usage sections")
        elif readme_score < 0.8:
            suggestions.append("Add usage examples with code blocks")
            if not any("image" in f.lower() for f in readme_findings):
                suggestions.append("Add visual content (screenshots, diagrams, or GIFs)")

        if suggestions:
            repos_with_suggestions += 1
            total_suggestions += len(suggestions)
            grade = audit.get("grade", "F")
            lines.append(f"## {name} (Grade {grade}, README score {readme_score:.2f})")
            lines.append("")
            for s in suggestions:
                lines.append(f"- {s}")
            lines.append("")

    if not total_suggestions:
        lines.append("All READMEs look good! No suggestions at this time.")
        lines.append("")

    output_dir.mkdir(parents=True, exist_ok=True)
    suggestions_path = output_dir / f"readme-suggestions-{date}.md"
    suggestions_path.write_text("\n".join(lines))

    return {
        "suggestions_path": suggestions_path,
        "total_suggestions": total_suggestions,
        "repos_with_suggestions": repos_with_suggestions,
    }
