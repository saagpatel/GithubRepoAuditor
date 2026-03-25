from __future__ import annotations

import statistics
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

# Languages considered "novel" for a personal portfolio — uncommon enough to signal curiosity
NOVEL_LANGUAGES = frozenset({
    "Rust", "Swift", "GDScript", "Elixir", "Zig", "Haskell", "OCaml",
    "Nim", "Crystal", "Gleam", "Odin", "V", "Julia", "Lua",
})

# Asset file extensions that signal creative/ambitious projects
ASSET_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp",
    ".mp3", ".wav", ".ogg", ".mp4",
    ".glb", ".gltf", ".obj", ".fbx",
    ".ttf", ".woff", ".woff2",
    ".shader", ".gdshader", ".metal",
})


class InterestAnalyzer(BaseAnalyzer):
    """Scores how interesting, ambitious, or noteworthy a project is.

    This is orthogonal to completeness — a skeleton can be fascinating,
    a shipped project can be mundane.
    """

    name = "interest"
    weight = 0.0  # Not part of completeness score — separate axis

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # 1. Description quality (0–0.15)
        desc_score = _score_description(metadata)
        score += desc_score
        details["description_score"] = desc_score
        if desc_score >= 0.10:
            findings.append("Rich project description")
        elif desc_score > 0:
            findings.append("Basic description")
        else:
            findings.append("No description")

        # 2. Topic tags (0–0.10)
        topic_score = 0.0
        if metadata.topics:
            topic_score += 0.05
            if len(metadata.topics) >= 3:
                topic_score += 0.05
            findings.append(f"Topics: {', '.join(metadata.topics[:5])}")
        else:
            findings.append("No topic tags")
        score += topic_score
        details["topic_count"] = len(metadata.topics)

        # 3. Tech novelty (0–0.20)
        novelty_score = 0.0
        if metadata.language in NOVEL_LANGUAGES:
            novelty_score += 0.10
            findings.append(f"Novel language: {metadata.language}")
        lang_count = len(metadata.languages)
        if lang_count >= 3:
            novelty_score += 0.10
            findings.append(f"Multi-language: {lang_count} languages")
        score += novelty_score
        details["tech_novelty"] = novelty_score

        # 4. Commit burst patterns (0–0.15)
        burst_score = 0.0
        if github_client:
            owner = metadata.full_name.split("/")[0]
            participation = github_client.get_participation_stats(owner, metadata.name)
            if isinstance(participation, dict):
                owner_weeks = participation.get("owner", [])
                burst_score = _score_commit_bursts(owner_weeks)
                details["burst_coefficient"] = _burst_coefficient(owner_weeks)
        score += burst_score
        if burst_score > 0.10:
            findings.append("Passionate burst development pattern")
        elif burst_score > 0:
            findings.append("Some development bursts")

        # 5. Project ambition (0–0.20)
        ambition_score, ambition_details = _score_ambition(repo_path, metadata)
        score += ambition_score
        details["ambition"] = ambition_details
        if ambition_score >= 0.15:
            findings.append("Ambitious project scope")
        elif ambition_score >= 0.05:
            findings.append("Moderate scope")

        # 6. External validation (0–0.10)
        validation_score = 0.0
        if metadata.stars > 0:
            validation_score += 0.05
            findings.append(f"Stars: {metadata.stars}")
        if metadata.forks > 0:
            validation_score += 0.05
            findings.append(f"Forks: {metadata.forks}")
        score += validation_score

        # 7. README storytelling (0–0.10)
        storytelling = _score_readme_storytelling(repo_path)
        score += storytelling
        details["readme_storytelling"] = storytelling
        if storytelling > 0:
            findings.append("README tells a story (images/diagrams, detailed)")

        return self._result(score, findings, details)


def _score_description(metadata: RepoMetadata) -> float:
    """Score the GitHub description for quality."""
    desc = metadata.description or ""
    score = 0.0
    if len(desc) > 30:
        score += 0.05
    if len(desc) > 80:
        score += 0.05
    # Check if description has specific content (not just project name)
    name_lower = metadata.name.lower().replace("-", " ").replace("_", " ")
    if desc.lower().strip() != name_lower and len(desc) > len(metadata.name) + 10:
        score += 0.05
    return score


