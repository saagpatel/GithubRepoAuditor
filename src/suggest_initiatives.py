"""LLM-ranked initiative suggestions — Arc G Sprint 8.4.

Walk the portfolio, narrow repos that are close to qualifying for their next
maturity tier, ask an LLM to rank them by leverage, and return structured
:class:`InitiativeSuggestion` objects.

Deterministic fallback (rank by fewest missing requirements) is used
automatically when no LLM provider is available.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.narrative import _resolve_provider

logger = logging.getLogger(__name__)

# ── In-process suggestion cache ───────────────────────────────────────────────

# Maximum number of entries retained in _suggestion_cache (in-memory and on-disk).
_CACHE_MAX_SIZE = 100

# In-process cache for generate_suggestions results, keyed by caller-supplied cache_key.
# Caller is responsible for picking a key that captures all relevant inputs
# (e.g. portfolio-truth generated_at + target_tier).
# OrderedDict for LRU-style eviction (insertion-order, FIFO eviction on overflow).
_suggestion_cache: OrderedDict[str, tuple[list["InitiativeSuggestion"], float]] = OrderedDict()

# Track which output_dir paths have already been loaded from disk (lazy-load guard).
_loaded_from_disk: set[Path] = set()


# ── Persistent cache helpers ──────────────────────────────────────────────────


def suggestion_cache_path(output_dir: Path) -> Path:
    """Return the path to the persistent suggestion cache file."""
    return output_dir / "suggestion-cache.json"


def load_suggestion_cache(
    path: Path,
) -> OrderedDict[str, tuple[list["InitiativeSuggestion"], float]]:
    """Read the versioned JSON cache file.

    Missing file or malformed JSON → returns an empty OrderedDict and logs a
    warning for the malformed-JSON case.  Hydrates :class:`InitiativeSuggestion`
    instances from stored dicts.
    """
    if not path.exists():
        return OrderedDict()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("suggest_initiatives: could not load cache %s: %s", path, exc)
        return OrderedDict()

    if not isinstance(data, dict) or data.get("version") != 1:
        logger.warning("suggest_initiatives: unrecognised cache schema in %s — ignoring", path)
        return OrderedDict()

    result: OrderedDict[str, tuple[list[InitiativeSuggestion], float]] = OrderedDict()
    for entry in data.get("entries", []):
        try:
            key = str(entry["key"])
            cost = float(entry["cost"])
            suggestions = [InitiativeSuggestion.from_dict(s) for s in entry["suggestions"]]
            result[key] = (suggestions, cost)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("suggest_initiatives: skipping malformed cache entry: %s", exc)

    return result


def save_suggestion_cache(
    path: Path,
    cache: OrderedDict[str, tuple[list["InitiativeSuggestion"], float]],
) -> None:
    """Persist *cache* to *path* atomically using a tmp+rename pattern.

    Only the most recent :data:`_CACHE_MAX_SIZE` entries (by insertion order) are
    written.  Schema: ``{"version": 1, "entries": [...]}``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Cap to most recent _CACHE_MAX_SIZE entries
    entries_to_write = list(cache.items())[-_CACHE_MAX_SIZE:]

    serialisable = {
        "version": 1,
        "entries": [
            {
                "key": key,
                "cost": cost,
                "suggestions": [s.to_dict() for s in suggestions],
            }
            for key, (suggestions, cost) in entries_to_write
        ],
    }

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".suggestion_cache_tmp_",
            suffix=".json",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(serialisable, tmp, indent=2)
        tmp_path.replace(path)
    except OSError as exc:
        logger.error("suggest_initiatives: atomic cache write failed for %s: %s", path, exc)
        raise


# ── Dismissed suggestions persistence ────────────────────────────────────────


@dataclass(frozen=True)
class DismissedSuggestion:
    """A repo that has been dismissed from LLM-suggested initiatives."""

    repo_name: str
    reason: str  # operator-provided text, default ""
    dismissed_at: str  # ISO timestamp
    dismissed_by: str  # operator_identity() from src.initiatives

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "reason": self.reason,
            "dismissed_at": self.dismissed_at,
            "dismissed_by": self.dismissed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DismissedSuggestion":
        return cls(
            repo_name=str(data.get("repo_name", "")),
            reason=str(data.get("reason", "")),
            dismissed_at=str(data.get("dismissed_at", "")),
            dismissed_by=str(data.get("dismissed_by", "")),
        )


