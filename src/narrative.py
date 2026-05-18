"""AI portfolio narrative — generates human-readable analysis using Claude or GitHub Models."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.llm_cost import CostTracker

# Allow override via env var for testing / proxies
GITHUB_MODELS_BASE_URL = os.environ.get(
    "GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"
)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_GITHUB_MODELS_MODEL = "gpt-4o-mini"


# ── Provider protocol ────────────────────────────────────────────────────────


class NarrativeProvider(Protocol):
    def generate(self, prompt: str, model: str, max_tokens: int) -> str: ...


# ── Anthropic provider ───────────────────────────────────────────────────────


class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        *,
        cost_tracker: CostTracker | None = None,
        feature: str = "narrative",
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if cost_tracker is not None:
            usage = message.usage
            cost_tracker.record_call(
                provider="anthropic",
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                feature=feature,
            )
        return message.content[0].text


# ── GitHub Models provider ───────────────────────────────────────────────────


class GitHubModelsProvider:
    def __init__(self, github_token: str) -> None:
        self._github_token = github_token

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        *,
        cost_tracker: CostTracker | None = None,
        feature: str = "narrative",
    ) -> str:
        import requests

        url = f"{GITHUB_MODELS_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._github_token}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }

        response = requests.post(url, json=body, headers=headers, timeout=30)

        if response.status_code == 403:
            text = response.text or ""
            if "models" in text.lower() or "scope" in text.lower() or response.status_code == 403:
                raise PermissionError(
                    "GitHub Models requires PAT scope `models: read` — "
                    "regenerate your token with this scope enabled."
                )
            response.raise_for_status()

        response.raise_for_status()
        data = response.json()
        if cost_tracker is not None:
            usage = data.get("usage", {})
            cost_tracker.record_call(
                provider="github-models",
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                feature=feature,
            )
        return data["choices"][0]["message"]["content"]


# ── Provider selection ───────────────────────────────────────────────────────


def _resolve_provider(
    provider_name: str | None,
    model: str | None,
    github_token: str | None,
) -> tuple[NarrativeProvider, str] | None:
    """
    Resolve the provider and model to use.

    Returns (provider, model) or None if narrative should be skipped.
    Raises ValueError if an explicit provider is requested but credentials are missing.
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    # Auto-detect when no provider is explicitly specified
    if provider_name is None:
        if anthropic_key:
            provider_name = "anthropic"
        elif github_token:
            provider_name = "github-models"
        else:
            return None  # skip gracefully

    if provider_name == "anthropic":
        if not anthropic_key:
            raise ValueError(
                "--narrative-provider anthropic requested but ANTHROPIC_API_KEY is not set."
            )
        resolved_model = model or DEFAULT_ANTHROPIC_MODEL
        return AnthropicProvider(anthropic_key), resolved_model

    if provider_name == "github-models":
        if not github_token:
            raise ValueError(
                "--narrative-provider github-models requested but no GitHub token is available. "
                "Set GITHUB_TOKEN or pass --token."
            )
        resolved_model = model or DEFAULT_GITHUB_MODELS_MODEL
        return GitHubModelsProvider(github_token), resolved_model

    raise ValueError(f"Unknown narrative provider: {provider_name!r}")


# ── Prompt builder ───────────────────────────────────────────────────────────


def _build_prompt(report_data: dict) -> str:
    """Build a focused prompt from audit data."""
    tiers = report_data.get("tier_distribution", {})
    lang_dist = report_data.get("language_distribution", {})
    summary = report_data.get("summary", {})
    top_langs = list(lang_dist.items())[:8]

    return f"""Analyze this developer's GitHub portfolio and write a concise 3-paragraph narrative.

Portfolio stats:
- {report_data.get("repos_audited", 0)} repositories audited
- Average completeness score: {report_data.get("average_score", 0):.2f} / 1.00
- Portfolio grade: {report_data.get("portfolio_grade", "?")}
- Tier distribution: {json.dumps(tiers)}
- Top languages: {", ".join(f"{language} ({count} repos)" for language, count in top_langs)}
- Highest scored: {", ".join(summary.get("highest_scored", [])[:5])}
- Lowest scored: {", ".join(summary.get("lowest_scored", [])[:5])}
- Most active: {", ".join(summary.get("most_active", [])[:5])}

Write exactly 3 paragraphs:
1. Overall portfolio assessment — strengths and character
2. Patterns you notice — tech preferences, completion habits, areas of focus
3. Specific recommendations — what to prioritize next

Be direct, specific, and actionable. Reference repo names where relevant."""


# ── Public entry point ───────────────────────────────────────────────────────


def generate_narrative(
    report_data: dict,
    output_dir: Path,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    github_token: str | None = None,
    cost_tracker: CostTracker | None = None,
) -> dict:
    """Generate AI narrative. Returns {narrative_path} or {skipped, reason}."""
    try:
        result = _resolve_provider(provider_name, model, github_token)
    except ValueError as exc:
        print(f"  Narrative error: {exc}", file=sys.stderr)
        return {"skipped": True, "reason": str(exc)}

    if result is None:
        print("  No narrative credentials available. Skipping narrative.", file=sys.stderr)
        return {"skipped": True, "reason": "no credentials"}

    provider, resolved_model = result
    prompt = _build_prompt(report_data)
    username = report_data.get("username", "unknown")
    date = report_data.get("generated_at", "")[:10] or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d"
    )

    try:
        narrative_text = provider.generate(
            prompt, resolved_model, max_tokens=1024, cost_tracker=cost_tracker, feature="narrative"
        )
    except PermissionError as exc:
        print(f"  Narrative generation failed: {exc}", file=sys.stderr)
        return {"skipped": True, "reason": str(exc)}
    except Exception as exc:
        print(f"  Narrative generation failed: {exc}", file=sys.stderr)
        return {"skipped": True, "reason": str(exc)}

    lines = [
        f"# Portfolio Narrative: {username}",
        "",
        f"*AI-generated analysis from {date} audit data.*",
        "",
        narrative_text,
        "",
        "---",
        "*Generated by [GithubRepoAuditor](https://github.com/saagpatel/GithubRepoAuditor) + Claude*",
        "",
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"narrative-{date}.md"
    path.write_text("\n".join(lines))
    print(f"  Narrative generated: {path}", file=sys.stderr)
    return {"narrative_path": path}
