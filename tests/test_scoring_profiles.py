from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models import AnalyzerResult, RepoMetadata
from src.app.run_audit import _load_scoring_profile
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

    def test_partial_run_grade_discloses_scored_basis(self):
        scored_dimensions = list(WEIGHTS)[:6] + ["documentation"]
        results = _make_results({dim: 0.72 for dim in scored_dimensions})

        audit = score_repo(_make_metadata(), results)

        assert audit.grade == "B"
        assert audit.scored_dimensions == scored_dimensions
        assert audit.scored_weight_sum == 0.75
        assert audit.to_dict()["scored_dimensions"] == scored_dimensions
        assert audit.to_dict()["scored_weight_sum"] == 0.75
        assert audit.to_dict()["grade"] == "B"

    def test_full_run_grade_remains_unqualified(self):
        results = _make_results({dim: 0.72 for dim in WEIGHTS})

        audit = score_repo(_make_metadata(), results)

        assert audit.grade == "B"
        assert audit.scored_dimensions == list(WEIGHTS)
        assert audit.scored_weight_sum == 1.0

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

    def test_flat_profile_loads_weights_without_overrides(self):
        profile, profile_name = _load_scoring_profile("default")

        assert profile_name == "default"
        assert profile is not None
        assert dict(profile) == json.loads(
            Path("config/scoring-profiles/default.json").read_text()
        )
        assert profile.overrides == {}

    def test_profile_reserved_constants_override_scorer(self, tmp_path, monkeypatch):
        profiles_dir = tmp_path / "config/scoring-profiles"
        profiles_dir.mkdir(parents=True)
        profile_path = profiles_dir / "override.json"
        profile_path.write_text(
            json.dumps(
                {
                    **WEIGHTS,
                    "stale_threshold_days": 1,
                    "grade_thresholds": [[0.9, "A"], [0.0, "F"]],
                    "completeness_tiers": [["shipped", 0.8], ["functional", 0.7], ["draft", 0.0]],
                }
            )
        )
        monkeypatch.chdir(tmp_path)
        profile, _ = _load_scoring_profile("override")
        assert profile is not None

        metadata = _make_metadata(
            pushed_at=datetime.now(timezone.utc) - timedelta(days=3)
        )
        results = _make_results({dimension: 0.76 for dimension in WEIGHTS})
        default_audit = score_repo(metadata, results)
        overridden_audit = score_repo(
            metadata,
            results,
            custom_weights=profile,
            scoring_profile=profile.overrides,
        )

        assert dict(profile) == WEIGHTS
        assert default_audit.completeness_tier == "shipped"
        assert overridden_audit.completeness_tier == "wip"
        assert default_audit.grade == "B"
        assert overridden_audit.grade == "F"
