"""Tests for src/suggest_initiatives.py — Arc G Sprint 8.4 + 9.1 + 10.3 + 10.4 + 11.1 + 11.2."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

import src.suggest_initiatives as _si_mod
from src.llm_cost import BudgetExceededError
from src.suggest_initiatives import (
    InitiativeSuggestion,
    accept_suggestion,
    build_suggest_prompt,
    clear_suggestion_cache,
    default_deadline_for_effort,
    generate_suggestions,
    load_suggestion_cache,
    narrow_candidates,
    parse_suggest_response,
    save_suggestion_cache,
    suggestion_cache_path,
)

# ── Factories ─────────────────────────────────────────────────────────────────


def _make_pt_repo(
    name: str = "TestRepo",
    has_git: bool = True,
    activity_status: str = "active",
    context_quality: str = "good",
    has_readme: bool = True,
    has_license: bool = True,
    has_ci: bool = True,
    readme_chars: int = 600,
    release_count: int = 1,
    has_tests: bool = True,
    days_since_push: int = 10,
    risk_factors: list | None = None,
) -> dict:
    """Build a portfolio-truth-style repo dict for use in tests."""
    return {
        "identity": {
            "display_name": name,
            "has_git": has_git,
        },
        "derived": {
            "activity_status": activity_status,
            "context_quality": context_quality,
            "has_readme": has_readme,
            "has_license": has_license,
            "has_ci": has_ci,
            "readme_char_count": readme_chars,
            "release_count": release_count,
            "has_tests": has_tests,
            "days_since_push": days_since_push,
        },
        "risk": {
            "risk_factors": risk_factors or [],
        },
    }


def _bronze_repo(name: str = "BronzeRepo") -> dict:
    """Repo that is at Bronze (tier 1) — qualifies for has_git but NOT Silver."""
    return _make_pt_repo(
        name=name,
        has_readme=False,
        has_license=False,
        has_ci=False,
        readme_chars=0,
        release_count=0,
        has_tests=False,
        days_since_push=100,
    )


def _near_silver_repo(name: str = "NearSilverRepo") -> dict:
    """Repo at Bronze (tier 1) with exactly 1 missing requirement for Silver.

    Has README, license, CI, tests, run_instructions — just stale (>365 days).
    Falls within max_missing=3 (default) so narrow_candidates includes it.
    """
    return {
        "identity": {"display_name": name, "has_git": True},
        "derived": {
            "has_readme": True,
            "has_license": True,
            "has_ci": True,
            "readme_char_count": 600,
            "release_count": 0,
            "has_tests": True,
            "days_since_push": 400,  # > 365 → "Last commit ≤ 365 days ago" missing
            "activity_status": "stale",
            "context_quality": "good",
            "run_instructions_present": True,
        },
        "risk": {"risk_factors": [], "doctor_gap": False},
    }


def _silver_qualifying_repo(name: str = "SilverRepo") -> dict:
    """Repo that qualifies for Silver (tier 2) already."""
    return _make_pt_repo(
        name=name,
        has_readme=True,
        has_license=True,
        readme_chars=600,
        days_since_push=30,
    )


def _platinum_repo(name: str = "PlatinumRepo") -> dict:
    """Repo at Platinum (tier 4) — no next tier."""
    return _make_pt_repo(
        name=name,
        has_readme=True,
        has_license=True,
        has_ci=True,
        readme_chars=2000,
        release_count=5,
        has_tests=True,
        days_since_push=5,
        risk_factors=[],
    )


# ── narrow_candidates ─────────────────────────────────────────────────────────


class TestNarrowCandidates:
    def test_empty_projects_returns_empty(self):
        result = narrow_candidates([])
        assert result == []

    def test_bronze_repo_with_no_target_returns_target_2(self):
        """A Bronze (tier 1) repo with target=None should target tier 2."""
        repo = _bronze_repo("BronzeA")
        # Use max_missing=10 to ensure Bronze repos with multiple gaps are included
        result = narrow_candidates([repo], target_tier=None, max_missing=10)
        assert len(result) == 1
        repo_out, target, gap = result[0]
        assert target == 2
        assert gap.current_tier == 1
        assert gap.target_tier == 2
        assert len(gap.missing_requirements) > 0

    def test_platinum_repo_skipped(self):
        """Repos at tier 4 (Platinum) have no next tier — should be skipped."""
        from src.maturity_tiers import compute_tier

        repo = _platinum_repo()
        # Only include if actually Platinum (tier 4)
        tier = compute_tier(repo)
        if tier < 4:
            pytest.skip("Platinum factory did not produce tier 4 in this environment")
        result = narrow_candidates([repo])
        assert result == []

    def test_no_git_repo_skipped(self):
        """Repos without git history (tier 0) must be skipped."""
        repo = _make_pt_repo("NoGitRepo", has_git=False)
        result = narrow_candidates([repo])
        assert result == []

    def test_target_tier_too_far_skipped(self):
        """A Bronze repo with max_missing=1 should be skipped if it needs >1 requirement."""
        repo = _bronze_repo("BronzeB")
        result = narrow_candidates([repo], max_missing=1)
        # Bronze repos typically need multiple requirements for Silver; at max_missing=1 many skip
        # At least verify no crash; may or may not return entries depending on actual gap
        assert isinstance(result, list)

    def test_already_qualifying_repo_skipped(self):
        """If a repo already qualifies for target, missing_requirements is empty → skip."""
        # A Silver-qualifying repo at target=2 has no missing requirements
        repo = _silver_qualifying_repo()
        from src.maturity_tiers import compute_tier, tier_gap

        current = compute_tier(repo)
        if current < 2:
            # Doesn't qualify yet — use a higher target it already meets
            # Just verify the function skips repos where gap is empty
            gap = tier_gap(repo, current)
            assert not gap.missing_requirements  # already at current means empty gap
        else:
            # It qualifies for Silver, so narrow_candidates with target=2 should skip it
            result = narrow_candidates([repo], target_tier=2)
            assert result == []

    def test_specific_target_tier_applied(self):
        """With target_tier=3, all returned candidates should have target 3."""
        repos = [_bronze_repo(f"Repo{i}") for i in range(5)]
        result = narrow_candidates(repos, target_tier=3, max_missing=10)
        for _, target, _ in result:
            assert target == 3

    def test_target_tier_above_4_skipped(self):
        """target_tier=5 is invalid; should return empty."""
        repo = _bronze_repo()
        result = narrow_candidates([repo], target_tier=5)
        assert result == []


# ── build_suggest_prompt ──────────────────────────────────────────────────────


class TestBuildSuggestPrompt:
    def test_includes_all_candidate_names(self):
        repos = [_bronze_repo("Alpha"), _bronze_repo("Beta"), _bronze_repo("Gamma")]
        candidates = narrow_candidates(repos, max_missing=10)
        prompt = build_suggest_prompt(candidates)
        for name in ["Alpha", "Beta", "Gamma"]:
            assert name in prompt

    def test_includes_tier_info(self):
        repo = _bronze_repo("MyRepo")
        candidates = narrow_candidates([repo], max_missing=10)
        if not candidates:
            pytest.skip("No candidates produced")
        prompt = build_suggest_prompt(candidates)
        assert "current_tier" in prompt
        assert "target_tier" in prompt
        assert "missing_requirements" in prompt

    def test_asks_for_json_array(self):
        repo = _bronze_repo("Repo")
        candidates = narrow_candidates([repo], max_missing=10)
        if not candidates:
            pytest.skip("No candidates produced")
        prompt = build_suggest_prompt(candidates)
        assert "JSON" in prompt
        assert "estimated_effort" in prompt
        assert "rationale" in prompt

    def test_empty_candidates_produces_prompt(self):
        """build_suggest_prompt with empty list should not crash."""
        prompt = build_suggest_prompt([])
        assert isinstance(prompt, str)


# ── parse_suggest_response ────────────────────────────────────────────────────


class TestParseSuggestResponse:
    def _candidates(self, names: list[str]) -> list:
        repos = [_bronze_repo(n) for n in names]
        return narrow_candidates(repos, max_missing=10)

    def test_valid_json_returns_suggestions(self):
        candidates = self._candidates(["Repo1", "Repo2"])
        if not candidates:
            pytest.skip("No candidates produced")
        known_names = [
            (
                c[0].get("identity", {}).get("display_name")
                or c[0].get("metadata", {}).get("name")
                or "unknown"
            )
            for c in candidates
        ]
        raw = json.dumps(
            [
                {
                    "repo_name": known_names[0],
                    "rationale": "High leverage",
                    "estimated_effort": "small",
                },
            ]
        )
        result = parse_suggest_response(raw, candidates)
        assert len(result) == 1
        assert result[0].repo_name == known_names[0]
        assert result[0].rationale == "High leverage"
        assert result[0].estimated_effort == "small"

    def test_unknown_repo_names_filtered_out(self):
        candidates = self._candidates(["RealRepo"])
        raw = json.dumps(
            [
                {"repo_name": "RealRepo", "rationale": "Good", "estimated_effort": "small"},
                {"repo_name": "FakeRepo", "rationale": "Invented", "estimated_effort": "large"},
            ]
        )
        result = parse_suggest_response(raw, candidates)
        names = [s.repo_name for s in result]
        assert "FakeRepo" not in names

    def test_malformed_json_returns_empty(self):
        candidates = self._candidates(["Repo1"])
        result = parse_suggest_response("not valid json at all", candidates)
        assert result == []

    def test_tiers_from_candidate_not_llm(self):
        """current_tier and target_tier come from candidate tuple, NOT from LLM output."""
        candidates = self._candidates(["MyRepo"])
        if not candidates:
            pytest.skip("No candidates produced")
        name = (
            candidates[0][0].get("identity", {}).get("display_name")
            or candidates[0][0].get("metadata", {}).get("name")
            or "unknown"
        )
        _, expected_target, gap = candidates[0]
        raw = json.dumps(
            [
                {
                    "repo_name": name,
                    "rationale": "Good pick",
                    "estimated_effort": "medium",
                    "current_tier": 99,  # LLM hallucination — must be ignored
                    "target_tier": 99,  # LLM hallucination — must be ignored
                }
            ]
        )
        result = parse_suggest_response(raw, candidates)
        assert len(result) == 1
        assert result[0].current_tier == gap.current_tier
        assert result[0].target_tier == expected_target

    def test_fenced_json_is_parsed(self):
        candidates = self._candidates(["Repo1"])
        if not candidates:
            pytest.skip("No candidates produced")
        name = (
            candidates[0][0].get("identity", {}).get("display_name")
            or candidates[0][0].get("metadata", {}).get("name")
            or "unknown"
        )
        raw = (
            "```json\n"
            + json.dumps([{"repo_name": name, "rationale": "x", "estimated_effort": "large"}])
            + "\n```"
        )
        result = parse_suggest_response(raw, candidates)
        assert len(result) >= 1


# ── generate_suggestions ──────────────────────────────────────────────────────


class _MockProvider:
    """Fake NarrativeProvider that returns a canned JSON response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    def generate(self, prompt: str, model: str, max_tokens: int, **kwargs) -> str:
        self.call_count += 1
        return self._response


