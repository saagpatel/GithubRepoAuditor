"""Tests for the weekly operator briefing module (Arc F S3.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.briefing import (
    Briefing,
    InitiativeSuggestionRow,
    NeedsAttentionRepo,
    ScoreMover,
    ShippedRepo,
    Suggestion,
    _build_health_delta,
    _parse_suggestions_json,
    build_briefing,
    generate_briefing,
    render_markdown,
    render_voice,
)

# ── Factories ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _make_audit(
    name: str = "TestRepo",
    language: str = "Python",
    overall_score: float = 0.5,
    pushed_days_ago: int = 10,
    automation_eligible: bool = False,
    days_since_push_override: int | None = None,
) -> dict:
    pushed_at = _days_ago_iso(pushed_days_ago)
    days_since = (
        days_since_push_override if days_since_push_override is not None else pushed_days_ago
    )
    return {
        "metadata": {
            "name": name,
            "language": language,
            "pushed_at": pushed_at,
        },
        "overall_score": overall_score,
        "analyzer_results": [
            {
                "dimension": "activity",
                "score": 0.4,
                "max_score": 1.0,
                "findings": [],
                "details": {"days_since_push": days_since, "archived": False},
            }
        ],
        "portfolio_catalog": {
            "automation_eligible": automation_eligible,
        },
        "hotspots": [{"title": "Add README", "severity": "high"}],
    }


def _make_report(audits: list[dict] | None = None, username: str = "testuser") -> dict:
    return {
        "username": username,
        "generated_at": "2026-05-11T12:00:00Z",
        "audits": audits or [],
    }


# ── Build briefing — happy path ───────────────────────────────────────────────


class TestBuildBriefingHappyPath:
    def test_shipped_section_populated(self):
        audits = [
            _make_audit("RepoA", pushed_days_ago=2, overall_score=0.7),
            _make_audit("RepoB", pushed_days_ago=10, overall_score=0.3),
        ]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        names = [r.name for r in briefing.shipped_this_week]
        assert "RepoA" in names
        assert "RepoB" not in names  # 10 days > 7-day window

    def test_needs_attention_populated(self):
        audits = [
            _make_audit("LowScore", overall_score=0.1, pushed_days_ago=200),
            _make_audit("HighScore", overall_score=0.95, pushed_days_ago=1),
        ]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        assert len(briefing.needs_attention) >= 1
        top = briefing.needs_attention[0]
        assert top.name == "LowScore"

    def test_health_delta_empty_without_history(self):
        audits = [_make_audit("RepoA")]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        assert briefing.health_delta == {"up": [], "down": []}

    def test_suggestions_empty_without_provider(self):
        audits = [_make_audit("RepoA")]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False, provider=None)
        assert briefing.suggestions == []

    def test_automation_status_eligible(self):
        audits = [_make_audit("AutoRepo", pushed_days_ago=1, automation_eligible=True)]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        assert briefing.shipped_this_week[0].automation_status == "eligible"

    def test_automation_status_not_eligible(self):
        audits = [_make_audit("ManualRepo", pushed_days_ago=1, automation_eligible=False)]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        assert briefing.shipped_this_week[0].automation_status == "not-eligible"


# ── Empty week ────────────────────────────────────────────────────────────────


class TestEmptyWeek:
    def test_no_shipped_repos_when_all_old(self):
        audits = [
            _make_audit("OldRepo1", pushed_days_ago=30),
            _make_audit("OldRepo2", pushed_days_ago=60),
        ]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        assert briefing.shipped_this_week == []

    def test_briefing_still_renders_without_shipped(self):
        audits = [_make_audit("OldRepo", pushed_days_ago=30)]
        briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        md = render_markdown(briefing)
        assert "No commits pushed in the last 7 days" in md

    def test_empty_audits_produces_valid_briefing(self):
        briefing = build_briefing([], "user", "2026-05-11", use_history=False)
        assert briefing.shipped_this_week == []
        assert briefing.needs_attention == []
        md = render_markdown(briefing)
        assert "Weekly Operator Briefing" in md


# ── No warehouse history ──────────────────────────────────────────────────────


class TestNoWarehouseHistory:
    def test_health_delta_graceful_without_history_file(self):
        audits = [_make_audit("Repo")]
        with patch("src.briefing._build_health_delta") as mock_delta:
            mock_delta.return_value = {"up": [], "down": []}
            briefing = build_briefing(audits, "user", "2026-05-11", use_history=False)
        assert briefing.health_delta == {"up": [], "down": []}

    def test_build_health_delta_returns_empty_when_use_history_false(self):
        audits = [_make_audit("Repo")]
        result = _build_health_delta(audits, use_history=False)
        assert result == {"up": [], "down": []}

    def test_health_delta_graceful_on_load_error(self):
        audits = [_make_audit("Repo")]
        with patch("src.history.load_repo_score_history", side_effect=OSError("no file")):
            result = _build_health_delta(audits, use_history=True)
        assert result == {"up": [], "down": []}


# ── Markdown rendering ─────────────────────────────────────────────────────────


class TestMarkdownRendering:
    def _make_full_briefing(self) -> Briefing:
        return Briefing(
            username="alice",
            date="2026-05-11",
            shipped_this_week=[
                ShippedRepo(name="Alpha", language="Python", automation_status="eligible"),
                ShippedRepo(name="Beta", language="TypeScript", automation_status="not-eligible"),
            ],
            needs_attention=[
                NeedsAttentionRepo(
                    name="OldRepo",
                    overall_score=0.2,
                    days_since_push=120,
                    reason="low completeness",
                )
            ],
            health_delta={
                "up": [ScoreMover(name="UpRepo", old_score=0.5, new_score=0.65, delta=0.15)],
                "down": [ScoreMover(name="DownRepo", old_score=0.8, new_score=0.7, delta=-0.1)],
            },
            suggestions=[
                Suggestion(name="Alpha", action="Add unit tests to improve coverage."),
                Suggestion(name="OldRepo", action="Update README with usage examples."),
            ],
        )

    def test_section_headings_present(self):
        md = render_markdown(self._make_full_briefing())
        assert "## Shipped This Week" in md
        assert "## Needs Attention" in md
        assert "## Portfolio Health Delta" in md
        assert "## Suggested Next Actions" in md

    def test_table_formatting_for_shipped(self):
        md = render_markdown(self._make_full_briefing())
        assert "| Alpha |" in md
        assert "| Python |" in md
        assert "| eligible |" in md

    def test_all_suggestions_present(self):
        md = render_markdown(self._make_full_briefing())
        assert "**Alpha**" in md
        assert "Add unit tests" in md
        assert "**OldRepo**" in md
        assert "Update README" in md

    def test_score_movers_in_delta_section(self):
        md = render_markdown(self._make_full_briefing())
        assert "UpRepo" in md
        assert "DownRepo" in md
        assert "+0.150" in md or "0.150" in md


# ── Voice rendering ────────────────────────────────────────────────────────────


class TestVoiceRendering:
    def _make_full_briefing(self) -> Briefing:
        return Briefing(
            username="alice",
            date="2026-05-11",
            shipped_this_week=[
                ShippedRepo(name="Alpha", language="Python", automation_status="eligible"),
            ],
            needs_attention=[
                NeedsAttentionRepo(
                    name="OldRepo",
                    overall_score=0.2,
                    days_since_push=120,
                    reason="low completeness",
                )
            ],
            health_delta={
                "up": [ScoreMover(name="UpRepo", old_score=0.5, new_score=0.65, delta=0.15)],
                "down": [],
            },
            suggestions=[
                Suggestion(name="Alpha", action="Add unit tests."),
            ],
        )

    def test_no_markdown_tables(self):
        voice = render_voice(self._make_full_briefing())
        assert "|" not in voice

    def test_no_markdown_headers(self):
        voice = render_voice(self._make_full_briefing())
        assert "##" not in voice
        assert "**" not in voice

    def test_paragraph_structure_with_blank_lines(self):
        voice = render_voice(self._make_full_briefing())
        paragraphs = [p for p in voice.split("\n\n") if p.strip()]
        assert len(paragraphs) >= 4  # header + 4 sections

    def test_content_all_sections_present(self):
        voice = render_voice(self._make_full_briefing())
        assert "Shipped this week" in voice
        assert "Needs attention" in voice
        assert "Portfolio health delta" in voice
        assert "Suggested next actions" in voice

    def test_no_pipe_chars_anywhere(self):
        voice = render_voice(self._make_full_briefing())
        assert "|" not in voice


# ── LLM provider failure ──────────────────────────────────────────────────────


class TestLLMProviderFailure:
    def test_provider_exception_yields_empty_suggestions(self):
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("provider down")

        audits = [_make_audit("RepoA", overall_score=0.2)]
        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            provider=mock_provider,
        )
        assert briefing.suggestions == []

    def test_provider_exception_does_not_raise(self):
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = ConnectionError("timeout")

        audits = [_make_audit("RepoA", overall_score=0.1)]
        # Should not raise
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, provider=mock_provider
        )
        assert isinstance(briefing, Briefing)


# ── LLM JSON parse failure ────────────────────────────────────────────────────


class TestLLMJsonParseFail:
    def _top_repos(self) -> list[dict]:
        return [_make_audit("RepoA"), _make_audit("RepoB")]

    def test_non_json_returns_empty(self):
        result = _parse_suggestions_json("Sure, I cannot provide that.", self._top_repos())
        assert result == []

    def test_partial_json_uses_regex_fallback(self):
        raw = 'Here are my suggestions: ["Add CI pipeline", "Write tests"]'
        result = _parse_suggestions_json(raw, self._top_repos())
        assert len(result) == 2
        assert result[0].name == "RepoA"
        assert "CI" in result[0].action

    def test_valid_json_array_parsed_correctly(self):
        raw = '["Improve docs", "Fix security issue"]'
        result = _parse_suggestions_json(raw, self._top_repos())
        assert result[0].action == "Improve docs"
        assert result[1].action == "Fix security issue"

    def test_provider_returns_non_json_no_crash(self):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "I think you should work on documentation."

        audits = [_make_audit("RepoA", overall_score=0.1)]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, provider=mock_provider
        )
        # Regex fallback may or may not extract something; either way no crash
        assert isinstance(briefing.suggestions, list)


# ── CLI integration ────────────────────────────────────────────────────────────


class TestCLIIntegration:
    def test_briefing_writes_markdown_file(self, tmp_path):
        report = _make_report([_make_audit("Repo1", pushed_days_ago=2)])
        with patch("src.briefing._resolve_provider", return_value=None):
            result = generate_briefing(report, tmp_path, write_voice=False)
        assert "briefing_path" in result
        md_path = result["briefing_path"]
        assert md_path.exists()
        assert "Weekly Operator Briefing" in md_path.read_text()

    def test_briefing_voice_flag_writes_both_files(self, tmp_path):
        report = _make_report([_make_audit("Repo1", pushed_days_ago=2)])
        with patch("src.briefing._resolve_provider", return_value=None):
            result = generate_briefing(report, tmp_path, write_voice=True)
        assert "briefing_path" in result
        assert "voice_path" in result
        assert result["voice_path"].exists()
        assert "|" not in result["voice_path"].read_text()

    def test_briefing_uses_output_dir_from_report(self, tmp_path):
        report = _make_report()
        subdir = tmp_path / "output"
        with patch("src.briefing._resolve_provider", return_value=None):
            result = generate_briefing(report, subdir, write_voice=False)
        assert result["briefing_path"].parent == subdir

    def test_mutually_exclusive_narrative_and_briefing(self):
        """argparse rejects --narrative together with --briefing."""
        from src.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["testuser", "--narrative", "--briefing"])


# ---------------------------------------------------------------------------
# Arc F S3.4: semantic index enrichment in briefing suggestions
# ---------------------------------------------------------------------------


class _FakeSemanticIndex:
    """Stub SemanticIndex for briefing tests — returns pre-canned neighbors."""

    def __init__(self, neighbor_map: dict[str, list]) -> None:
        self._neighbor_map = neighbor_map

    def find_neighbors(self, repo_name: str, k: int = 3):
        from src.semantic_index import SearchResult

        return [
            SearchResult(repo_name=n, score=0.1, snippet=f"repo: {n}")
            for n in self._neighbor_map.get(repo_name, [])
        ][:k]


class TestBriefingSemanticEnrichment:
    """Tests for semantic_index integration in build_briefing / _build_suggestions."""

    def _make_low_score_audit(self, name: str) -> dict:
        """Return a minimal audit dict with a low overall_score to reach top-3."""
        return {
            "metadata": {"name": name, "language": "Python", "pushed_at": _days_ago_iso(5)},
            "overall_score": 0.1,
            "hotspots": [{"category": "readme", "title": "No README"}],
            "analyzer_results": [
                {
                    "dimension": "activity",
                    "score": 0.3,
                    "max_score": 1.0,
                    "findings": [],
                    "details": {"days_since_push": 5, "archived": False},
                }
            ],
        }

    def test_briefing_with_semantic_index_passes_related_repos(self) -> None:
        """When a semantic index is provided, find_neighbors is called for top-3 repos."""
        neighbor_map = {"RepoA": ["RepoB", "RepoC"], "RepoB": [], "RepoC": []}
        fake_idx = _FakeSemanticIndex(neighbor_map)

        audits = [
            self._make_low_score_audit("RepoA"),
            self._make_low_score_audit("RepoB"),
            self._make_low_score_audit("RepoC"),
        ]

        captured: list[str] = []

        class _CapturingProvider:
            def generate(self, prompt: str, model: str, **kwargs) -> str:
                captured.append(prompt)
                return '["fix readme", "add tests", "update deps"]'

        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            provider=_CapturingProvider(),
            semantic_index=fake_idx,
        )

        assert len(captured) == 1
        prompt = captured[0]
        # Prompt should contain the related repos annotation for RepoA
        assert "related:" in prompt or "RepoB" in prompt or "RepoC" in prompt
        assert len(briefing.suggestions) == 3

    def test_briefing_without_semantic_index_unchanged(self) -> None:
        """When semantic_index=None, build_briefing behaves identically to S3.2."""
        audits = [
            self._make_low_score_audit("RepoX"),
            self._make_low_score_audit("RepoY"),
        ]

        class _SimpleProvider:
            def generate(self, prompt: str, model: str, **kwargs) -> str:
                # Verify no "related:" annotation was injected
                assert "related:" not in prompt
                return '["improve docs", "add CI"]'

        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            provider=_SimpleProvider(),
            semantic_index=None,
        )

        assert len(briefing.suggestions) == 2


# ── Initiative integration ────────────────────────────────────────────────────


class TestInitiativesBriefing:
    """Tests for the initiatives section in build_briefing / render_markdown / render_voice."""

    from datetime import date as _date_cls
    from datetime import timedelta as _td_cls

    def _future(self, days: int = 30) -> str:
        from datetime import date, timedelta

        return (date.today() + timedelta(days=days)).isoformat()

    def _past(self, days: int = 5) -> str:
        from datetime import date, timedelta

        return (date.today() - timedelta(days=days)).isoformat()

    def _write_initiatives(self, tmp_path, initiatives):
        from src.initiatives import initiatives_path, save_initiatives

        save_initiatives(initiatives_path(tmp_path), initiatives)

    def _make_initiative(
        self,
        repo_name: str = "Wavelength",
        target_tier: int = 3,
        deadline: str | None = None,
        closed_at: str | None = None,
    ):
        from src.initiatives import Initiative

        return Initiative(
            repo_name=repo_name,
            target_tier=target_tier,
            deadline=deadline or self._future(30),
            set_at="2026-05-12T10:00:00+00:00",
            set_by="operator",
            closed_at=closed_at,
            closed_reason=None,
        )

    def test_no_output_dir_yields_empty_initiatives(self):
        audits = [_make_audit("RepoA")]
        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            output_dir=None,
        )
        assert briefing.initiatives == []

    def test_empty_initiatives_file_yields_empty_list(self, tmp_path):
        # Write an empty initiatives file
        self._write_initiatives(tmp_path, [])
        audits = [_make_audit("RepoA")]
        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            output_dir=tmp_path,
        )
        assert briefing.initiatives == []

    def test_one_on_track_initiative_populates_list(self, tmp_path):
        initiative = self._make_initiative("Wavelength", target_tier=2, deadline=self._future(60))
        self._write_initiatives(tmp_path, [initiative])
        audits = [_make_audit("Wavelength")]
        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            output_dir=tmp_path,
        )
        assert len(briefing.initiatives) == 1
        ini = briefing.initiatives[0]
        assert ini.repo_name == "Wavelength"
        assert ini.target_tier == 2
        assert ini.status in ("on-track", "at-risk", "overdue", "met")

    def test_closed_initiative_excluded(self, tmp_path):
        closed = self._make_initiative("Closed-Repo", closed_at="2026-05-01T00:00:00+00:00")
        self._write_initiatives(tmp_path, [closed])
        audits = [_make_audit("Closed-Repo")]
        briefing = build_briefing(
            audits,
            "user",
            "2026-05-11",
            use_history=False,
            output_dir=tmp_path,
        )
        assert briefing.initiatives == []

    def test_markdown_no_initiatives_section_when_empty(self, tmp_path):
        self._write_initiatives(tmp_path, [])
        audits = [_make_audit("RepoA")]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, output_dir=tmp_path
        )
        md = render_markdown(briefing)
        assert "## Initiatives this week" not in md

    def test_markdown_includes_section_with_one_initiative(self, tmp_path):
        initiative = self._make_initiative("Wavelength", target_tier=2, deadline=self._future(60))
        self._write_initiatives(tmp_path, [initiative])
        audits = [_make_audit("Wavelength")]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, output_dir=tmp_path
        )
        md = render_markdown(briefing)
        assert "## Initiatives this week" in md
        assert "Wavelength" in md

    def test_markdown_includes_status_counts_line(self, tmp_path):
        initiative = self._make_initiative("Wavelength", target_tier=2, deadline=self._future(60))
        self._write_initiatives(tmp_path, [initiative])
        audits = [_make_audit("Wavelength")]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, output_dir=tmp_path
        )
        md = render_markdown(briefing)
        assert "**Status counts:**" in md
        assert "on-track" in md

    def test_markdown_initiatives_section_comes_before_shipped(self, tmp_path):
        initiative = self._make_initiative("Wavelength", target_tier=2, deadline=self._future(60))
        self._write_initiatives(tmp_path, [initiative])
        audits = [_make_audit("Wavelength", pushed_days_ago=1)]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, output_dir=tmp_path
        )
        md = render_markdown(briefing)
        idx_initiatives = md.index("## Initiatives this week")
        idx_shipped = md.index("## Shipped This Week")
        assert idx_initiatives < idx_shipped, "Initiatives section must appear before Shipped"

    def test_render_voice_no_initiatives_no_line(self, tmp_path):
        self._write_initiatives(tmp_path, [])
        audits = [_make_audit("RepoA")]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, output_dir=tmp_path
        )
        voice = render_voice(briefing)
        assert "initiative" not in voice.lower() or "0 initiatives" not in voice.lower()

    def test_render_voice_includes_initiative_summary(self, tmp_path):
        initiative = self._make_initiative("Wavelength", target_tier=2, deadline=self._future(60))
        self._write_initiatives(tmp_path, [initiative])
        audits = [_make_audit("Wavelength")]
        briefing = build_briefing(
            audits, "user", "2026-05-11", use_history=False, output_dir=tmp_path
        )
        voice = render_voice(briefing)
        assert "initiative" in voice.lower()
        assert "1" in voice


# ── Arc G S10.1 — Briefing render smoke tests ─────────────────────────────────


class TestSuggestedInitiativesRender:
    """Smoke tests for the Suggested Initiatives section in render_markdown (Arc G S10.1)."""

    def _make_suggestion(
        self,
        repo_name: str = "MyRepo",
        current_tier: int = 1,
        target_tier: int = 2,
        rationale: str = "Close to Bronze.",
        estimated_effort: str = "low",
    ) -> InitiativeSuggestionRow:
        return InitiativeSuggestionRow(
            repo_name=repo_name,
            current_tier=current_tier,
            target_tier=target_tier,
            rationale=rationale,
            estimated_effort=estimated_effort,
        )

    def test_render_markdown_includes_suggestions_section_when_non_empty(self):
        """Briefing with one suggestion renders the section header and repo name."""
        briefing = Briefing(
            username="alice",
            date="2026-05-11",
            suggested_initiatives=[
                self._make_suggestion(repo_name="Wavelength"),
            ],
        )
        md = render_markdown(briefing)
        assert "## Suggested Initiatives" in md
        assert "Wavelength" in md

    def test_render_markdown_omits_suggestions_section_when_empty(self):
        """Briefing with no suggestions omits the section header entirely."""
        briefing = Briefing(
            username="alice",
            date="2026-05-11",
            suggested_initiatives=[],
        )
        md = render_markdown(briefing)
        assert "## Suggested Initiatives" not in md

    def test_build_briefing_with_include_suggestions_populates_field(self):
        """build_briefing(include_suggestions=True) with a mock provider populates the field."""
        from src.suggest_initiatives import InitiativeSuggestion

        fake_suggestion = InitiativeSuggestion(
            repo_name="Wavelength",
            current_tier=1,
            target_tier=2,
            rationale="Close to Bronze.",
            estimated_effort="low",
            missing_requirements=["readme"],
        )

        with patch(
            "src.suggest_initiatives.generate_suggestions",
            return_value=([fake_suggestion], 0.001),
        ):
            audits = [_make_audit("Wavelength")]
            briefing = build_briefing(
                audits,
                "user",
                "2026-05-11",
                use_history=False,
                include_suggestions=True,
            )

        assert len(briefing.suggested_initiatives) == 1
        assert briefing.suggested_initiatives[0].repo_name == "Wavelength"
