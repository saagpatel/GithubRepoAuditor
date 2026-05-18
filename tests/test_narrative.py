from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.narrative import (
    AnthropicProvider,
    GitHubModelsProvider,
    _build_prompt,
    _resolve_provider,
    generate_narrative,
)


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


class TestAnthropicProvider:
    def test_happy_path(self):
        """AnthropicProvider passes model + prompt and returns text content."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Great portfolio!")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch("anthropic.Anthropic", return_value=mock_client) as mock_cls:
            provider = AnthropicProvider(api_key="test-key")
            result = provider.generate(
                prompt="Analyze this portfolio", model="claude-haiku-test", max_tokens=512
            )

        mock_cls.assert_called_once_with(api_key="test-key")
        mock_client.messages.create.assert_called_once_with(
            model="claude-haiku-test",
            max_tokens=512,
            messages=[{"role": "user", "content": "Analyze this portfolio"}],
        )
        assert result == "Great portfolio!"


class TestGitHubModelsProvider:
    def test_happy_path(self):
        """GitHubModelsProvider POSTs to the right URL with OpenAI-compatible body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Nice repos!"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response) as mock_post:
            provider = GitHubModelsProvider(github_token="ghp_test")
            result = provider.generate(
                prompt="Analyze this", model="gpt-4o-mini", max_tokens=256
            )

        call_kwargs = mock_post.call_args
        url_called = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url", "")
        assert "chat/completions" in url_called

        headers_sent = call_kwargs[1]["headers"]
        assert headers_sent["Authorization"] == "Bearer ghp_test"
        assert headers_sent["Content-Type"] == "application/json"

        body_sent = call_kwargs[1]["json"]
        assert body_sent["model"] == "gpt-4o-mini"
        assert body_sent["max_tokens"] == 256
        assert body_sent["messages"] == [{"role": "user", "content": "Analyze this"}]

        assert result == "Nice repos!"

    def test_403_scope_error(self):
        """GitHubModelsProvider raises PermissionError with clear message on 403."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden: missing models scope"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            provider = GitHubModelsProvider(github_token="ghp_test")
            with pytest.raises(PermissionError) as exc_info:
                provider.generate("Analyze this", "gpt-4o-mini", 256)

        assert "models: read" in str(exc_info.value)
        assert "scope" in str(exc_info.value).lower()

    def test_403_returns_skipped_in_generate_narrative(self, tmp_path):
        """generate_narrative surfaces the 403 scope error as a skipped result."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "missing models scope"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
                result = generate_narrative(
                    _make_report(),
                    tmp_path,
                    provider_name="github-models",
                    github_token="ghp_test",
                )

        assert result.get("skipped") is True
        assert "models: read" in result.get("reason", "")


class TestProviderSelection:
    """Tests for _resolve_provider default-resolution logic."""

    def test_anthropic_key_present_selects_anthropic(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        result = _resolve_provider(None, None, github_token=None)
        assert result is not None
        provider, model = result
        assert isinstance(provider, AnthropicProvider)

    def test_no_anthropic_key_github_token_selects_github_models(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _resolve_provider(None, None, github_token="ghp_test")
        assert result is not None
        provider, model = result
        assert isinstance(provider, GitHubModelsProvider)

    def test_neither_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _resolve_provider(None, None, github_token=None)
        assert result is None

    def test_explicit_anthropic_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _resolve_provider("anthropic", None, github_token=None)

    def test_explicit_github_models_without_token_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="GitHub token"):
            _resolve_provider("github-models", None, github_token=None)

    def test_custom_model_propagates(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _resolve_provider("github-models", "gpt-4o", github_token="ghp_test")
        assert result is not None
        _provider, model = result
        assert model == "gpt-4o"


class TestGenerateNarrativeSkips:
    def test_skips_without_any_credentials(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = generate_narrative(_make_report(), tmp_path, github_token=None)
        assert result.get("skipped") is True
        assert result.get("reason") == "no credentials"

    def test_skips_when_explicit_anthropic_key_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = generate_narrative(
            _make_report(), tmp_path, provider_name="anthropic", github_token=None
        )
        assert result.get("skipped") is True
        assert "ANTHROPIC_API_KEY" in result.get("reason", "")


class TestCLIProviderIntegration:
    """Verify CLI parser wires --narrative-provider and --narrative-model correctly."""

    def test_github_models_provider_flag_routes_to_github_models(self, tmp_path, monkeypatch):
        """End-to-end: explicit --narrative-provider github-models selects GitHubModelsProvider."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "CLI test narrative"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            result = generate_narrative(
                _make_report(),
                tmp_path,
                provider_name="github-models",
                model="gpt-4o-mini",
                github_token="ghp_cli_test",
            )

        assert "narrative_path" in result
        content = result["narrative_path"].read_text()
        assert "CLI test narrative" in content

    def test_cli_parser_accepts_narrative_provider_flag(self):
        """Parser correctly maps --narrative-provider and --narrative-model."""
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["someuser", "--narrative", "--narrative-provider", "github-models", "--narrative-model", "gpt-4o-mini"]
        )
        assert args.narrative is True
        assert args.narrative_provider == "github-models"
        assert args.narrative_model == "gpt-4o-mini"

    def test_cli_parser_narrative_provider_defaults_to_none(self):
        """narrative_provider is None by default (auto-detect)."""
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["someuser"])
        assert args.narrative_provider is None
        assert args.narrative_model is None