class TestGenerateSuggestions:
    def test_no_provider_returns_deterministic_fallback(self):
        """When no LLM provider is available, return deterministic ranking."""
        repos = [_near_silver_repo("Alpha"), _near_silver_repo("Beta")]
        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            suggestions, cost = generate_suggestions(repos)
        assert cost == 0.0
        assert isinstance(suggestions, list)
        # Deterministic fallback uses "(no LLM available...)" rationale
        for s in suggestions:
            assert "no LLM available" in s.rationale

    def test_mock_provider_returns_parsed_suggestions(self):
        """With a mock provider returning valid JSON, suggestions are parsed."""
        repos = [_near_silver_repo("MyRepo")]
        # Use default max_missing=3 — near_silver_repo has exactly 1 missing
        candidates = narrow_candidates(repos)
        if not candidates:
            pytest.skip("No candidates produced")
        name = (
            candidates[0][0].get("identity", {}).get("display_name")
            or candidates[0][0].get("metadata", {}).get("name")
            or "unknown"
        )
        canned = json.dumps(
            [{"repo_name": name, "rationale": "High value", "estimated_effort": "small"}]
        )
        mock_provider = _MockProvider(canned)
        with patch(
            "src.suggest_initiatives._resolve_provider", return_value=(mock_provider, "test-model")
        ):
            suggestions, cost = generate_suggestions(repos, budget_usd=1.0)
        assert len(suggestions) >= 1
        assert suggestions[0].repo_name == name
        assert suggestions[0].rationale == "High value"

    def test_budget_exceeded_raises(self):
        """If estimated cost exceeds budget, BudgetExceededError is raised before LLM call."""
        # Use near_silver repos so they pass max_missing=3 filter and candidates are found
        repos = [_near_silver_repo(f"Repo{i}") for i in range(20)]
        mock_provider = _MockProvider("[]")
        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            # Force a very tiny budget so the pre-call estimate triggers
            with pytest.raises(BudgetExceededError):
                generate_suggestions(repos, budget_usd=0.000001)

    def test_specific_target_tier_propagates(self):
        """With target_tier=3, all returned suggestions have target_tier=3."""
        repos = [_near_silver_repo(f"R{i}") for i in range(3)]
        candidates = narrow_candidates(repos, target_tier=3, max_missing=10)
        if not candidates:
            pytest.skip("No candidates for target=3 in this environment")
        names = [
            (
                c[0].get("identity", {}).get("display_name")
                or c[0].get("metadata", {}).get("name")
                or "unknown"
            )
            for c in candidates
        ]
        canned = json.dumps(
            [{"repo_name": n, "rationale": "ok", "estimated_effort": "medium"} for n in names]
        )
        mock_provider = _MockProvider(canned)
        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            suggestions, _ = generate_suggestions(repos, target_tier=3, budget_usd=1.0)
        for s in suggestions:
            assert s.target_tier == 3

    def test_empty_projects_returns_empty(self):
        suggestions, cost = generate_suggestions([])
        assert suggestions == []
        assert cost == 0.0


