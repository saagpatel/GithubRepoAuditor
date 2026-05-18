# tests/test_readme_staleness_by_age.py
"""Tests for the age-based README staleness flag added in Arc H A2."""
import time
from pathlib import Path
from unittest.mock import patch

from src.analyzers.readme import _compute_readme_staleness


def test_readme_stale_by_age_when_over_threshold():
    now = int(time.time())
    with patch("src.analyzers.readme._git_last_touched_unix", return_value=now - (200 * 86400)):
        result = _compute_readme_staleness(Path("/fake"), "README.md")
    assert result["readme_stale_by_age"] is True


def test_readme_not_stale_by_age_when_under_threshold():
    now = int(time.time())
    with patch("src.analyzers.readme._git_last_touched_unix", return_value=now - (100 * 86400)):
        result = _compute_readme_staleness(Path("/fake"), "README.md")
    assert result["readme_stale_by_age"] is False


def test_readme_stale_by_age_none_when_no_git_history():
    with patch("src.analyzers.readme._git_last_touched_unix", return_value=None):
        result = _compute_readme_staleness(Path("/fake"), "README.md")
    assert result["readme_stale_by_age"] is None


def test_readme_stale_by_age_at_exact_threshold():
    """Exactly 180 days is NOT stale (threshold is strict >)."""
    now = int(time.time())
    with patch("src.analyzers.readme._git_last_touched_unix", return_value=now - (180 * 86400)):
        result = _compute_readme_staleness(Path("/fake"), "README.md")
    assert result["readme_stale_by_age"] is False


def test_readme_stale_by_age_one_day_over_threshold():
    now = int(time.time())
    with patch("src.analyzers.readme._git_last_touched_unix", return_value=now - (181 * 86400)):
        result = _compute_readme_staleness(Path("/fake"), "README.md")
    assert result["readme_stale_by_age"] is True
