from __future__ import annotations

from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

# Binary file extensions to skip when sampling for comments
BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".zip", ".tar", ".gz", ".bz2",
    ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".class", ".o", ".a",
    ".mp3", ".mp4", ".wav", ".avi",
    ".db", ".sqlite", ".sqlite3",
    ".lock", ".lockb",
})

# Comment prefixes by extension
COMMENT_PREFIXES: dict[str, list[str]] = {
    ".py": ["#"],
    ".js": ["//", "/*"],
    ".ts": ["//", "/*"],
    ".tsx": ["//", "/*"],
    ".jsx": ["//", "/*"],
    ".rs": ["//", "/*"],
    ".go": ["//", "/*"],
    ".rb": ["#"],
    ".java": ["//", "/*"],
    ".swift": ["//", "/*"],
    ".c": ["//", "/*"],
    ".cpp": ["//", "/*"],
    ".h": ["//", "/*"],
    ".sh": ["#"],
    ".yml": ["#"],
    ".yaml": ["#"],
    ".toml": ["#"],
}

DEPLOY_CONFIGS = (
    "vercel.json",
    "netlify.toml",
    "fly.toml",
    "render.yaml",
    "railway.json",
    "app.yaml",
    "Procfile",
    "heroku.yml",
)


class DocumentationAnalyzer(BaseAnalyzer):
    name = "documentation"
    weight = 0.05

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # docs/ directory
        if (repo_path / "docs").is_dir():
            score += 0.3
            findings.append("Has docs/ directory")
        else:
            findings.append("No docs/ directory")

        # CHANGELOG / HISTORY
        changelog_names = (
            "CHANGELOG.md", "CHANGELOG", "CHANGELOG.txt",
            "HISTORY.md", "HISTORY", "CHANGES.md",
        )
        has_changelog = any((repo_path / n).is_file() for n in changelog_names)
        if has_changelog:
            score += 0.3
            findings.append("Has CHANGELOG")
        else:
            findings.append("No CHANGELOG")

        # CONTRIBUTING
        contrib_names = ("CONTRIBUTING.md", "CONTRIBUTING", "CONTRIBUTING.txt")
        has_contributing = any((repo_path / n).is_file() for n in contrib_names)
        if has_contributing:
            score += 0.2
            findings.append("Has CONTRIBUTING guide")
        else:
            findings.append("No CONTRIBUTING guide")

        # Comment density (sample 5 largest code files)
        comment_ratio = _sample_comment_density(repo_path)
        details["comment_ratio"] = comment_ratio
        if comment_ratio is not None and comment_ratio > 0.05:
            score += 0.2
            findings.append(f"Comment density: {comment_ratio:.0%}")
        elif comment_ratio is not None:
            findings.append(f"Low comment density: {comment_ratio:.0%}")
        else:
            findings.append("Could not assess comment density")

        return self._result(score, findings, details)


class BuildReadinessAnalyzer(BaseAnalyzer):
    name = "build_readiness"
    weight = 0.05

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # Dockerfile / docker-compose
        docker_files = []
        for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"):
            if (repo_path / name).is_file():
                docker_files.append(name)
        if docker_files:
            score += 0.3
            findings.append(f"Docker: {', '.join(docker_files)}")
            details["docker"] = docker_files
        else:
            findings.append("No Docker configuration")

        # Makefile or build script
        has_makefile = (repo_path / "Makefile").is_file()
        has_justfile = (repo_path / "justfile").is_file() or (repo_path / "Justfile").is_file()
        if has_makefile or has_justfile:
            score += 0.3
            name = "Makefile" if has_makefile else "justfile"
            findings.append(f"Has {name}")
        else:
            findings.append("No Makefile or build script")

        # .env.example / .env.sample
        env_examples = [
            n for n in (".env.example", ".env.sample", ".env.template")
            if (repo_path / n).is_file()
        ]
        if env_examples:
            score += 0.2
            findings.append(f"Environment template: {env_examples[0]}")
        else:
            findings.append("No .env.example")

        # Deploy config
        deploy_found = [n for n in DEPLOY_CONFIGS if (repo_path / n).is_file()]
        details["deploy_configs"] = deploy_found
        if deploy_found:
            score += 0.2
            findings.append(f"Deploy config: {', '.join(deploy_found)}")
        else:
            findings.append("No deployment configuration")

        return self._result(score, findings, details)


def _sample_comment_density(repo_path: Path, max_files: int = 5) -> float | None:
    """Sample the 5 largest code files and return comment line ratio."""
    code_files: list[tuple[int, Path]] = []

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in BINARY_EXTENSIONS:
            continue
        if path.suffix not in COMMENT_PREFIXES:
            continue
        if any(part.startswith(".") or part == "node_modules" for part in path.parts):
            continue
        try:
            size = path.stat().st_size
            if size > 1_000_000:  # skip files >1MB
                continue
            code_files.append((size, path))
        except OSError:
            continue

    if not code_files:
        return None

    # Take largest files
    code_files.sort(reverse=True)
    sampled = code_files[:max_files]

    total_lines = 0
    comment_lines = 0

    for _, path in sampled:
        try:
            content = path.read_text(errors="replace")
            prefixes = COMMENT_PREFIXES.get(path.suffix, [])
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                total_lines += 1
                if any(stripped.startswith(p) for p in prefixes):
                    comment_lines += 1
        except OSError:
            continue

    if total_lines == 0:
        return None

    return comment_lines / total_lines