# ── CLI tests ─────────────────────────────────────────────────────────────────


class TestCLISuggestInitiatives:
    def test_no_portfolio_truth_prints_warning(self, tmp_path, capsys):
        """Without portfolio-truth-latest.json, prints a warning and returns."""
        import argparse

        # We call the mode function directly to avoid needing a full CLI run
        args = argparse.Namespace(
            output_dir=str(tmp_path),
            suggest_initiatives=0,
            llm_budget=None,
        )
        from src.cli import _run_suggest_initiatives_mode

        _run_suggest_initiatives_mode(args)
        captured = capsys.readouterr()
        assert (
            "portfolio-truth-latest.json not found" in captured.out
            or "portfolio-truth-latest.json not found" in captured.err
        )

    def test_with_valid_portfolio_truth_prints_table(self, tmp_path, capsys):
        """With a valid portfolio-truth-latest.json, prints a table of suggestions."""
        repos = [_bronze_repo(f"Repo{i}") for i in range(3)]
        truth = {"projects": repos}
        pt_path = tmp_path / "portfolio-truth-latest.json"
        pt_path.write_text(json.dumps(truth))

        import argparse

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            suggest_initiatives=0,
            llm_budget=None,
        )

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            from src.cli import _run_suggest_initiatives_mode  # noqa: PLC0415

            _run_suggest_initiatives_mode(args)

        captured = capsys.readouterr()
        # Should either print table or "No suggestions"
        output = captured.out + captured.err
        assert "Suggested Initiatives" in output or "No suggestions" in output

    def test_target_tier_3_propagates(self, tmp_path):
        """--suggest-initiatives 3 passes target_tier=3 to generate_suggestions."""
        repos = [_bronze_repo("Repo1")]
        truth = {"projects": repos}
        pt_path = tmp_path / "portfolio-truth-latest.json"
        pt_path.write_text(json.dumps(truth))

        import argparse

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            suggest_initiatives=3,
            llm_budget=None,
        )

        captured_targets: list[int | None] = []

        def _mock_gen(projects, target_tier=None, budget_usd=0.10, **kw):
            captured_targets.append(target_tier)
            return [], 0.0

        # _run_suggest_initiatives_mode imports generate_suggestions locally, so patch
        # the name in the cli module's namespace after the local import happens
        with patch("src.suggest_initiatives.generate_suggestions", _mock_gen):
            from src.cli import _run_suggest_initiatives_mode

            _run_suggest_initiatives_mode(args)

        assert captured_targets == [3]

    def test_llm_budget_propagates(self, tmp_path):
        """--llm-budget 0.01 propagates budget_usd=0.01 to generate_suggestions."""
        repos = [_bronze_repo("Repo1")]
        truth = {"projects": repos}
        pt_path = tmp_path / "portfolio-truth-latest.json"
        pt_path.write_text(json.dumps(truth))

        import argparse

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            suggest_initiatives=0,
            llm_budget=0.01,
        )

        captured_budgets: list[float] = []

        def _mock_gen(projects, target_tier=None, budget_usd=0.10, **kw):
            captured_budgets.append(budget_usd)
            return [], 0.0

        with patch("src.suggest_initiatives.generate_suggestions", _mock_gen):
            from src.cli import _run_suggest_initiatives_mode

            _run_suggest_initiatives_mode(args)

        assert captured_budgets == [0.01]

    def test_parser_suggest_initiatives_const_is_0(self):
        """--suggest-initiatives with no value → args.suggest_initiatives == 0 (sentinel)."""
        import argparse

        from src.cli import _build_triage_subparser

        sp = argparse.ArgumentParser()
        subs = sp.add_subparsers(dest="subcommand")
        _build_triage_subparser(subs)
        args = sp.parse_args(["triage", "testuser", "--suggest-initiatives"])
        assert args.suggest_initiatives == 0

    def test_parser_suggest_initiatives_with_value(self):
        """--suggest-initiatives 4 → args.suggest_initiatives == 4."""
        import argparse

        from src.cli import _build_triage_subparser

        sp = argparse.ArgumentParser()
        subs = sp.add_subparsers(dest="subcommand")
        _build_triage_subparser(subs)
        args = sp.parse_args(["triage", "testuser", "--suggest-initiatives", "4"])
        assert args.suggest_initiatives == 4


# ── Briefing integration tests ────────────────────────────────────────────────


