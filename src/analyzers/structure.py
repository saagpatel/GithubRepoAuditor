from __future__ import annotations

from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

CONFIG_FILES = {
    "package.json",
    "Cargo.toml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
    "Makefile",
    "mix.exs",
    "deno.json",
    "composer.json",
    "Package.swift",
}

# Language -> expected source directories
LANG_DIRS: dict[str | None, list[str]] = {
    "Python": ["src", "lib", "app"],
    "JavaScript": ["src", "lib", "app", "pages", "components"],
    "TypeScript": ["src", "lib", "app", "pages", "components"],
    "Rust": ["src"],
    "Go": ["cmd", "pkg", "internal"],
    "Java": ["src"],
    "Swift": ["Sources", "src"],
    "C#": ["src"],
    "Ruby": ["lib", "app"],
    "Kotlin": ["src"],
    None: ["src", "lib", "app"],
}


class StructureAnalyzer(BaseAnalyzer):
    name = "structure"
    weight = 0.10

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # .gitignore
        if (repo_path / ".gitignore").is_file():
            score += 0.2
            findings.append("Has .gitignore")
        else:
            findings.append("No .gitignore")

        # Language-standard directory structure
        expected_dirs = LANG_DIRS.get(metadata.language, LANG_DIRS[None])
        found_dirs = [d for d in expected_dirs if (repo_path / d).is_dir()]
        if found_dirs:
            score += 0.3
            findings.append(f"Has standard dirs: {', '.join(found_dirs)}")
            details["source_dirs"] = found_dirs
        else:
            findings.append("No standard source directory structure")

        # Config file
        found_configs = [f for f in CONFIG_FILES if (repo_path / f).is_file()]
        if found_configs:
            score += 0.3
            findings.append(f"Has config: {', '.join(found_configs)}")
            details["config_files"] = found_configs
        else:
            findings.append("No project config file")

        # LICENSE
        license_found = any(
            (repo_path / name).is_file()
            for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")
        )
        if license_found:
            score += 0.1
            findings.append("Has LICENSE")
        else:
            findings.append("No LICENSE file")

        # Directory depth >1
        max_depth = _max_dir_depth(repo_path)
        details["max_depth"] = max_depth
        if max_depth > 1:
            score += 0.1
            findings.append(f"Directory depth: {max_depth}")
        else:
            findings.append("Flat directory structure")

        return self._result(score, findings, details)


def _max_dir_depth(root: Path, max_scan: int = 200) -> int:
    """Walk directory tree and return max depth, capped at max_scan entries."""
    max_depth = 0
    count = 0
    root_depth = len(root.parts)

    for path in root.rglob("*"):
        if path.name.startswith("."):
            continue
        if path.is_dir():
            depth = len(path.parts) - root_depth
            max_depth = max(max_depth, depth)
            count += 1
            if count >= max_scan:
                break

    return max_depth
