from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

logger = logging.getLogger(__name__)

README_NAMES = ("README.md", "README", "README.rst", "readme.md", "Readme.md")

# Source-code extensions used for staleness comparison.
_CODE_GLOBS = (
    "*.py",
    "*.ts",
    "*.tsx",
    "*.js",
    "*.jsx",
    "*.swift",
    "*.rs",
    "*.go",
    "*.java",
    "*.kt",
)

SETUP_HEADINGS = re.compile(
    r"^#{1,3}\s.*(install|setup|getting\s+started|usage|quick\s*start)",
    re.IGNORECASE | re.MULTILINE,
)


class ReadmeAnalyzer(BaseAnalyzer):
    name = "readme"
    weight = 0.15

    def cache_inputs_hash(
        self,
        repo_path: Path | None,
        metadata: RepoMetadata,
    ) -> str | None:
        """Hash README bytes + git last-touched timestamps for README and code files.

        The staleness calculation inside analyze() depends on these timestamps, so
        including them in the hash ensures we recompute when the commit history
        changes even if the file bytes did not.
        """
        if repo_path is None:
            return None
        readme_path = None
        for name in README_NAMES:
            candidate = repo_path / name
            if candidate.is_file():
                readme_path = candidate
                break
        if readme_path is None:
            # No README — sentinel so identical "no README" results can be cached.
            h = hashlib.sha256(b"no-readme")
            h.update(b"\x00")
            return h.hexdigest()
        try:
            readme_bytes = readme_path.read_bytes()
        except OSError:
            return None
        readme_ts = _git_last_touched_unix(repo_path, readme_path.name)
        code_ts = _git_last_touched_unix(repo_path, *_CODE_GLOBS)
        h = hashlib.sha256()
        h.update(readme_bytes)
        h.update(b"\x00")
        h.update(str(readme_ts).encode())
        h.update(b"\x00")
        h.update(str(code_ts).encode())
        h.update(b"\x00")
        return h.hexdigest()

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
            return self._result(
                0.0,
                findings,
                {
                    "exists": False,
                    "readme_last_touched_days": None,
                    "code_last_touched_days": None,
                    "readme_staleness_ratio": None,
                    "readme_stale": None,
                },
            )

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

        # Staleness: compare README last-touched vs code last-touched via git log.
        # Only meaningful when repo_path is a git working tree.
        readme_name = readme_path.name
        staleness = _compute_readme_staleness(repo_path, readme_name)
        details.update(staleness)

        return self._result(score, findings, details)


def _git_last_touched_unix(repo_path: Path, *pathspecs: str) -> int | None:
    """Return the Unix commit timestamp of the most recent commit touching *pathspecs*.

    Returns None if git is not available, the path is not a git repo, or no
    matching commits exist.
    """
    cmd = [
        "git",
        "log",
        "-1",
        "--format=%ct",
        "--",
        *pathspecs,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        stdout = result.stdout.strip()
        if stdout:
            return int(stdout)
        return None
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as exc:
        logger.debug("git log failed for %s (%s): %s", repo_path, pathspecs, exc)
        return None


def _compute_readme_staleness(repo_path: Path, readme_name: str) -> dict:
    """Compute README staleness fields relative to code last-touched date.

    Fields returned:
    - ``readme_last_touched_days`` — days since README was last committed (None if unknown)
    - ``code_last_touched_days``   — days since any code file was last committed (None if no code)
    - ``readme_staleness_ratio``   — readme_days / max(code_days, 1); None if either is unknown
    - ``readme_stale``             — True if ratio > 5.0 AND code_last_touched_days < 90
      (README is 5x older than the code AND code is being actively touched)
    """
    now_ts = int(time.time())

    readme_ts = _git_last_touched_unix(repo_path, readme_name)
    code_ts = _git_last_touched_unix(repo_path, *_CODE_GLOBS)

    readme_days: int | None = None
    if readme_ts is not None:
        readme_days = max(0, (now_ts - readme_ts) // 86400)

    code_days: int | None = None
    if code_ts is not None:
        code_days = max(0, (now_ts - code_ts) // 86400)

    staleness_ratio: float | None = None
    stale: bool | None = None

    if readme_days is not None and code_days is not None:
        staleness_ratio = readme_days / max(code_days, 1)
        stale = staleness_ratio > 5.0 and code_days < 90
    elif readme_days is not None and code_days is None:
        # Docs-only repo — skip staleness
        pass

    return {
        "readme_last_touched_days": readme_days,
        "code_last_touched_days": code_days,
        "readme_staleness_ratio": staleness_ratio,
        "readme_stale": stale,
    }


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
