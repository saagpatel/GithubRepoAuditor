from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

# Common entry points by language
ENTRY_POINTS: dict[str | None, list[str]] = {
    "Python": ["main.py", "app.py", "src/main.py", "src/app.py", "__main__.py", "src/__main__.py", "manage.py"],
    "JavaScript": ["index.js", "src/index.js", "app.js", "src/app.js", "server.js"],
    "TypeScript": ["index.ts", "src/index.ts", "app.ts", "src/app.ts", "src/main.ts"],
    "Rust": ["src/main.rs", "src/lib.rs"],
    "Go": ["main.go", "cmd/main.go"],
    "Java": ["src/main/java"],
    "Swift": ["Sources/main.swift", "Sources"],
    "C#": ["Program.cs"],
    "Ruby": ["app.rb", "config.ru", "Rakefile"],
    None: ["main.py", "index.js", "index.ts", "src/main.rs", "main.go", "App.tsx"],
}

# Additional patterns that work across languages
GENERIC_ENTRY_PATTERNS = [
    "App.tsx", "App.jsx", "src/App.tsx", "src/App.jsx",
    "index.html", "src/index.html",
]

VENDORED_DIRS = {"node_modules", "vendor", "third_party", "bower_components"}

# Extensions to scan for TODOs
CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".swift", ".rb", ".c", ".cpp", ".h", ".cs", ".kt", ".scala",
    ".sh", ".lua", ".ex", ".exs", ".zig",
})

TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

LAZY_COMMIT_PATTERNS = re.compile(
    r"^(update|fix|wip|initial commit|first commit|\.|\w)$",
    re.IGNORECASE,
)


class CodeQualityAnalyzer(BaseAnalyzer):
    name = "code_quality"
    weight = 0.15

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # Entry point exists
        entry = _find_entry_point(repo_path, metadata.language)
        details["entry_point"] = entry
        if entry:
            score += 0.3
            findings.append(f"Entry point: {entry}")
        else:
            findings.append("No identifiable entry point")

        # TODO/FIXME density
        todo_count, total_loc = _count_todos(repo_path)
        details["todo_count"] = todo_count
        details["total_loc"] = total_loc
        if total_loc > 0:
            density = (todo_count / total_loc) * 1000
            details["todo_density_per_1k"] = round(density, 1)
            if density < 5:
                score += 0.2
                findings.append(f"Low TODO density: {density:.1f}/1k LOC")
            elif density < 10:
                score += 0.1
                findings.append(f"Moderate TODO density: {density:.1f}/1k LOC")
            else:
                findings.append(f"High TODO density: {density:.1f}/1k LOC")
        else:
            findings.append("No code files to assess TODO density")

        # Type definitions
        has_types = _has_type_definitions(repo_path, metadata.language)
        details["has_types"] = has_types
        if has_types:
            score += 0.2
            findings.append("Has type definitions")
        else:
            findings.append("No type definitions detected")

        # No vendored/generated files
        vendored = _detect_vendored(repo_path)
        details["vendored"] = vendored
        if not vendored:
            score += 0.15
            findings.append("No vendored/generated files committed")
        else:
            findings.append(f"Vendored content: {', '.join(vendored)}")

        # Meaningful commit messages + conventional commits (via API)
        if github_client:
            owner = metadata.full_name.split("/")[0]
            commits = github_client.get_recent_commits(owner, metadata.name, count=10)
            commit_score, commit_detail = _score_commit_messages(commits)
            details["commit_quality"] = commit_detail
            score += commit_score * 0.15
            if commit_score >= 0.7:
                findings.append("Commit messages are descriptive")
            else:
                findings.append("Commit messages could be more descriptive")

            # Conventional commit detection
            messages = [c.get("commit", {}).get("message", "").split("\n")[0] for c in commits]
            conv = _classify_commits(messages)
            details.update(conv)
            if conv["conventional_ratio"] > 0.5:
                score = min(1.0, score + 0.05)
                findings.append(f"Conventional commits: {conv['conventional_ratio']:.0%}")

            # PR closure ratio (metadata, not scored)
            prs = github_client.get_pull_requests(owner, metadata.name)
            if prs:
                merged = sum(1 for p in prs if p.get("merged_at"))
                details["pr_total"] = len(prs)
                details["pr_merged"] = merged
                details["pr_merge_ratio"] = round(merged / len(prs), 2) if prs else None
                findings.append(f"PRs: {merged}/{len(prs)} merged")
        else:
            findings.append("Skipped commit message analysis (no API client)")

        # Radon complexity (Python repos only)
        if metadata.language == "Python":
            radon_data = _radon_analysis(repo_path)
            if radon_data:
                details.update(radon_data)
                if radon_data.get("avg_maintainability_index", 0) > 20:
                    findings.append(f"Maintainability: {radon_data['avg_maintainability_index']:.0f}/100")

        return self._result(score, findings, details)


def _find_entry_point(repo_path: Path, language: str | None) -> str | None:
    """Check for language-appropriate entry points."""
    candidates = ENTRY_POINTS.get(language, ENTRY_POINTS[None]) + GENERIC_ENTRY_PATTERNS

    for candidate in candidates:
        path = repo_path / candidate
        if path.is_file() or path.is_dir():
            return candidate

    # Swift/Xcode: check for @main or App.swift in any subdirectory
    if language == "Swift":
        for swift_file in repo_path.rglob("*App.swift"):
            if "DerivedData" not in swift_file.parts:
                return str(swift_file.relative_to(repo_path))
        # Check for *.xcodeproj as an entry point signal
        for child in repo_path.iterdir():
            if child.suffix in (".xcodeproj", ".xcworkspace"):
                return child.name

    return None