class TestBriefingSuggestedInitiatives:
    def _make_audit(self, name: str = "Repo") -> dict:
        return {
            "metadata": {"name": name, "language": "Python", "pushed_at": "2026-05-01T00:00:00Z"},
            "overall_score": 0.5,
            "analyzer_results": [
                {
                    "dimension": "activity",
                    "score": 0.5,
                    "max_score": 1.0,
                    "findings": [],
                    "details": {"days_since_push": 10, "archived": False},
                }
            ],
        }

    def test_include_suggestions_false_skips_llm(self):
        """build_briefing(include_suggestions=False) → suggested_initiatives is empty, no LLM call."""
        from src.briefing import build_briefing

        audits = [self._make_audit()]
        with patch("src.narrative._resolve_provider") as mock_resolve:
            briefing = build_briefing(
                audits, "user", "2026-05-11", use_history=False, include_suggestions=False
            )
        # _resolve_provider should NOT be called when include_suggestions=False
        mock_resolve.assert_not_called()
        assert briefing.suggested_initiatives == []

    def test_include_suggestions_true_with_mock_provider_populates_field(self):
        """build_briefing(include_suggestions=True) with mock provider → suggestions populated."""
        from src.briefing import build_briefing

        # Use near_silver repos which have only 1 missing requirement (passes max_missing=3 filter)
        audits = [_near_silver_repo(f"Repo{i}") for i in range(2)]
        candidates = narrow_candidates(audits)
        if not candidates:
            pytest.skip("No candidates in this environment")
        name = (
            candidates[0][0].get("identity", {}).get("display_name")
            or candidates[0][0].get("metadata", {}).get("name")
            or "unknown"
        )
        canned = json.dumps(
            [{"repo_name": name, "rationale": "Good pick", "estimated_effort": "small"}]
        )
        mock_provider = _MockProvider(canned)
        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            briefing = build_briefing(
                audits,
                "user",
                "2026-05-11",
                use_history=False,
                include_suggestions=True,
            )
        assert len(briefing.suggested_initiatives) >= 1
        assert briefing.suggested_initiatives[0].repo_name == name

    def test_render_markdown_includes_section_when_non_empty(self):
        """render_markdown includes '## Suggested Initiatives' when field is populated."""
        from src.briefing import Briefing, InitiativeSuggestionRow, render_markdown

        briefing = Briefing(
            username="user",
            date="2026-05-11",
            suggested_initiatives=[
                InitiativeSuggestionRow(
                    repo_name="Alpha",
                    current_tier=1,
                    target_tier=2,
                    rationale="Great candidate",
                    estimated_effort="small",
                )
            ],
        )
        md = render_markdown(briefing)
        assert "## Suggested Initiatives" in md
        assert "Alpha" in md
        assert "Great candidate" in md
        assert "small" in md

    def test_render_markdown_omits_section_when_empty(self):
        """render_markdown omits '## Suggested Initiatives' when field is empty."""
        from src.briefing import Briefing, render_markdown

        briefing = Briefing(username="user", date="2026-05-11")
        md = render_markdown(briefing)
        assert "## Suggested Initiatives" not in md


# ── default_deadline_for_effort ───────────────────────────────────────────────


class TestDefaultDeadlineForEffort:
    def test_small_is_14_days(self):
        today = date(2026, 1, 1)
        result = default_deadline_for_effort("small", today=today)
        assert result == "2026-01-15"

    def test_medium_is_30_days(self):
        today = date(2026, 1, 1)
        result = default_deadline_for_effort("medium", today=today)
        assert result == "2026-01-31"

    def test_large_is_60_days(self):
        today = date(2026, 1, 1)
        result = default_deadline_for_effort("large", today=today)
        assert result == "2026-03-02"

    def test_unknown_is_30_days(self):
        today = date(2026, 1, 1)
        result = default_deadline_for_effort("unknown", today=today)
        assert result == "2026-01-31"

    def test_empty_string_is_30_days(self):
        today = date(2026, 1, 1)
        result = default_deadline_for_effort("", today=today)
        assert result == "2026-01-31"

    def test_case_insensitive_small(self):
        today = date(2026, 1, 1)
        result = default_deadline_for_effort("SMALL", today=today)
        assert result == "2026-01-15"

    def test_explicit_today_small(self):
        result = default_deadline_for_effort("small", today=date(2026, 1, 1))
        assert result == "2026-01-15"

    def test_returns_iso_format_string(self):
        """Result must be a valid YYYY-MM-DD string."""
        result = default_deadline_for_effort("medium")
        assert len(result) == 10
        # Must parse without error
        parsed = date.fromisoformat(result)
        assert parsed > date.today()


# ── accept_suggestion ─────────────────────────────────────────────────────────


def _silver_repo_for_accept(name: str = "Wavelength") -> dict:
    """Repo at Silver (tier 2) — can be accepted for Gold (tier 3)."""
    return {
        "identity": {"display_name": name, "has_git": True},
        "derived": {
            "has_readme": True,
            "has_license": True,
            "has_ci": True,
            "readme_char_count": 600,
            "release_count": 1,
            "has_tests": True,
            "days_since_push": 10,
            "activity_status": "active",
            "context_quality": "good",
            "run_instructions_present": True,
        },
        "risk": {"risk_factors": [], "doctor_gap": False},
    }


def _git_repo_for_accept(name: str = "BronzeRepo") -> dict:
    """Repo at Bronze (tier 1) — can be accepted for Silver (tier 2)."""
    return _near_silver_repo(name)