def dismissed_path(output_dir: Path) -> Path:
    """Return output_dir / 'dismissed-suggestions.json'."""
    return output_dir / "dismissed-suggestions.json"


def load_dismissed(path: Path) -> list[DismissedSuggestion]:
    """Read versioned JSON. Missing/malformed → empty list (log warning)."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("suggest_initiatives: could not load dismissed file %s: %s", path, exc)
        return []

    if not isinstance(data, dict) or data.get("version") != 1:
        logger.warning("suggest_initiatives: unrecognised dismissed schema in %s — ignoring", path)
        return []

    result: list[DismissedSuggestion] = []
    for entry in data.get("items", []):
        try:
            result.append(DismissedSuggestion.from_dict(entry))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("suggest_initiatives: skipping malformed dismissed entry: %s", exc)

    return result


def save_dismissed(path: Path, items: list[DismissedSuggestion]) -> None:
    """Atomic tmp+rename write. Schema {"version": 1, "items": [...]}."""
    path.parent.mkdir(parents=True, exist_ok=True)

    serialisable = {
        "version": 1,
        "items": [d.to_dict() for d in items],
    }

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".dismissed_suggestions_tmp_",
            suffix=".json",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(serialisable, tmp, indent=2)
        tmp_path.replace(path)
    except OSError as exc:
        logger.error("suggest_initiatives: atomic dismissed write failed for %s: %s", path, exc)
        raise


def dismiss_suggestion_record(path: Path, repo_name: str, reason: str = "") -> DismissedSuggestion:
    """Add or replace by repo_name (idempotent). Returns the recorded entry.

    Validates repo_name is non-empty; raises ValueError if blank.
    On re-dismissal: dismissed_at is updated to the current timestamp.
    """
    if not repo_name.strip():
        raise ValueError("repo_name must not be blank")

    from datetime import datetime, timezone

    from src.initiatives import operator_identity

    items = load_dismissed(path)
    # Remove any existing entry for this repo_name
    items = [d for d in items if d.repo_name != repo_name]

    entry = DismissedSuggestion(
        repo_name=repo_name,
        reason=reason,
        dismissed_at=datetime.now(timezone.utc).isoformat(),
        dismissed_by=operator_identity(),
    )
    items.append(entry)
    save_dismissed(path, items)
    return entry


def undo_dismiss(path: Path, repo_name: str) -> bool:
    """Remove entry for repo_name. Return True if removed, False if not present."""
    items = load_dismissed(path)
    new_items = [d for d in items if d.repo_name != repo_name]
    if len(new_items) == len(items):
        return False
    save_dismissed(path, new_items)
    return True


def clear_suggestion_cache(path: Path | None = None) -> None:
    """Drop all in-memory cached suggestions.

    If *path* is provided and the file exists, delete it as well.  Also clears
    the ``_loaded_from_disk`` tracking set so a subsequent call with the same
    *output_dir* will re-load from disk (or start fresh).
    """
    _suggestion_cache.clear()
    _loaded_from_disk.clear()
    if path is not None and path.exists():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("suggest_initiatives: could not delete cache %s: %s", path, exc)


# ── Public dataclass ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InitiativeSuggestion:
    repo_name: str
    current_tier: int
    target_tier: int
    missing_requirements: list[str]
    rationale: str  # LLM-provided (or fallback message)
    estimated_effort: str  # "small" | "medium" | "large" | "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {
            "repo_name": self.repo_name,
            "current_tier": self.current_tier,
            "target_tier": self.target_tier,
            "missing_requirements": list(self.missing_requirements),
            "rationale": self.rationale,
            "estimated_effort": self.estimated_effort,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InitiativeSuggestion":
        """Hydrate from a JSON-compatible dict.  Missing keys default safely."""
        return cls(
            repo_name=str(data.get("repo_name", "")),
            current_tier=int(data.get("current_tier", 0)),
            target_tier=int(data.get("target_tier", 0)),
            missing_requirements=list(data.get("missing_requirements", [])),
            rationale=str(data.get("rationale", "")),
            estimated_effort=str(data.get("estimated_effort", "unknown")),
        )


# ── Candidate selection ───────────────────────────────────────────────────────


def narrow_candidates(
    projects: list[dict],
    target_tier: int | None = None,
    max_missing: int = 3,
    dismissed: set[str] | None = None,
) -> list[tuple[dict, int, "TierGap"]]:  # noqa: F821
    """Return (repo, target_tier, gap) tuples for repos close to their next tier.

    Filters:
    - Skip repos with ``compute_tier == 0`` (no git history).
    - Skip repos already at Platinum (tier 4) — no next tier exists.
    - If *target_tier* is specified, use it for all repos; otherwise use
      ``current + 1`` per repo.
    - Skip if *target_tier* > 4.
    - Skip if repo already qualifies for the target (no missing requirements).
    - Skip if ``len(missing_requirements) > max_missing`` (too far away).
    - If *dismissed* is provided, skip repos whose ``identity.display_name``
      is in the set.  Pass ``None`` (default) to disable filtering.
    """
    from src.maturity_tiers import TierGap, compute_tier, tier_gap

    candidates: list[tuple[dict, int, TierGap]] = []

    for repo in projects:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or ""
        )
        if dismissed is not None and name in dismissed:
            continue

        current = compute_tier(repo)
        # Skip no-git repos and repos already at max tier
        if current == 0 or current >= 4:
            continue

        t = target_tier if target_tier is not None else current + 1
        if t > 4:
            continue

        gap = tier_gap(repo, t)
        # Skip if already qualifies
        if not gap.missing_requirements:
            continue
        # Skip if too many missing
        if len(gap.missing_requirements) > max_missing:
            continue

        candidates.append((repo, t, gap))

    return candidates


# ── Prompt builder ────────────────────────────────────────────────────────────


def build_suggest_prompt(
    candidates: list[tuple[dict, int, "TierGap"]],  # noqa: F821
) -> str:
    """Build a prompt asking the LLM to rank candidates by leverage.

    Includes per-candidate context (name, tiers, missing requirements, and a
    1-line status blurb).  Asks the LLM to return a JSON array sorted by
    descending leverage, capped at 8 entries.
    """
    from src.maturity_tiers import tier_name

    blurbs: list[str] = []
    for repo, target, gap in candidates:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or "unknown"
        )
        current = gap.current_tier
        derived = repo.get("derived", {})
        activity_status = derived.get("activity_status", "unknown")
        context_quality = derived.get("context_quality", "unknown")
        missing_str = "; ".join(gap.missing_requirements)

        blurbs.append(
            f"- repo_name: {name}\n"
            f"  current_tier: {current} ({tier_name(current)})\n"
            f"  target_tier: {target} ({tier_name(target)})\n"
            f"  missing_requirements: [{missing_str}]\n"
            f"  activity_status: {activity_status}\n"
            f"  context_quality: {context_quality}"
        )

    candidates_block = "\n".join(blurbs)

    return (
        "You are a portfolio advisor for a software developer with many GitHub repos.\n"
        "Below is a list of repos that are close to qualifying for a higher maturity tier.\n"
        "Each entry shows the repo name, current and target tiers, and the missing requirements.\n\n"
        "Rank these repos by LEVERAGE — which ones would benefit MOST from the small remaining "
        "effort to reach the next tier? Consider factors like: how few requirements remain, "
        "how active the repo is, how much context quality matters, and which tier upgrades are "
        "most impactful.\n\n"
        "Return a JSON array of objects (up to 8 entries, sorted by descending leverage):\n"
        '[\n  {"repo_name": "...", "rationale": "1-sentence why this is high-leverage",'
        ' "estimated_effort": "small|medium|large"},\n  ...\n]\n\n'
        "IMPORTANT: Return ONLY the JSON array, no other text.\n\n"
        "Candidates:\n"
        f"{candidates_block}\n\n"
        "JSON response:"
    )


# ── Response parser ───────────────────────────────────────────────────────────


def parse_suggest_response(
    raw_response: str,
    candidates: list[tuple[dict, int, "TierGap"]],  # noqa: F821
) -> list[InitiativeSuggestion]:
    """Parse the LLM JSON response into :class:`InitiativeSuggestion` objects.

    Uses brace-scan (mirrors plan_campaign.py pattern).  Cross-references
    repo_name against the known candidates — LLM-invented names are dropped.
    The current_tier, target_tier, and missing_requirements are taken from the
    candidate tuple, NOT from the LLM output.
    """
    # Build a lookup from repo_name → (repo, target, gap)
    candidate_map: dict[str, tuple[dict, int, "TierGap"]] = {}  # noqa: F821
    for repo, target, gap in candidates:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or "unknown"
        )
        candidate_map[name] = (repo, target, gap)

    text = raw_response.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Find the first [ ... ] array block
    start = text.find("[")
    end = text.rfind("]") + 1
    if start < 0 or end <= start:
        logger.warning("suggest_initiatives: no JSON array found in provider response")
        return []

    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        logger.warning("suggest_initiatives: failed to parse JSON response: %s", exc)
        return []

    if not isinstance(parsed, list):
        logger.warning("suggest_initiatives: expected JSON array, got %s", type(parsed))
        return []

    results: list[InitiativeSuggestion] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        repo_name = str(entry.get("repo_name") or "")
        if repo_name not in candidate_map:
            logger.debug(
                "suggest_initiatives: unknown repo_name %r in LLM response — skipping", repo_name
            )
            continue

        _repo, target, gap = candidate_map[repo_name]
        rationale = str(entry.get("rationale") or "")
        raw_effort = str(entry.get("estimated_effort") or "unknown").lower()
        effort = raw_effort if raw_effort in ("small", "medium", "large") else "unknown"

        results.append(
            InitiativeSuggestion(
                repo_name=repo_name,
                current_tier=gap.current_tier,
                target_tier=target,
                missing_requirements=list(gap.missing_requirements),
                rationale=rationale,
                estimated_effort=effort,
            )
        )

    return results


# ── Deterministic fallback ────────────────────────────────────────────────────


def _deterministic_rank(
    candidates: list[tuple[dict, int, "TierGap"]],  # noqa: F821
) -> list[InitiativeSuggestion]:
    """Rank candidates by fewest missing requirements, then by highest current tier.

    Used when no LLM provider is available.
    """
    # Sort: ascending by missing count, descending by current tier
    sorted_candidates = sorted(
        candidates,
        key=lambda t: (len(t[2].missing_requirements), -t[2].current_tier),
    )

    results: list[InitiativeSuggestion] = []
    for repo, target, gap in sorted_candidates[:8]:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or "unknown"
        )
        results.append(
            InitiativeSuggestion(
                repo_name=name,
                current_tier=gap.current_tier,
                target_tier=target,
                missing_requirements=list(gap.missing_requirements),
                rationale="(no LLM available; ranked by fewest missing requirements)",
                estimated_effort="unknown",
            )
        )

    return results


# ── Deadline helpers ─────────────────────────────────────────────────────────

_EFFORT_DAYS: dict[str, int] = {"small": 14, "medium": 30, "large": 60}
_DEFAULT_DEADLINE_DAYS = 30  # for "unknown" or any other value


def default_deadline_for_effort(effort: str, today: date | None = None) -> str:
    """Map estimated_effort string to a deadline in YYYY-MM-DD form.

    small  → today + 14 days
    medium → today + 30 days
    large  → today + 60 days
    unknown/anything else → today + 30 days
    """
    if today is None:
        today = date.today()
    days = (
        _EFFORT_DAYS.get(effort.lower(), _DEFAULT_DEADLINE_DAYS)
        if effort
        else _DEFAULT_DEADLINE_DAYS
    )
    return (today + timedelta(days=days)).isoformat()


def accept_suggestion(
    repo_name: str,
    projects: list[dict],
    output_dir: Path,
    deadline: str | None = None,
    target_tier: int | None = None,
) -> "Initiative":  # noqa: F821
    """Convert a suggestion into an initiative.

    This is the single backend entry point for both CLI and web routes.

    Steps
    -----
    1. Find project in ``projects`` by ``identity.display_name == repo_name``.
    2. Validate current tier (must be 1-3).
    3. Derive or validate ``target_tier``.
    4. Derive ``deadline`` from suggestion effort when not supplied.
    5. Validate ``deadline`` is a future YYYY-MM-DD string.
    6. Build, persist, and return the :class:`Initiative`.
    """
    from datetime import datetime, timezone

    from src.initiatives import Initiative, initiatives_path, operator_identity, upsert_initiative
    from src.maturity_tiers import compute_tier

    # 1. Find project
    project: dict | None = None
    for p in projects:
        if p.get("identity", {}).get("display_name") == repo_name:
            project = p
            break
    if project is None:
        raise ValueError(f"repo '{repo_name}' not found in portfolio truth")

    # 2. Validate current tier
    current = compute_tier(project)
    if current == 0:
        raise ValueError(f"repo '{repo_name}' has no git (current_tier=0); cannot set initiative")
    if current >= 4:
        raise ValueError(f"repo '{repo_name}' is already at Platinum (tier 4)")

    # 3. Derive / validate target_tier
    if target_tier is None:
        target = current + 1
    else:
        if target_tier <= current:
            raise ValueError(
                f"target_tier {target_tier} must be greater than current tier {current}"
            )
        if target_tier not in {2, 3, 4}:
            raise ValueError(f"target_tier must be 2, 3, or 4; got {target_tier}")
        target = target_tier

    # 4. Derive deadline when not supplied
    if deadline is None:
        effort = "medium"  # default
        suggestions, _ = generate_suggestions(
            projects, target_tier=target, force_deterministic=True
        )
        for s in suggestions:
            if s.repo_name == repo_name:
                effort = s.estimated_effort
                break
        deadline = default_deadline_for_effort(effort)

    # 5. Validate deadline format
    try:
        deadline_date = date.fromisoformat(deadline)
    except ValueError:
        raise ValueError(f"deadline must be YYYY-MM-DD, got: {deadline!r}")

    # 6. Validate deadline is not in the past
    if deadline_date < date.today():
        raise ValueError(
            f"deadline {deadline} must be in the future (today is {date.today().isoformat()})"
        )

    # 7. Build initiative
    initiative = Initiative(
        repo_name=repo_name,
        target_tier=target,
        deadline=deadline,
        set_at=datetime.now(timezone.utc).isoformat(),
        set_by=operator_identity(),
        closed_at=None,
        closed_reason=None,
    )

    # 8. Persist
    upsert_initiative(initiatives_path(output_dir), initiative)

    # 9. Return
    return initiative


# ── Top-level entrypoint ──────────────────────────────────────────────────────


def generate_suggestions(
    projects: list[dict],
    target_tier: int | None = None,
    budget_usd: float = 0.10,
    max_missing: int = 3,
    cache_key: str | None = None,
    force_deterministic: bool = False,
    output_dir: Path | None = None,
) -> tuple[list[InitiativeSuggestion], float]:
    """Generate LLM-ranked initiative suggestions for the portfolio.

    Parameters
    ----------
    projects:
        List of repo dicts from portfolio-truth.
    target_tier:
        If set, filter to repos targeting this specific tier.
        If ``None``, each repo targets its own ``current_tier + 1``.
    budget_usd:
        Hard cap on LLM spend.  Default $0.10.
    max_missing:
        Maximum number of missing requirements to include a repo as a candidate.
    cache_key:
        If provided, results are cached in-process under this key.  Subsequent
        calls with the same key skip the LLM entirely.  Caller is responsible for
        choosing a key that captures all relevant inputs (e.g.
        ``f"{generated_at}|target={target_tier}"``).  Pass ``None`` (default) to
        disable caching.
    force_deterministic:
        If ``True``, skip the LLM call entirely and use the deterministic ranking
        (fewest missing requirements).  Cost is always 0.0.  Never raises.
        Useful for deadline derivation in :func:`accept_suggestion`.
    output_dir:
        When provided, the persistent cache at
        ``output_dir / "suggestion-cache.json"`` is lazily loaded on the first
        call for that directory.  New results are also written back to disk.
        Callers that omit this parameter see no behaviour change (opt-in).

    Returns
    -------
    (suggestions, actual_cost_usd)
        ``actual_cost_usd`` is 0.0 when the deterministic fallback is used.
    """
    import os

    from src.llm_cost import BudgetExceededError, CostTracker

    # ── Lazy disk load (first call per output_dir) ────────────────────────────
    if output_dir is not None and output_dir not in _loaded_from_disk:
        disk_cache = load_suggestion_cache(suggestion_cache_path(output_dir))
        for k, v in disk_cache.items():
            _suggestion_cache[k] = v
        _loaded_from_disk.add(output_dir)

    # ── Load dismissed set when output_dir is provided ───────────────────────
    _dismissed_set: set[str] | None = None
    if output_dir is not None:
        dismissed_items = load_dismissed(dismissed_path(output_dir))
        _dismissed_set = {d.repo_name for d in dismissed_items} if dismissed_items else None

    # ── Cache lookup ──────────────────────────────────────────────────────────
    if cache_key is not None and cache_key in _suggestion_cache:
        _suggestion_cache.move_to_end(cache_key)  # mark as recently used
        return _suggestion_cache[cache_key]

    # ── Deterministic fast-path (no LLM, no CostTracker) ─────────────────────
    if force_deterministic:
        candidates = narrow_candidates(
            projects, target_tier=target_tier, max_missing=max_missing, dismissed=_dismissed_set
        )
        if not candidates:
            return [], 0.0
        suggestions = _deterministic_rank(candidates)
        if cache_key is not None:
            _suggestion_cache[cache_key] = (suggestions, 0.0)
            _suggestion_cache.move_to_end(cache_key)
            # Bounded eviction
            while len(_suggestion_cache) > _CACHE_MAX_SIZE:
                _suggestion_cache.popitem(last=False)
            if output_dir is not None:
                save_suggestion_cache(suggestion_cache_path(output_dir), _suggestion_cache)
        return suggestions, 0.0

    candidates = narrow_candidates(
        projects, target_tier=target_tier, max_missing=max_missing, dismissed=_dismissed_set
    )
    if not candidates:
        return [], 0.0

    # Resolve LLM provider (module-level import so tests can patch src.suggest_initiatives._resolve_provider)
    github_token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    provider_result = _resolve_provider(None, None, github_token)

    if provider_result is None:
        logger.warning(
            "suggest_initiatives: no LLM provider available; using deterministic fallback"
        )
        suggestions = _deterministic_rank(candidates)
        if cache_key is not None:
            _suggestion_cache[cache_key] = (suggestions, 0.0)
            _suggestion_cache.move_to_end(cache_key)
            while len(_suggestion_cache) > _CACHE_MAX_SIZE:
                _suggestion_cache.popitem(last=False)
            if output_dir is not None:
                save_suggestion_cache(suggestion_cache_path(output_dir), _suggestion_cache)
        return suggestions, 0.0

    provider, model_name = provider_result
    prompt = build_suggest_prompt(candidates)

    cost_tracker = CostTracker(budget_usd=budget_usd)

    # Rough token estimate: ~4 chars per token; enforce pre-call budget check
    estimated_input_tokens = len(prompt) // 4
    estimated_output_tokens = 1500
    estimated_cost = estimated_input_tokens * 0.000003 + estimated_output_tokens * 0.000015
    if budget_usd is not None and estimated_cost > budget_usd:
        raise BudgetExceededError(
            budget_usd=budget_usd,
            current_usd=0.0,
            call_cost_usd=estimated_cost,
            feature="suggest-initiatives",
        )

    raw = provider.generate(
        prompt,
        model_name,
        1500,
        cost_tracker=cost_tracker,
        feature="suggest-initiatives",
    )

    actual_cost = cost_tracker._total_usd
    suggestions = parse_suggest_response(raw, candidates)
    if cache_key is not None:
        _suggestion_cache[cache_key] = (suggestions, actual_cost)
        _suggestion_cache.move_to_end(cache_key)
        # Bounded eviction — FIFO: oldest entry evicted first
        while len(_suggestion_cache) > _CACHE_MAX_SIZE:
            _suggestion_cache.popitem(last=False)
        # Persist to disk if caller passed output_dir
        if output_dir is not None:
            save_suggestion_cache(suggestion_cache_path(output_dir), _suggestion_cache)
    return suggestions, actual_cost
