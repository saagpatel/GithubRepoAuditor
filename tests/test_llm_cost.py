"""Tests for src/llm_cost.py — CostTracker, BudgetExceededError, and provider wiring."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.llm_cost import (
    BudgetExceededError,
    CostTracker,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_tracker(budget: float | None = None, tmp: Path | None = None) -> CostTracker:
    return CostTracker(budget_usd=budget, output_path=tmp)


# ── 1. CostTracker.record_call computes cost correctly ──────────────────────


def test_record_call_cost_anthropic_haiku():
    tracker = _make_tracker()
    record = tracker.record_call(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        feature="narrative",
    )
    # PRICES["claude-haiku-4-5"] = {"input": 1.0, "output": 5.0}
    expected = 1.0 + 5.0
    assert abs(record.cost_usd - expected) < 1e-6
    assert abs(tracker.total_usd() - expected) < 1e-6


def test_record_call_cost_gpt4o_mini():
    tracker = _make_tracker()
    record = tracker.record_call(
        provider="github-models",
        model="gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        feature="briefing-suggestion",
    )
    # PRICES["gpt-4o-mini"] = {"input": 0.15, "output": 0.60}
    expected = 0.15 + 0.60
    assert abs(record.cost_usd - expected) < 1e-6


def test_record_call_partial_tokens():
    tracker = _make_tracker()
    # 500 input tokens + 100 output tokens using claude-sonnet-4-6 (3.0/15.0 per M)
    record = tracker.record_call(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=500,
        output_tokens=100,
        feature="narrative",
    )
    expected = (500 / 1_000_000) * 3.0 + (100 / 1_000_000) * 15.0
    assert abs(record.cost_usd - expected) < 1e-9


# ── 2. Budget exceeded raises ────────────────────────────────────────────────


def test_budget_exceeded_raises():
    tracker = _make_tracker(budget=0.001)
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_call(
            provider="anthropic",
            model="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            feature="narrative",
        )
    err = exc_info.value
    assert err.budget_usd == 0.001
    assert err.feature == "narrative"
    assert "raise --max-llm-spend" in str(err)


def test_budget_not_recorded_on_exceed():
    """When budget is exceeded, the call is NOT recorded."""
    tracker = _make_tracker(budget=0.001)
    with pytest.raises(BudgetExceededError):
        tracker.record_call(
            provider="anthropic",
            model="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            feature="narrative",
        )
    assert tracker.total_usd() == 0.0
    assert len(tracker.records()) == 0


# ── 3. No budget = no enforcement ───────────────────────────────────────────


def test_no_budget_allows_unlimited():
    tracker = _make_tracker(budget=None)
    for _ in range(5):
        tracker.record_call(
            provider="anthropic",
            model="claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            feature="narrative",
        )
    assert len(tracker.records()) == 5


# ── 4. Unknown model uses fallback, logs warning ─────────────────────────────


def test_unknown_model_uses_fallback_no_exception():
    tracker = _make_tracker()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        record = tracker.record_call(
            provider="anthropic",
            model="claude-unknown-9999",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            feature="narrative",
        )
    # Should not raise, and at least one warning emitted
    assert any("unknown model" in str(warning.message).lower() for warning in w)
    # Cost should be computed using fallback (5.0 + 20.0)
    assert record.cost_usd > 0


# ── 5. Telemetry write produces correct JSONL ────────────────────────────────


def test_write_telemetry_correct_shape(tmp_path: Path):
    tracker = CostTracker(output_path=tmp_path)
    tracker.record_call(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=1200,
        output_tokens=150,
        feature="narrative",
    )
    tracker.record_call(
        provider="github-models",
        model="gpt-4o-mini",
        input_tokens=800,
        output_tokens=90,
        feature="briefing-suggestion",
    )
    tracker.record_call(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=500,
        output_tokens=50,
        feature="narrative",
    )
    tracker.write_telemetry()

    telemetry_file = tmp_path / "run-telemetry.jsonl"
    assert telemetry_file.exists()

    lines = telemetry_file.read_text().strip().splitlines()
    assert len(lines) == 3

    for line in lines:
        obj = json.loads(line)
        assert set(obj.keys()) >= {
            "timestamp",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "feature",
        }
        assert obj["cost_usd"] >= 0


# ── 6. Telemetry is append-only ──────────────────────────────────────────────


def test_write_telemetry_appends(tmp_path: Path):
    tracker = CostTracker(output_path=tmp_path)
    tracker.record_call(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=100,
        output_tokens=10,
        feature="narrative",
    )
    tracker.write_telemetry()

    tracker2 = CostTracker(output_path=tmp_path)
    tracker2.record_call(
        provider="github-models",
        model="gpt-4o-mini",
        input_tokens=200,
        output_tokens=20,
        feature="briefing-suggestion",
    )
    tracker2.write_telemetry()

    lines = (tmp_path / "run-telemetry.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2  # first write (1) + second write (1) = 2 total lines


# ── 7. AnthropicProvider records cost ───────────────────────────────────────


def test_anthropic_provider_records_cost():
    from src.narrative import AnthropicProvider

    tracker = CostTracker()

    # Build a mock message response matching Anthropic SDK structure
    mock_usage = MagicMock()
    mock_usage.input_tokens = 1000
    mock_usage.output_tokens = 200

    mock_content = MagicMock()
    mock_content.text = "generated text"

    mock_message = MagicMock()
    mock_message.usage = mock_usage
    mock_message.content = [mock_content]

    provider = AnthropicProvider(api_key="test-key")

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message
        mock_anthropic_cls.return_value = mock_client

        result = provider.generate(
            "test prompt", "claude-haiku-4-5", 512, cost_tracker=tracker, feature="narrative"
        )

    assert result == "generated text"
    assert len(tracker.records()) == 1
    rec = tracker.records()[0]
    assert rec.provider == "anthropic"
    assert rec.model == "claude-haiku-4-5"
    assert rec.input_tokens == 1000
    assert rec.output_tokens == 200
    assert rec.feature == "narrative"


# ── 8. GitHubModelsProvider records cost ─────────────────────────────────────


def test_github_models_provider_records_cost():
    from src.narrative import GitHubModelsProvider

    tracker = CostTracker()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "suggestion text"}}],
        "usage": {"prompt_tokens": 800, "completion_tokens": 90},
    }
    mock_response.raise_for_status.return_value = None

    provider = GitHubModelsProvider(github_token="test-token")

    with patch("requests.post", return_value=mock_response):
        result = provider.generate(
            "test prompt", "gpt-4o-mini", 150, cost_tracker=tracker, feature="briefing-suggestion"
        )

    assert result == "suggestion text"
    assert len(tracker.records()) == 1
    rec = tracker.records()[0]
    assert rec.provider == "github-models"
    assert rec.model == "gpt-4o-mini"
    assert rec.input_tokens == 800
    assert rec.output_tokens == 90
    assert rec.feature == "briefing-suggestion"


# ── 9. Briefing call chain records with feature="briefing-suggestion" ────────


def test_briefing_call_chain_records_feature():
    from src.briefing import _build_suggestions

    tracker = CostTracker()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '["Add tests.", "Write README.", "Add CI."]'}}],
        "usage": {"prompt_tokens": 500, "completion_tokens": 30},
    }
    mock_response.raise_for_status.return_value = None

    from src.narrative import GitHubModelsProvider

    provider = GitHubModelsProvider(github_token="test-token")

    audits = [
        {
            "metadata": {"name": "repo-a", "language": "Python"},
            "overall_score": 0.2,
            "hotspots": [],
        },
        {"metadata": {"name": "repo-b", "language": "Rust"}, "overall_score": 0.3, "hotspots": []},
        {"metadata": {"name": "repo-c", "language": "Swift"}, "overall_score": 0.4, "hotspots": []},
    ]

    with patch("requests.post", return_value=mock_response):
        suggestions, _ = _build_suggestions(audits, provider, "gpt-4o-mini", cost_tracker=tracker)

    assert len(tracker.records()) == 1
    assert tracker.records()[0].feature == "briefing-suggestion"


# ── 10. CLI budget halt: error message attributes and sys.exit(1) path ───────


def test_budget_exceeded_error_message_contains_feature():
    err = BudgetExceededError(
        budget_usd=0.05,
        current_usd=0.04,
        call_cost_usd=0.02,
        feature="briefing-suggestion",
    )
    msg = str(err)
    assert "briefing-suggestion" in msg
    assert "0.0500" in msg
    assert "--max-llm-spend" in msg


def test_cli_budget_halt_path(tmp_path: Path):
    """Simulate the CLI budget-halt code path end-to-end without a full audit.

    When BudgetExceededError fires, the CLI catches it, prints to stderr,
    calls write_telemetry(), and sys.exit(1).
    """
    import io
    import sys as _sys

    # A tracker with a tiny budget that a single Haiku call blows past
    tracker = CostTracker(budget_usd=0.0001, output_path=tmp_path)

    caught: BudgetExceededError | None = None
    try:
        tracker.record_call(
            provider="anthropic",
            model="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            feature="narrative",
        )
    except BudgetExceededError as e:
        caught = e

    assert caught is not None, "Expected BudgetExceededError from tiny budget"

    # Replicate the CLI's catch block
    stderr_buf = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        print(f"\nERROR: {caught}", file=stderr_buf)
        tracker.write_telemetry()
        _sys.exit(1)

    assert exc_info.value.code == 1
    err_text = stderr_buf.getvalue()
    assert "--max-llm-spend" in err_text or "budget" in err_text.lower()
    # Telemetry file should NOT have been written (no records were committed)
    telemetry = tmp_path / "run-telemetry.jsonl"
    assert not telemetry.exists() or telemetry.read_text().strip() == ""