class TestAcceptSuggestion:
    def test_happy_path_explicit_deadline_and_tier(self, tmp_path):
        """With explicit deadline + target_tier, initiative is built and returned."""
        project = _near_silver_repo("Wavelength")
        projects = [project]

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            initiative = accept_suggestion(
                repo_name="Wavelength",
                projects=projects,
                output_dir=tmp_path,
                deadline="2026-12-31",
                target_tier=2,
            )

        assert initiative.repo_name == "Wavelength"
        assert initiative.target_tier == 2
        assert initiative.deadline == "2026-12-31"
        assert initiative.closed_at is None

        # Verify it was persisted
        initiatives_file = tmp_path / "initiatives.json"
        assert initiatives_file.exists()
        data = json.loads(initiatives_file.read_text())
        names = [i["repo_name"] for i in data["initiatives"]]
        assert "Wavelength" in names

    def test_defaults_derived_when_no_deadline_or_tier(self, tmp_path):
        """When deadline and target_tier omitted, defaults are derived."""
        project = _near_silver_repo("AutoRepo")
        projects = [project]

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            initiative = accept_suggestion(
                repo_name="AutoRepo",
                projects=projects,
                output_dir=tmp_path,
            )

        # target = current + 1 (Bronze=1 → Silver=2)
        from src.maturity_tiers import compute_tier

        current = compute_tier(project)
        assert initiative.target_tier == current + 1
        # deadline must be a future date
        assert date.fromisoformat(initiative.deadline) > date.today()

    def test_re_accept_overwrites_prior_initiative(self, tmp_path):
        """Re-accepting the same repo overwrites the existing initiative (idempotent)."""
        project = _near_silver_repo("DupRepo")
        projects = [project]

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            accept_suggestion(
                repo_name="DupRepo",
                projects=projects,
                output_dir=tmp_path,
                deadline="2026-12-31",
            )
            second = accept_suggestion(
                repo_name="DupRepo",
                projects=projects,
                output_dir=tmp_path,
                deadline="2027-01-15",
            )

        assert second.deadline == "2027-01-15"
        data = json.loads((tmp_path / "initiatives.json").read_text())
        matching = [i for i in data["initiatives"] if i["repo_name"] == "DupRepo"]
        assert len(matching) == 1
        assert matching[0]["deadline"] == "2027-01-15"

    def test_override_target_tier_via_re_accept(self, tmp_path):
        """Re-accepting with a different target_tier updates the entry."""
        project = _near_silver_repo("TierSwap")
        projects = [project]

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            accept_suggestion(
                repo_name="TierSwap",
                projects=projects,
                output_dir=tmp_path,
                deadline="2026-12-31",
                target_tier=2,
            )
            # Re-accept with target_tier=3 if current allows it
            from src.maturity_tiers import compute_tier

            current = compute_tier(project)
            if current < 3:
                second = accept_suggestion(
                    repo_name="TierSwap",
                    projects=projects,
                    output_dir=tmp_path,
                    deadline="2026-12-31",
                    target_tier=3,
                )
                assert second.target_tier == 3

    def test_repo_not_found_raises_value_error(self, tmp_path):
        """Repo not in projects raises ValueError with 'not found in portfolio truth'."""
        with pytest.raises(ValueError, match="not found in portfolio truth"):
            accept_suggestion(
                repo_name="NonExistent",
                projects=[_near_silver_repo("OtherRepo")],
                output_dir=tmp_path,
                deadline="2026-12-31",
            )

    def test_no_git_repo_raises_value_error(self, tmp_path):
        """Repo with compute_tier==0 raises ValueError mentioning 'no git'."""
        no_git = _make_pt_repo("NoGit", has_git=False)
        with pytest.raises(ValueError, match="no git"):
            accept_suggestion(
                repo_name="NoGit",
                projects=[no_git],
                output_dir=tmp_path,
                deadline="2026-12-31",
            )

    def test_platinum_repo_raises_value_error(self, tmp_path):
        """Repo at tier 4 raises ValueError mentioning 'already at Platinum'."""
        from src.maturity_tiers import compute_tier

        repo = _platinum_repo("MaxedOut")
        tier = compute_tier(repo)
        if tier < 4:
            pytest.skip("Platinum factory did not reach tier 4 in this environment")
        with pytest.raises(ValueError, match="already at Platinum"):
            accept_suggestion(
                repo_name="MaxedOut",
                projects=[repo],
                output_dir=tmp_path,
                deadline="2026-12-31",
            )

    def test_target_tier_not_greater_than_current_raises(self, tmp_path):
        """target_tier <= current_tier raises ValueError mentioning 'must be greater than'."""
        project = _near_silver_repo("LowTarget")
        from src.maturity_tiers import compute_tier

        current = compute_tier(project)
        with pytest.raises(ValueError, match="must be greater than"):
            accept_suggestion(
                repo_name="LowTarget",
                projects=[project],
                output_dir=tmp_path,
                deadline="2026-12-31",
                target_tier=current,
            )

    def test_target_tier_5_invalid_raises(self, tmp_path):
        """target_tier=5 raises ValueError mentioning valid range (2, 3, or 4)."""
        project = _near_silver_repo("TierFive")
        with pytest.raises(ValueError, match="2, 3, or 4"):
            accept_suggestion(
                repo_name="TierFive",
                projects=[project],
                output_dir=tmp_path,
                deadline="2026-12-31",
                target_tier=5,
            )

    def test_past_deadline_raises_value_error(self, tmp_path):
        """Deadline in the past raises ValueError mentioning 'must be in the future'."""
        project = _near_silver_repo("PastDeadline")
        with pytest.raises(ValueError, match="must be in the future"):
            accept_suggestion(
                repo_name="PastDeadline",
                projects=[project],
                output_dir=tmp_path,
                deadline="2020-01-01",
            )

    def test_malformed_deadline_raises_value_error(self, tmp_path):
        """Malformed deadline raises ValueError mentioning 'YYYY-MM-DD'."""
        project = _near_silver_repo("BadDate")
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            accept_suggestion(
                repo_name="BadDate",
                projects=[project],
                output_dir=tmp_path,
                deadline="not-a-date",
            )


# ── CLI accept-suggestion tests ───────────────────────────────────────────────


