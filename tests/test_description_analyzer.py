from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.models import RepoMetadata

_DT = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _meta(**kwargs) -> RepoMetadata:
    defaults = dict(
        name="test-repo",
        full_name="user/test-repo",
        description=None,
        language=None,
        languages={},
        topics=[],
        private=False,
        fork=False,
        archived=False,
        created_at=_DT,
        updated_at=_DT,
        pushed_at=_DT,
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=100,
        html_url="https://github.com/user/test-repo",
        clone_url="https://github.com/user/test-repo.git",
        default_branch="main",
    )
    defaults.update(kwargs)
    return RepoMetadata(**defaults)


def test_correct_swift_classification(tmp_path: Path) -> None:
    from src.analyzers.description_analyzer import DescriptionAnalyzer

    (tmp_path / "MyApp.xcodeproj").mkdir()
    meta = _meta(description="A SwiftUI iOS app for tracking habits", language="Swift")
    result = DescriptionAnalyzer().analyze(tmp_path, meta)
    assert result.details["description_confidence"] == 1.0
    assert result.details["description_present"] is True
    assert result.details["conflicting_languages"] == []


def test_misclassified_ios_repo_with_python_description(tmp_path: Path) -> None:
    from src.analyzers.description_analyzer import DescriptionAnalyzer

    (tmp_path / "MyApp.xcodeproj").mkdir()
    meta = _meta(description="A Python CLI script for data processing", language="Swift")
    result = DescriptionAnalyzer().analyze(tmp_path, meta)
    assert result.details["description_confidence"] == 0.2
    assert "Python" in result.details["conflicting_languages"]


def test_missing_description(tmp_path: Path) -> None:
    from src.analyzers.description_analyzer import DescriptionAnalyzer

    meta = _meta(description=None, language="Python")
    result = DescriptionAnalyzer().analyze(tmp_path, meta)
    assert result.details["description_confidence"] == 0.0
    assert result.details["description_present"] is False
    assert result.score == 0.0


def test_unknown_language_returns_full_score(tmp_path: Path) -> None:
    from src.analyzers.description_analyzer import DescriptionAnalyzer

    meta = _meta(description="A COBOL mainframe batch processor", language="COBOL")
    result = DescriptionAnalyzer().analyze(tmp_path, meta)
    assert result.details["description_confidence"] == 1.0
    assert result.details["conflicting_languages"] == []


def test_conflict_with_expected_match_gives_partial_score(tmp_path: Path) -> None:
    from src.analyzers.description_analyzer import DescriptionAnalyzer

    meta = _meta(
        description="A swift iOS app with some react components",
        language="Swift",
    )
    result = DescriptionAnalyzer().analyze(tmp_path, meta)
    assert result.details["description_confidence"] == 0.6
    assert (
        "JavaScript" in result.details["conflicting_languages"]
        or "TypeScript" in result.details["conflicting_languages"]
    )


def test_topics_used_as_conflict_signals(tmp_path: Path) -> None:
    from src.analyzers.description_analyzer import DescriptionAnalyzer

    meta = _meta(
        description="An xcode project for iOS",
        language="Swift",
        topics=["python", "django"],
    )
    result = DescriptionAnalyzer().analyze(tmp_path, meta)
    assert result.details["description_confidence"] == 0.6
    assert "Python" in result.details["conflicting_languages"]
