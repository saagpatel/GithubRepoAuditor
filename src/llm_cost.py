"""LLM cost tracking and optional budget gate for audit runs.

Wraps all LLM call sites (narrative, briefing) to record per-call spend and
optionally halt runs that would exceed a configured USD budget.

Usage::

    tracker = CostTracker(budget_usd=0.50, output_path=Path("output"))
    # pass tracker to provider.generate(...) — recorded automatically

Telemetry is appended to ``output/run-telemetry.jsonl`` (one JSON object per
line).  The file is append-only; rotation and cleanup are the operator's
responsibility.
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-million-token prices (USD).
# NOTE: These are placeholder values — real rates change frequently.
#       Update this dict when Anthropic/OpenAI publish new pricing.
#       Operators can supply a custom tracker with overridden prices if needed.
# ---------------------------------------------------------------------------
PRICES: dict[str, dict[str, float]] = {
    # Anthropic models (input / output per 1M tokens)
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    # GitHub Models / OpenAI-compatible (free-tier proxy — prices reflect underlying model)
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

# Fallback rate for unknown models (conservative estimate).
_UNKNOWN_PRICE: dict[str, float] = {"input": 5.0, "output": 20.0}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a call.  Logs a warning for unknown models."""
    price = PRICES.get(model)
    if price is None:
        warnings.warn(
            f"llm_cost: unknown model {model!r} — using fallback rate "
            f"(${_UNKNOWN_PRICE['input']:.2f}/${_UNKNOWN_PRICE['output']:.2f} per 1M tokens). "
            "Update PRICES in src/llm_cost.py.",
            stacklevel=3,
        )
        logger.warning(
            "llm_cost: unknown model %r — using fallback rate. Update PRICES in src/llm_cost.py.",
            model,
        )
        price = _UNKNOWN_PRICE

    input_cost = (input_tokens / 1_000_000) * price["input"]
    output_cost = (output_tokens / 1_000_000) * price["output"]
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LLMCallRecord:
    """Immutable record for a single LLM API call."""

    timestamp: str  # ISO8601 UTC
    provider: str  # "anthropic" | "github-models"
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    feature: str  # "narrative" | "briefing-suggestion" | …

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "feature": self.feature,
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """Raised when an LLM call would push total_usd past the configured budget.

    Attributes
    ----------
    budget_usd:   The configured limit.
    current_usd:  The accumulated spend *before* this call.
    call_cost_usd: The cost of the call that triggered the limit.
    feature:      The feature name that triggered the limit.
    """

    def __init__(
        self,
        budget_usd: float,
        current_usd: float,
        call_cost_usd: float,
        feature: str,
    ) -> None:
        self.budget_usd = budget_usd
        self.current_usd = current_usd
        self.call_cost_usd = call_cost_usd
        self.feature = feature
        total = current_usd + call_cost_usd
        super().__init__(
            f"LLM budget of ${budget_usd:.4f} exceeded by feature {feature!r} at "
            f"${total:.4f} (accumulated ${current_usd:.4f} + call ${call_cost_usd:.4f}) — "
            f"raise --max-llm-spend or omit --briefing/--narrative"
        )


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class CostTracker:
    """Accumulates LLM call costs for a single audit run.

    Thread-safe. Provider classes wrap their ``generate()`` in a call to
    :meth:`record_call` after each successful API response.

    Parameters
    ----------
    budget_usd:
        Optional hard cap in USD.  When a call would push the running total
        past this value, :class:`BudgetExceededError` is raised *before* the
        call happens (the call is not charged).  ``None`` disables enforcement.
    output_path:
        Directory where ``run-telemetry.jsonl`` will be written.  If ``None``,
        :meth:`write_telemetry` is a no-op (records are still accumulated in
        memory for the caller to inspect).
    """

    def __init__(
        self,
        *,
        budget_usd: float | None = None,
        output_path: Path | None = None,
    ) -> None:
        self._budget_usd = budget_usd
        self._output_path = output_path
        self._records: list[LLMCallRecord] = []
        self._total_usd: float = 0.0
        self._lock = Lock()

    # ── Core accumulation ────────────────────────────────────────────────────

    def record_call(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        feature: str,
    ) -> LLMCallRecord:
        """Add a call record.  Returns the :class:`LLMCallRecord`.

        Raises :class:`BudgetExceededError` if the budget would be exceeded.
        """
        cost = _compute_cost(model, input_tokens, output_tokens)

        with self._lock:
            if self._budget_usd is not None and (self._total_usd + cost) > self._budget_usd:
                raise BudgetExceededError(
                    budget_usd=self._budget_usd,
                    current_usd=self._total_usd,
                    call_cost_usd=cost,
                    feature=feature,
                )

            record = LLMCallRecord(
                timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=round(cost, 8),
                feature=feature,
            )
            self._records.append(record)
            self._total_usd += cost

        return record

    # ── Accessors ────────────────────────────────────────────────────────────

    def total_usd(self) -> float:
        """Return the accumulated spend in USD (thread-safe snapshot)."""
        with self._lock:
            return self._total_usd

    def records(self) -> list[LLMCallRecord]:
        """Return a snapshot of all recorded calls."""
        with self._lock:
            return list(self._records)

    # ── Telemetry persistence ────────────────────────────────────────────────

    def write_telemetry(self) -> None:
        """Append all accumulated records to ``output/run-telemetry.jsonl``.

        Append-only — never truncates the existing file.  Each record is
        serialised as one JSON object per line.  Write failures are logged
        and silently swallowed so they never crash an audit run.
        """
        if self._output_path is None:
            logger.debug("llm_cost: no output_path configured, skipping telemetry write")
            return

        with self._lock:
            records_snapshot = list(self._records)

        if not records_snapshot:
            return

        telemetry_file = self._output_path / "run-telemetry.jsonl"
        try:
            self._output_path.mkdir(parents=True, exist_ok=True)
            with telemetry_file.open("a", encoding="utf-8") as fh:
                for record in records_snapshot:
                    fh.write(json.dumps(record.to_dict()) + "\n")
            logger.debug(
                "llm_cost: wrote %d telemetry record(s) to %s",
                len(records_snapshot),
                telemetry_file,
            )
        except Exception as exc:
            logger.warning("llm_cost: failed to write telemetry to %s: %s", telemetry_file, exc)