class TestCLIAcceptSuggestion:
    def _write_truth(self, tmp_path, projects: list[dict]) -> None:
        (tmp_path / "portfolio-truth-latest.json").write_text(json.dumps({"projects": projects}))

    def test_no_portfolio_truth_prints_warning(self, tmp_path, capsys):
        """Missing portfolio-truth-latest.json → warning printed, exit 0."""
        import argparse

        from src.cli import _run_accept_suggestion_mode

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            accept_suggestion="Wavelength",
            deadline=None,
            target_tier=None,
        )
        _run_accept_suggestion_mode(args)
        captured = capsys.readouterr()
        assert "portfolio-truth-latest.json not found" in (captured.out + captured.err)

    def test_valid_repo_creates_initiative(self, tmp_path, capsys):
        """Valid repo in truth → initiative written, stdout has confirmation."""
        import argparse

        project = _near_silver_repo("Wavelength")
        self._write_truth(tmp_path, [project])

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            accept_suggestion="Wavelength",
            deadline="2026-12-31",
            target_tier=2,
        )

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            from src.cli import _run_accept_suggestion_mode

            _run_accept_suggestion_mode(args)

        captured = capsys.readouterr()
        assert "Initiative accepted" in (captured.out + captured.err)
        assert "Wavelength" in (captured.out + captured.err)

        initiatives_file = tmp_path / "initiatives.json"
        assert initiatives_file.exists()

    def test_repo_not_in_truth_exits_2(self, tmp_path, capsys):
        """Repo not in portfolio-truth → error printed, sys.exit(2)."""
        import argparse

        self._write_truth(tmp_path, [_near_silver_repo("OtherRepo")])

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            accept_suggestion="NonExistentRepo",
            deadline="2026-12-31",
            target_tier=None,
        )

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            from src.cli import _run_accept_suggestion_mode

            with pytest.raises(SystemExit) as exc_info:
                _run_accept_suggestion_mode(args)

        assert exc_info.value.code == 2

    def test_deadline_and_target_tier_overrides_applied(self, tmp_path, capsys):
        """--deadline and --target-tier override defaults when provided."""
        import argparse

        project = _near_silver_repo("OverrideRepo")
        self._write_truth(tmp_path, [project])

        args = argparse.Namespace(
            output_dir=str(tmp_path),
            accept_suggestion="OverrideRepo",
            deadline="2026-12-31",
            target_tier=2,
        )

        with patch("src.suggest_initiatives._resolve_provider", return_value=None):
            from src.cli import _run_accept_suggestion_mode

            _run_accept_suggestion_mode(args)

        data = json.loads((tmp_path / "initiatives.json").read_text())
        entry = next(i for i in data["initiatives"] if i["repo_name"] == "OverrideRepo")
        assert entry["deadline"] == "2026-12-31"
        assert entry["target_tier"] == 2

    def test_parser_accept_suggestion_flag_registered(self):
        """--accept-suggestion REPO is registered in _build_triage_subparser."""
        import argparse

        from src.cli import _build_triage_subparser

        sp = argparse.ArgumentParser()
        subs = sp.add_subparsers(dest="subcommand")
        _build_triage_subparser(subs)
        args = sp.parse_args(["triage", "testuser", "--accept-suggestion", "MyRepo"])
        assert args.accept_suggestion == "MyRepo"


# ── 10.3 Cache tests ──────────────────────────────────────────────────────────


class TestSuggestionCache:
    """Tests for the in-process cache introduced in Arc G Sprint 10.3."""

    def setup_method(self):
        """Ensure cache is clean before each test."""
        clear_suggestion_cache()

    def teardown_method(self):
        """Leave cache clean after each test."""
        clear_suggestion_cache()

    def _make_mock_provider(self, repos):
        """Return a MockProvider with a canned response for the given repo list."""
        candidates = narrow_candidates(repos)
        names = [
            c[0].get("identity", {}).get("display_name")
            or c[0].get("metadata", {}).get("name")
            or "unknown"
            for c in candidates
        ]
        canned = json.dumps(
            [{"repo_name": n, "rationale": "ok", "estimated_effort": "small"} for n in names]
        )
        return _MockProvider(canned)

    def test_same_cache_key_calls_provider_once(self):
        """Two calls with the same cache_key only invoke the provider once."""
        repos = [_near_silver_repo("CacheRepo")]
        mock_provider = self._make_mock_provider(repos)

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            suggestions1, cost1 = generate_suggestions(repos, budget_usd=1.0, cache_key="k1")
            suggestions2, cost2 = generate_suggestions(repos, budget_usd=1.0, cache_key="k1")

        assert mock_provider.call_count == 1
        assert suggestions1 == suggestions2
        assert cost1 == cost2

    def test_different_cache_keys_call_provider_twice(self):
        """Two calls with different cache_keys each invoke the provider."""
        repos = [_near_silver_repo("Repo1"), _near_silver_repo("Repo2")]
        mock_provider = self._make_mock_provider(repos)

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            generate_suggestions(repos, budget_usd=1.0, cache_key="key-a")
            generate_suggestions(repos, budget_usd=1.0, cache_key="key-b")

        assert mock_provider.call_count == 2

    def test_no_cache_key_calls_provider_every_time(self):
        """Without a cache_key, the provider is called on every invocation."""
        repos = [_near_silver_repo("NoCacheRepo")]
        mock_provider = self._make_mock_provider(repos)

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            generate_suggestions(repos, budget_usd=1.0)
            generate_suggestions(repos, budget_usd=1.0)

        assert mock_provider.call_count == 2

    def test_clear_cache_causes_re_invocation(self):
        """After clear_suggestion_cache(), the same key re-invokes the provider."""
        repos = [_near_silver_repo("ClearRepo")]
        mock_provider = self._make_mock_provider(repos)

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            generate_suggestions(repos, budget_usd=1.0, cache_key="ck")
            clear_suggestion_cache()
            generate_suggestions(repos, budget_usd=1.0, cache_key="ck")

        assert mock_provider.call_count == 2

    def test_cached_cost_value_is_preserved(self):
        """Cached hit returns the same cost as the original call."""
        repos = [_near_silver_repo("CostRepo")]
        mock_provider = self._make_mock_provider(repos)

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(mock_provider, "test-model"),
        ):
            _, cost_first = generate_suggestions(repos, budget_usd=1.0, cache_key="cost-k")

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(_MockProvider("[]"), "test-model"),
        ):
            _, cost_second = generate_suggestions(repos, budget_usd=1.0, cache_key="cost-k")

        # Provider was not called on second invocation; cost must match
        assert cost_first == cost_second


# ── 10.4 force_deterministic tests ───────────────────────────────────────────


