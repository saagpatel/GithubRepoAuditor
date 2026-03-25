from __future__ import annotations

import re
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

README_NAMES = ("README.md", "README", "README.rst", "readme.md", "Readme.md")

SETUP_HEADINGS = re.compile(
    r"^#{1,3}\s.*(install|setup|getting\s+started|usage|quick\s*start)",
    re.IGNORECASE | re.MULTILINE,
)


class ReadmeAnalyzer(BaseAnalyzer):
    name = "readme"
    weight = 0.15

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # Find README
        readme_path = None
        for name in README_NAMES:
            candidate = repo_path / name
            if candidate.is_file():
                readme_path = candidate
                break

        if not readme_path:
            findings.append("No README found")
            return self._result(0.0, findings, {"exists": False})

        score += 0.2
        findings.append(f"README found: {readme_path.name}")
        details["exists"] = True

        try:
            content = readme_path.read_text(errors="replace")
        except OSError:
            findings.append("Could not read README")
            return self._result(score, findings, details)

        details["length"] = len(content)
        lines = content.splitlines()

        # Description >50 chars in first section
        first_paragraph = _extract_first_paragraph(content)
        if len(first_paragraph) > 50:
            score += 0.2
            findings.append("Has project description (>50 chars)")
        else:
            findings.append("Missing or short project description")

        # Install/setup headings
        if SETUP_HEADINGS.search(content):
            score += 0.2
            findings.append("Has installation/setup instructions")
        else:
            findings.append("No installation/setup section found")

        # Code blocks or images
        has_code_blocks = "```" in content
        has_images = "![" in content and "](" in content
        if has_code_blocks or has_images:
            score += 0.2
            if has_code_blocks:
                findings.append("Has code examples")
            if has_images:
                findings.append("Has images/screenshots")
        else:
            findings.append("No code examples or images")

        # Length >500 chars
        if len(content) > 500:
            score += 0.1
        else:
            findings.append("README is short (<500 chars)")

        # Badges in first 10 lines
        first_lines = "\n".join(lines[:10])
        badge_count = first_lines.count("![")
        if badge_count > 0:
            score += 0.1
            details["badge_count"] = badge_count
        else:
            findings.append("No badges")

        return self._result(score, findings, details)


def _extract_first_paragraph(content: str) -> str:
    """Get text from the first non-heading, non-empty paragraph."""
    lines = content.splitlines()
    paragraph_lines: list[str] = []
    past_first_heading = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if past_first_heading and paragraph_lines:
                break
            past_first_heading = True
            continue
        if not stripped:
            if paragraph_lines:
                break
            continue
        # Skip badge lines
        if stripped.startswith("[![") or stripped.startswith("!["):
            continue
        paragraph_lines.append(stripped)

    return " ".join(paragraph_lines)
