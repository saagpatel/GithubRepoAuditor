from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models import AnalyzerResult, RepoMetadata
from src.scorer import WEIGHTS, score_repo


def _make_results(scores: dict[str, float]) -> list[AnalyzerResult]:
    results = []
    for dim, score in scores.items():
        details: dict = {}
        if dim == "structure":
            details = {"config_files": ["pyproject.toml"], "source_dirs": ["src"]}
        if dim == "code_quality":
            details = {"entry_point": "main.py", "total_loc": 500}
        results.append(AnalyzerResult(dimension=dim, score=score, max_score=1.0, findings=[], details=details))
    return results


def _make_metadata(**overrides) -> RepoMetadata:
    defaults = dict(
        name="test", full_name="user/test", description=None,
        language="Python", languages={}, private=False, fork=False,
        archived=False, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=0, forks=0, open_issues=0,
        size_kb=100, html_url="", clone_url="", topics=[],
    )
    defaults.update(overrides)
    return RepoMetadata(**defaults)


class TestScoringProfiles:
    def test_default_weights_unchanged(self):
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert abs(audit.overall_score - 0.5) < 0.01

    def test_custom_weights_change_score(self):
        scores = {dim: 0.5 for dim in WEIGHTS}
        scores["testing"] = 1.0  # Max testing
        results = _make_results(scores)

        # Default weights: testing = 0.18
        default_audit = score_repo(_make_metadata(), results)

        # Custom weights: testing = 0.50
        custom = dict(WEIGHTS)
        custom["testing"] = 0.50
        custom["activity"] = 0.05
        custom["code_quality"] = 0.05
        # Rebalance to sum to 1.0
        total = sum(custom.values())
        custom = {k: v / total for k, v in custom.items()}

        custom_audit = score_repo(_make_metadata(), results, custom_weights=custom)

        # Custom should score higher because testing is weighted more
        assert custom_audit.overall_score > default_audit.overall_score

    def test_custom_weights_none_uses_default(self):
        results = _make_results({dim: 0.6 for dim in WEIGHTS})
        audit_none = score_repo(_make_metadata(), results, custom_weights=None)
        audit_default = score_repo(_make_metadata(), results)
        assert audit_none.overall_score == audit_default.overall_score

    def test_profile_json_valid(self, tmp_path):
        """Verify profile JSONs sum to ~1.0."""
        from pathlib import Path
        profiles_dir = Path("config/scoring-profiles")
        if not profiles_dir.exists():
            return
        for profile_path in profiles_dir.glob("*.json"):
            weights = json.loads(profile_path.read_text())
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"{profile_path.name} weights sum to {total}"