def _score_commit_bursts(owner_weeks: list[int]) -> float:
    """Score based on commit pattern variance — high variance means passionate bursts."""
    if not owner_weeks or len(owner_weeks) < 4:
        return 0.0
    # Only consider non-zero weeks to avoid penalizing new projects
    active_weeks = [w for w in owner_weeks if w > 0]
    if len(active_weeks) < 2:
        return 0.0
    mean = statistics.mean(active_weeks)
    if mean == 0:
        return 0.0
    stdev = statistics.stdev(active_weeks)
    cv = stdev / mean  # coefficient of variation
    # CV > 1.0 means high burst pattern
    if cv > 1.5:
        return 0.15
    if cv > 1.0:
        return 0.10
    if cv > 0.5:
        return 0.05
    return 0.0


def _burst_coefficient(owner_weeks: list[int]) -> float:
    """Return the coefficient of variation for commit patterns."""
    active_weeks = [w for w in (owner_weeks or []) if w > 0]
    if len(active_weeks) < 2:
        return 0.0
    mean = statistics.mean(active_weeks)
    if mean == 0:
        return 0.0
    return round(statistics.stdev(active_weeks) / mean, 2)


def _score_ambition(repo_path: Path, metadata: RepoMetadata) -> tuple[float, dict]:
    """Score project ambition from local file analysis."""
    score = 0.0
    details: dict = {}

    # Multi-module structure (multiple top-level dirs with code)
    code_dirs = [
        d for d in repo_path.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name not in ("node_modules", "vendor", "__pycache__")
    ]
    details["top_level_dirs"] = len(code_dirs)
    if len(code_dirs) >= 3:
        score += 0.05

    # Real external dependencies (>5)
    dep_count = sum(metadata.languages.values()) > 0  # has code
    # Use the already-known dep count from dependencies analyzer if available
    # Fallback: check for manifest files
    for manifest in ("package.json", "Cargo.toml", "pyproject.toml", "go.mod"):
        if (repo_path / manifest).is_file():
            details["has_manifest"] = True
            score += 0.05
            break

    # >1000 LOC
    loc = _estimate_loc(repo_path)
    details["estimated_loc"] = loc
    if loc > 1000:
        score += 0.05

    # Has assets/media files
    asset_count = _count_assets(repo_path)
    details["asset_count"] = asset_count
    if asset_count > 0:
        score += 0.05

    return score, details


def _estimate_loc(repo_path: Path, max_files: int = 200) -> int:
    """Quick LOC estimate from code files."""
    code_exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".swift", ".java", ".c", ".cpp", ".gd"}
    total = 0
    count = 0
    for path in repo_path.rglob("*"):
        if count >= max_files:
            break
        if path.is_file() and path.suffix in code_exts:
            if any(part.startswith(".") or part == "node_modules" for part in path.parts):
                continue
            try:
                total += len(path.read_text(errors="replace").splitlines())
                count += 1
            except OSError:
                continue
    return total


def _count_assets(repo_path: Path, max_scan: int = 500) -> int:
    """Count media/asset files in the repo."""
    count = 0
    scanned = 0
    for path in repo_path.rglob("*"):
        scanned += 1
        if scanned > max_scan:
            break
        if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS:
            count += 1
    return count


def _score_readme_storytelling(repo_path: Path) -> float:
    """Score README for storytelling quality — images, diagrams, length."""
    for name in ("README.md", "README", "README.rst"):
        readme = repo_path / name
        if readme.is_file():
            try:
                content = readme.read_text(errors="replace")
                if len(content) > 1000:
                    has_images = "![" in content and "](" in content
                    has_diagrams = "```mermaid" in content or "```ascii" in content or "<svg" in content
                    if has_images or has_diagrams:
                        return 0.10
                return 0.0
            except OSError:
                return 0.0
    return 0.0