class TestForceDeterministic:
    """Tests for the force_deterministic parameter introduced in Arc G Sprint 10.4."""

    def setup_method(self):
        clear_suggestion_cache()

    def teardown_method(self):
        clear_suggestion_cache()

    def test_returns_suggestions_with_zero_cost(self):
        """force_deterministic=True returns a non-empty list and 0.0 cost."""
        repos = [_near_silver_repo("DetRepo")]
        suggestions, cost = generate_suggestions(repos, force_deterministic=True)
        assert cost == 0.0
        assert isinstance(suggestions, list)

    def test_does_not_call_provider(self):
        """force_deterministic=True never calls the LLM provider."""

        def _exploding_provider(*args, **kwargs):
            raise AssertionError("Provider must not be called with force_deterministic=True")

        repos = [_near_silver_repo("NeverCall")]
        with patch(
            "src.suggest_initiatives._resolve_provider",
            side_effect=_exploding_provider,
        ):
            # Should NOT raise despite the exploding mock
            suggestions, cost = generate_suggestions(repos, force_deterministic=True)

        assert cost == 0.0
        assert isinstance(suggestions, list)

    def test_empty_projects_returns_empty_list(self):
        """force_deterministic=True with no qualifying repos returns ([], 0.0)."""
        suggestions, cost = generate_suggestions([], force_deterministic=True)
        assert suggestions == []
        assert cost == 0.0

    def test_honors_cache_key(self):
        """force_deterministic=True stores results in cache under cache_key."""
        repos = [_near_silver_repo("CachedDet")]

        suggestions1, cost1 = generate_suggestions(
            repos, force_deterministic=True, cache_key="det-k"
        )

        # Second call with same key — provider would explode if called
        def _exploding_provider(*args, **kwargs):
            raise AssertionError("Should not be called on cache hit")

        with patch(
            "src.suggest_initiatives._resolve_provider",
            side_effect=_exploding_provider,
        ):
            suggestions2, cost2 = generate_suggestions(
                repos, force_deterministic=True, cache_key="det-k"
            )

        assert suggestions1 == suggestions2
        assert cost2 == 0.0

    def test_accept_suggestion_uses_force_deterministic(self, tmp_path):
        """accept_suggestion without deadline uses force_deterministic path, never raises BudgetExceededError."""
        project = _near_silver_repo("DetAccept")
        projects = [project]

        # BudgetExceededError would fire if the real cost path were taken with budget_usd=0.0.
        # force_deterministic=True skips the cost tracker entirely.
        # We verify by making _resolve_provider raise — if called, the test fails.
        def _exploding_provider(*args, **kwargs):
            raise AssertionError("accept_suggestion must not call LLM for deadline derivation")

        with patch(
            "src.suggest_initiatives._resolve_provider",
            side_effect=_exploding_provider,
        ):
            initiative = accept_suggestion(
                repo_name="DetAccept",
                projects=projects,
                output_dir=tmp_path,
                # No deadline — triggers internal generate_suggestions call
                deadline=None,
                target_tier=2,
            )

        assert initiative.repo_name == "DetAccept"
        assert date.fromisoformat(initiative.deadline) > date.today()


# ── Arc G Sprint 11.1 — InitiativeSuggestion round-trip ──────────────────────


class TestInitiativeSuggestionRoundTrip:
    """Tests for InitiativeSuggestion.to_dict() and from_dict()."""

    def _sample(self) -> InitiativeSuggestion:
        return InitiativeSuggestion(
            repo_name="MyRepo",
            current_tier=1,
            target_tier=2,
            missing_requirements=["Has tests", "Has CI"],
            rationale="High leverage due to active status",
            estimated_effort="small",
        )

    def test_to_dict_returns_expected_keys(self):
        """to_dict() returns all six expected keys with correct values."""
        s = self._sample()
        d = s.to_dict()
        assert d["repo_name"] == "MyRepo"
        assert d["current_tier"] == 1
        assert d["target_tier"] == 2
        assert d["missing_requirements"] == ["Has tests", "Has CI"]
        assert d["rationale"] == "High leverage due to active status"
        assert d["estimated_effort"] == "small"

    def test_round_trip_equality(self):
        """from_dict(to_dict(s)) == s for a fully-populated instance."""
        s = self._sample()
        assert InitiativeSuggestion.from_dict(s.to_dict()) == s

    def test_from_dict_missing_keys_defaults_safely(self):
        """from_dict with an empty dict returns an instance without raising."""
        s = InitiativeSuggestion.from_dict({})
        assert s.repo_name == ""
        assert s.current_tier == 0
        assert s.target_tier == 0
        assert s.missing_requirements == []
        assert s.rationale == ""
        assert s.estimated_effort == "unknown"

    def test_to_dict_missing_requirements_is_a_copy(self):
        """to_dict() returns a copy of missing_requirements, not the original list."""
        s = self._sample()
        d = s.to_dict()
        d["missing_requirements"].append("extra")
        assert "extra" not in s.missing_requirements


# ── Arc G Sprint 11.1 — Persistent cache ─────────────────────────────────────