def _count_todos(repo_path: Path, max_files: int = 500) -> tuple[int, int]:
    """Count TODO/FIXME occurrences and total lines of code."""
    todo_count = 0
    total_loc = 0
    files_scanned = 0

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in CODE_EXTENSIONS:
            continue
        if any(part in VENDORED_DIRS or part.startswith(".") for part in path.parts):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue

        files_scanned += 1
        if files_scanned > max_files:
            break

        try:
            content = path.read_text(errors="replace")
            lines = content.splitlines()
            total_loc += len(lines)
            for line in lines:
                if TODO_PATTERN.search(line):
                    todo_count += 1
        except OSError:
            continue

    return todo_count, total_loc


def _has_type_definitions(repo_path: Path, language: str | None) -> bool:
    """Check if the project uses type definitions."""
    if language in ("TypeScript", "Rust", "Go", "Java", "Swift", "C#", "Kotlin", "Scala"):
        return True

    # TypeScript files present in JS projects
    ts_files = list(repo_path.glob("**/*.ts"))
    ts_files = [f for f in ts_files if "node_modules" not in f.parts]
    if ts_files:
        return True

    # Python type hints
    if language == "Python":
        for py_file in list(repo_path.rglob("*.py"))[:20]:
            if "node_modules" in py_file.parts:
                continue
            try:
                content = py_file.read_text(errors="replace")
                if "def " in content and ("->" in content or ": " in content):
                    return True
            except OSError:
                continue

    return False


def _detect_vendored(repo_path: Path) -> list[str]:
    """Detect committed vendored or large generated files."""
    issues: list[str] = []

    for vdir in VENDORED_DIRS:
        if (repo_path / vdir).is_dir():
            issues.append(f"{vdir}/ committed")

    # Large files (>1MB)
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                rel = path.relative_to(repo_path)
                issues.append(f"Large file: {rel} ({path.stat().st_size // 1024}KB)")
                if len(issues) >= 5:
                    break
        except OSError:
            continue

    return issues


def _score_commit_messages(commits: list[dict]) -> tuple[float, str]:
    """Score commit messages for quality. Returns (0.0-1.0, description)."""
    if not commits:
        return 0.5, "No commits available"

    messages = []
    for commit in commits:
        msg = commit.get("commit", {}).get("message", "")
        first_line = msg.split("\n")[0].strip()
        messages.append(first_line)

    if not messages:
        return 0.5, "No commit messages"

    good = 0
    for msg in messages:
        if len(msg) > 10 and not LAZY_COMMIT_PATTERNS.match(msg):
            good += 1

    ratio = good / len(messages)
    return ratio, f"{good}/{len(messages)} descriptive commits"


CONVENTIONAL_PATTERN = re.compile(
    r"^(feat|fix|docs|chore|refactor|test|style|perf|ci|build|revert)(\(.+\))?[!]?:\s"
)


def _classify_commits(messages: list[str]) -> dict:
    """Classify commit messages for conventional commit adherence."""
    if not messages:
        return {"conventional_ratio": 0, "commit_types": {}, "has_issue_refs": 0}

    types: Counter = Counter()
    conventional_count = 0
    issue_refs = 0

    for msg in messages:
        if CONVENTIONAL_PATTERN.match(msg):
            conventional_count += 1
            type_ = msg.split(":")[0].split("(")[0].strip()
            types[type_] += 1
        if re.search(r"#\d+", msg):
            issue_refs += 1

    return {
        "conventional_ratio": round(conventional_count / len(messages), 2),
        "commit_types": dict(types),
        "has_issue_refs": round(issue_refs / len(messages), 2),
    }


def _radon_analysis(repo_path: Path, max_files: int = 50) -> dict | None:
    """Run Radon complexity analysis on Python files."""
    try:
        from radon.complexity import cc_visit
        from radon.metrics import mi_visit
    except ImportError:
        return None

    mi_scores: list[float] = []
    worst_cc = 0
    worst_fn = ""
    complex_count = 0
    files_analyzed = 0

    for py_file in repo_path.rglob("*.py"):
        if files_analyzed >= max_files:
            break
        if any(part.startswith(".") or part in ("node_modules", "vendor", "__pycache__") for part in py_file.parts):
            continue
        try:
            source = py_file.read_text(errors="replace")
            if not source.strip():
                continue

            # Maintainability index
            mi = mi_visit(source, True)
            if isinstance(mi, (int, float)):
                mi_scores.append(mi)

            # Cyclomatic complexity
            for block in cc_visit(source):
                if block.complexity > worst_cc:
                    worst_cc = block.complexity
                    worst_fn = f"{py_file.name}:{block.name}"
                if block.complexity > 15:
                    complex_count += 1

            files_analyzed += 1
        except Exception:
            continue

    if not mi_scores:
        return None

    return {
        "avg_maintainability_index": round(sum(mi_scores) / len(mi_scores), 1),
        "worst_cc_function": worst_fn,
        "worst_cc_score": worst_cc,
        "complex_function_count": complex_count,
        "python_files_analyzed": files_analyzed,
    }
