from __future__ import annotations

from src.narrative import _build_prompt, generate_narrative


def _make_report() -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-03-29T12:00:00Z",
        "repos_audited": 50,
        "average_score": 0.57,
        "portfolio_grade": "C",
        "tier_distribution": {"shipped": 10, "functional": 20, "wip": 15, "skeleton": 5},
        "language_distribution": {"TypeScript": 20, "Python": 15, "Rust": 10},
        "summary": {
            "highest_scored": ["RepoA", "RepoB"],
            "lowest_scored": ["RepoX", "RepoY"],
            "most_active": ["RepoA", "RepoC"],
        },
    }


class TestBuildPrompt:
    def test_includes_stats(self):
        prompt = _build_prompt(_make_report())
        assert "50 repositories" in prompt
        assert "0.57" in prompt

    def test_includes_languages(self):
        prompt = _build_prompt(_make_report())
        assert "TypeScript" in prompt
        assert "Python" in prompt

    def test_includes_repos(self):
        prompt = _build_prompt(_make_report())
        assert "RepoA" in prompt
        assert "RepoX" in prompt

    def test_requests_3_paragraphs(self):
        prompt = _build_prompt(_make_report())
        assert "3 paragraphs" in prompt


class TestGenerateNarrative:
    def test_skips_without_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = generate_narrative(_make_report(), tmp_path)
        assert result.get("skipped") is True
        assert "api key" in result.get("reason", "").lower()