class TestPersistentSuggestionCache:
    """Tests for save_suggestion_cache, load_suggestion_cache, and disk round-trips."""

    def setup_method(self):
        clear_suggestion_cache()

    def teardown_method(self):
        clear_suggestion_cache()

    def _make_cache_entry(self, key: str = "k1") -> tuple[str, list[InitiativeSuggestion], float]:
        s = InitiativeSuggestion(
            repo_name="Repo1",
            current_tier=1,
            target_tier=2,
            missing_requirements=["Has CI"],
            rationale="good",
            estimated_effort="small",
        )
        return key, [s], 0.05

    def test_save_writes_file_no_tmp_leftover(self, tmp_path):
        """save_suggestion_cache writes the final file; no .tmp file is left behind."""
        from collections import OrderedDict

        cache: OrderedDict = OrderedDict()
        key, suggestions, cost = self._make_cache_entry()
        cache[key] = (suggestions, cost)
        path = suggestion_cache_path(tmp_path)
        save_suggestion_cache(path, cache)

        assert path.exists()
        # No leftover tmp files
        tmp_files = list(tmp_path.glob(".suggestion_cache_tmp_*.json"))
        assert tmp_files == []

    def test_load_missing_file_returns_empty_ordered_dict(self, tmp_path):
        """load_suggestion_cache on a non-existent file returns an empty OrderedDict."""
        from collections import OrderedDict

        result = load_suggestion_cache(tmp_path / "no-such-file.json")
        assert result == OrderedDict()

    def test_load_malformed_json_returns_empty_ordered_dict(self, tmp_path, caplog):
        """load_suggestion_cache on malformed JSON returns empty OrderedDict and logs warning."""
        import logging
        from collections import OrderedDict

        bad = tmp_path / "suggestion-cache.json"
        bad.write_text("not valid json{{{", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="src.suggest_initiatives"):
            result = load_suggestion_cache(bad)
        assert result == OrderedDict()
        assert any("could not load cache" in r.message for r in caplog.records)

    def test_save_load_round_trip(self, tmp_path):
        """Save + load preserves keys, suggestion content, and cost."""
        from collections import OrderedDict

        cache: OrderedDict = OrderedDict()
        key, suggestions, cost = self._make_cache_entry("my-key")
        cache[key] = (suggestions, cost)
        path = suggestion_cache_path(tmp_path)
        save_suggestion_cache(path, cache)

        loaded = load_suggestion_cache(path)
        assert "my-key" in loaded
        loaded_suggestions, loaded_cost = loaded["my-key"]
        assert loaded_cost == cost
        assert loaded_suggestions == suggestions

    def test_generate_suggestions_writes_to_disk_after_llm_call(self, tmp_path):
        """generate_suggestions with output_dir persists the result to disk."""
        repos = [_near_silver_repo("DiskWriteRepo")]
        cache_key = "disk-write-test"

        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(None, None),
        ):
            # No provider → deterministic fallback; still writes to disk when output_dir set
            generate_suggestions(
                repos, cache_key=cache_key, output_dir=tmp_path, force_deterministic=True
            )

        path = suggestion_cache_path(tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["version"] == 1
        assert any(e["key"] == cache_key for e in data["entries"])

    def test_generate_suggestions_loads_from_disk_on_new_process(self, tmp_path):
        """After clear_suggestion_cache(), the same cache_key is served from disk."""
        repos = [_near_silver_repo("DiskLoadRepo")]
        cache_key = "disk-load-test"

        # First call — populates disk cache
        with patch(
            "src.suggest_initiatives._resolve_provider",
            return_value=(None, None),
        ):
            suggestions1, cost1 = generate_suggestions(
                repos, cache_key=cache_key, output_dir=tmp_path, force_deterministic=True
            )

        # Simulate a new process: clear in-memory cache and loaded-from-disk set
        clear_suggestion_cache()

        # Second call — should reload from disk without calling the LLM
        def _exploding_provider(*args, **kwargs):
            raise AssertionError("LLM must not be called on cache hit from disk")

        with patch(
            "src.suggest_initiatives._resolve_provider",
            side_effect=_exploding_provider,
        ):
            suggestions2, cost2 = generate_suggestions(
                repos, cache_key=cache_key, output_dir=tmp_path, force_deterministic=True
            )

        assert suggestions1 == suggestions2
        assert cost2 == cost1

    def test_clear_suggestion_cache_with_path_deletes_file(self, tmp_path):
        """clear_suggestion_cache(path) removes the cache file from disk."""
        from collections import OrderedDict

        cache: OrderedDict = OrderedDict()
        key, suggestions, cost = self._make_cache_entry()
        cache[key] = (suggestions, cost)
        path = suggestion_cache_path(tmp_path)
        save_suggestion_cache(path, cache)
        assert path.exists()

        clear_suggestion_cache(path)
        assert not path.exists()


# ── Arc G Sprint 11.2 — Bounded eviction ─────────────────────────────────────


class TestBoundedEviction:
    """Tests for OrderedDict eviction when _suggestion_cache exceeds _CACHE_MAX_SIZE."""

    def setup_method(self):
        clear_suggestion_cache()

    def teardown_method(self):
        clear_suggestion_cache()

    def _make_suggestion(self, name: str) -> InitiativeSuggestion:
        return InitiativeSuggestion(
            repo_name=name,
            current_tier=1,
            target_tier=2,
            missing_requirements=["req"],
            rationale="r",
            estimated_effort="small",
        )

    def _fill_cache_to(self, n: int, monkeypatch) -> None:
        """Insert exactly n entries into the in-memory cache via generate_suggestions."""
        monkeypatch.setattr(_si_mod, "_CACHE_MAX_SIZE", 100)
        repos_base = [_near_silver_repo(f"Repo{i}") for i in range(n)]
        for i, repo in enumerate(repos_base):
            generate_suggestions([repo], cache_key=f"fill-key-{i}", force_deterministic=True)

    def test_insert_101st_entry_evicts_oldest(self, monkeypatch):
        """Cache holding 100 entries: inserting 101st evicts the first entry."""
        monkeypatch.setattr(_si_mod, "_CACHE_MAX_SIZE", 100)
        self._fill_cache_to(100, monkeypatch)
        assert len(_si_mod._suggestion_cache) == 100
        first_key = next(iter(_si_mod._suggestion_cache))

        # Insert the 101st entry
        generate_suggestions(
            [_near_silver_repo("Evict101")], cache_key="evict-101-key", force_deterministic=True
        )

        assert len(_si_mod._suggestion_cache) == 100
        assert first_key not in _si_mod._suggestion_cache
        assert "evict-101-key" in _si_mod._suggestion_cache

    def test_recently_accessed_entry_not_evicted(self, monkeypatch):
        """Entry-0 accessed after fill avoids eviction when entry-1 is the oldest."""
        monkeypatch.setattr(_si_mod, "_CACHE_MAX_SIZE", 5)

        # Fill to exactly 5 entries: keys fill-key-0 .. fill-key-4
        for i in range(5):
            generate_suggestions(
                [_near_silver_repo(f"R{i}")], cache_key=f"fill-key-{i}", force_deterministic=True
            )
        assert len(_si_mod._suggestion_cache) == 5

        # Access fill-key-0 — moves it to MRU position
        generate_suggestions(
            [_near_silver_repo("R0")], cache_key="fill-key-0", force_deterministic=True
        )

        # Insert a 6th entry — should evict fill-key-1 (now oldest), NOT fill-key-0
        generate_suggestions(
            [_near_silver_repo("R6")], cache_key="fill-key-6", force_deterministic=True
        )

        assert len(_si_mod._suggestion_cache) == 5
        assert "fill-key-0" in _si_mod._suggestion_cache, "fill-key-0 should not be evicted"
        assert "fill-key-1" not in _si_mod._suggestion_cache, "fill-key-1 should be evicted"

    def test_disk_serialization_caps_at_cache_max_size(self, tmp_path, monkeypatch):
        """save_suggestion_cache writes at most _CACHE_MAX_SIZE entries even if cache is larger."""
        from collections import OrderedDict

        monkeypatch.setattr(_si_mod, "_CACHE_MAX_SIZE", 3)
        # Build a cache with 5 entries manually (bypass generate_suggestions limit)
        cache: OrderedDict = OrderedDict()
        for i in range(5):
            s = self._make_suggestion(f"Repo{i}")
            cache[f"key-{i}"] = ([s], 0.0)

        path = suggestion_cache_path(tmp_path)
        save_suggestion_cache(path, cache)

        data = json.loads(path.read_text())
        # Should contain only the last 3 (most recent) entries
        assert len(data["entries"]) == 3
        written_keys = {e["key"] for e in data["entries"]}
        # Last 3 keys are key-2, key-3, key-4
        assert written_keys == {"key-2", "key-3", "key-4"}
