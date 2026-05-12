# src/analyzers/description_analyzer.py
from __future__ import annotations

import hashlib
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

_LANG_KEYWORDS: dict[str, frozenset[str]] = {
    "Swift": frozenset(
        ["swift", "ios", "macos", "xcode", "swiftui", "uikit", "appkit", "watchos", "tvos"]
    ),
    "Python": frozenset(
        ["python", "py", "fastapi", "django", "flask", "cli", "script", "notebook"]
    ),
    "Rust": frozenset(["rust", "cargo", "tauri"]),
    "JavaScript": frozenset(["javascript", "js", "react", "node", "next", "vue", "angular"]),
    "TypeScript": frozenset(["typescript", "ts", "react", "next", "node", "vue", "angular"]),
    "Go": frozenset(["go", "golang"]),
}

_FILE_SIGNALS: list[tuple[str, str]] = [
    ("*.xcodeproj", "Swift"),
    ("*.xcworkspace", "Swift"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pyproject.toml", "Python"),
    ("requirements.txt", "Python"),
    ("setup.py", "Python"),
    ("package.json", "JavaScript"),
]


def _detect_language_from_files(repo_path: Path) -> str | None:
    for pattern, lang in _FILE_SIGNALS:
        if "*" in pattern:
            if any(repo_path.glob(pattern)):
                return lang
        elif (repo_path / pattern).exists():
            return lang
    return None


class DescriptionAnalyzer(BaseAnalyzer):
    name = "description"

    def cache_inputs_hash(self, repo_path: Path, metadata: RepoMetadata) -> str:
        key = str(metadata.description) + str(metadata.language) + str(sorted(metadata.topics))
        return hashlib.md5(key.encode()).hexdigest()

    def analyze(
        self, repo_path: Path, metadata: RepoMetadata, github_client: object | None = None
    ) -> AnalyzerResult:
        description = (metadata.description or "").lower()
        topics = {t.lower() for t in metadata.topics}
        if not description:
            return self._result(
                0.0,
                ["No description set"],
                {
                    "description_confidence": 0.0,
                    "description_present": False,
                    "conflicting_languages": [],
                },
            )
        file_lang = _detect_language_from_files(repo_path)
        detected_lang = file_lang or (metadata.language or "")
        expected_keywords = _LANG_KEYWORDS.get(detected_lang, frozenset())
        if not expected_keywords:
            return self._result(
                1.0,
                ["Language not in signal map"],
                {
                    "description_confidence": 1.0,
                    "description_present": True,
                    "conflicting_languages": [],
                },
            )
        all_tokens = set(description.split()) | topics
        conflicts = [
            lang
            for lang, kws in _LANG_KEYWORDS.items()
            if lang != detected_lang and kws & all_tokens
        ]
        expected_match = bool(expected_keywords & all_tokens)
        if conflicts and not expected_match:
            confidence = 0.2
        elif conflicts:
            confidence = 0.6
        elif expected_match:
            confidence = 1.0
        else:
            confidence = 0.8
        findings = [f"Description confidence: {confidence:.1f}"]
        if conflicts:
            findings.append(f"Conflicts: {conflicts}")
        return self._result(
            confidence,
            findings,
            {
                "description_confidence": confidence,
                "description_present": True,
                "conflicting_languages": conflicts,
            },
        )
