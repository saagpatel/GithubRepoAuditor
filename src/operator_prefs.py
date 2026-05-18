"""Operator preference memory — suppression hints for repetitively-rejected actions.

After each --approval-center session, detect (action_type, target_context) pairs that
have been rejected ≥ threshold times consecutively and persist suppression hints to
output/operator_prefs.json.  Future surfaces (briefing, planner, drafter) consult this
file before generating suggestions; suppressed actions are de-emphasised rather than
removed entirely, so observability is preserved.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

OPERATOR_PREFS_FILENAME = "operator_prefs.json"
OPERATOR_PREFS_VERSION = 1


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class SuppressionHint:
    action_type: str
    target_context: str  # e.g. "notion_writeback" or a repo glob / "*"
    rejection_count: int
    last_rejected_at: str
    suppressed_at: str
    manual: bool = False


# ── Path helper ──────────────────────────────────────────────────────────────


def prefs_path(output_dir: Path) -> Path:
    return Path(output_dir) / OPERATOR_PREFS_FILENAME


# ── Core detection ───────────────────────────────────────────────────────────


def detect_suppressions(
    approval_records: list[dict],
    *,
    threshold: int = 3,
) -> list[SuppressionHint]:
    """Identify (action_type, target_context) pairs rejected ≥ *threshold* times
    consecutively (no intervening approval).

    Each record in *approval_records* is expected to carry:

    - ``action_type``     — e.g. "campaign", "governance", or a free-form string.
                            Falls back to ``approval_subject_type`` if absent.
    - ``target_context``  — e.g. a campaign/scope key or ``"*"``.
                            Falls back to ``subject_key`` if absent.
    - ``decision``        — ``"rejected"`` | ``"approved"``.
                            A record without a ``decision`` field is **ignored**;
                            the caller is responsible for populating this.
    - ``timestamp``       — ISO8601 string used for ordering.
                            Falls back to ``approved_at`` then ``reviewed_at``.

    "Consecutively" means: sorted by timestamp ascending, the most-recent *N* records
    for that pair are ALL rejections (no interleaved approval resets the counter).
    """
    if not approval_records:
        return []

    # Normalise records into (action_type, target_context, decision, timestamp) tuples
    normalised: list[tuple[str, str, str, str]] = []
    for rec in approval_records:
        action_type = str(rec.get("action_type") or rec.get("approval_subject_type") or "").strip()
        target_context = str(rec.get("target_context") or rec.get("subject_key") or "*").strip()
        decision = str(rec.get("decision") or "").strip().lower()
        timestamp = str(
            rec.get("timestamp") or rec.get("approved_at") or rec.get("reviewed_at") or ""
        ).strip()

        if not action_type or decision not in {"approved", "rejected"}:
            continue
        if not target_context:
            target_context = "*"
        normalised.append((action_type, target_context, decision, timestamp))

    if not normalised:
        return []

    # Sort ascending by timestamp so we can walk in chronological order
    normalised.sort(key=lambda t: t[3])

    # Build per-pair ordered decision lists
    pair_decisions: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for action_type, target_context, decision, timestamp in normalised:
        key = (action_type, target_context)
        pair_decisions.setdefault(key, []).append((decision, timestamp))

    now_iso = datetime.now(timezone.utc).isoformat()
    hints: list[SuppressionHint] = []

    for (action_type, target_context), decisions in pair_decisions.items():
        # Count trailing consecutive rejections (working from most-recent backwards)
        streak = 0
        last_rejected_at = ""
        for decision, timestamp in reversed(decisions):
            if decision == "rejected":
                streak += 1
                if not last_rejected_at:
                    last_rejected_at = timestamp
            else:
                break  # approval breaks the streak

        if streak >= threshold:
            hints.append(
                SuppressionHint(
                    action_type=action_type,
                    target_context=target_context,
                    rejection_count=streak,
                    last_rejected_at=last_rejected_at,
                    suppressed_at=now_iso,
                    manual=False,
                )
            )

    return hints


# ── Persistence ──────────────────────────────────────────────────────────────


def load_prefs(path: Path) -> dict:
    """Read *operator_prefs.json*.  Returns ``{}`` if the file is missing or
    malformed — never crashes the caller.
    """
    resolved = Path(path)
    if not resolved.exists():
        return {}
    try:
        raw = resolved.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning("operator_prefs: unexpected root type, treating as empty")
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("operator_prefs: could not load %s: %s", path, exc)
        return {}


def save_prefs(path: Path, hints: list[SuppressionHint]) -> None:
    """Merge *hints* with any existing prefs and write atomically via tmp+rename.

    Preserves ``manual: true`` entries already present in the file.
    """
    resolved = Path(path)
    existing = load_prefs(resolved)
    merged = merge_with_existing(existing, hints)
    _write_atomic(resolved, merged)


def _write_atomic(path: Path, data: dict) -> None:
    """Write *data* to *path* atomically using a sibling temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Use the same directory so rename is on the same filesystem
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".operator_prefs_tmp_",
            suffix=".json",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(data, tmp, indent=2, sort_keys=True)
        tmp_path.replace(path)
    except OSError as exc:
        logger.error("operator_prefs: atomic write failed for %s: %s", path, exc)
        raise


# ── Merge helper ─────────────────────────────────────────────────────────────


def merge_with_existing(existing: dict, new_hints: list[SuppressionHint]) -> dict:
    """Return a fresh prefs dict that:

    - Keeps all ``manual: true`` suppressions from *existing* unchanged.
    - Replaces auto-detected suppressions (``manual: false``) with *new_hints*.
    - Preserves any top-level metadata keys (``version``, etc.).
    """
    current_suppressions: list[dict] = list(existing.get("suppressions", []))

    # Retain only manually-added entries
    manual_entries = [s for s in current_suppressions if s.get("manual") is True]

    # Build merged list: manual first, then auto-detected
    merged_suppressions: list[dict] = list(manual_entries)
    seen_manual_keys = {(s["action_type"], s["target_context"]) for s in manual_entries}

    for hint in new_hints:
        key = (hint.action_type, hint.target_context)
        if key not in seen_manual_keys:
            merged_suppressions.append(asdict(hint))

    return {
        "version": OPERATOR_PREFS_VERSION,
        "suppressions": merged_suppressions,
    }


# ── Lookup ───────────────────────────────────────────────────────────────────


def is_suppressed(
    prefs: dict,
    action_type: str,
    target_context: str,
) -> SuppressionHint | None:
    """Return the matching :class:`SuppressionHint` if the given
    ``(action_type, target_context)`` is suppressed, otherwise ``None``.

    Matching rules (in priority order):

    1. Exact match on both ``action_type`` and ``target_context``.
    2. Exact ``action_type`` + wildcard ``target_context == "*"`` in the prefs entry.
    """
    suppressions = prefs.get("suppressions", [])
    if not isinstance(suppressions, list):
        return None

    best: SuppressionHint | None = None
    for entry in suppressions:
        if not isinstance(entry, dict):
            continue
        if entry.get("action_type") != action_type:
            continue
        entry_ctx = entry.get("target_context", "")
        if entry_ctx == target_context:
            # Exact match — highest priority, return immediately
            return SuppressionHint(
                action_type=entry["action_type"],
                target_context=entry_ctx,
                rejection_count=int(entry.get("rejection_count", 0)),
                last_rejected_at=str(entry.get("last_rejected_at", "")),
                suppressed_at=str(entry.get("suppressed_at", "")),
                manual=bool(entry.get("manual", False)),
            )
        if entry_ctx == "*":
            # Wildcard match — keep as candidate but continue looking for exact
            best = SuppressionHint(
                action_type=entry["action_type"],
                target_context=entry_ctx,
                rejection_count=int(entry.get("rejection_count", 0)),
                last_rejected_at=str(entry.get("last_rejected_at", "")),
                suppressed_at=str(entry.get("suppressed_at", "")),
                manual=bool(entry.get("manual", False)),
            )
    return best


# ── Reset ────────────────────────────────────────────────────────────────────


def reset_prefs(path: Path) -> None:
    """Delete the prefs file.  Idempotent — does not error if already absent."""
    resolved = Path(path)
    try:
        resolved.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("operator_prefs: could not delete %s: %s", path, exc)


# ── Post-process helper (called by approval-center flow) ─────────────────────


def post_process_approval_session(
    approval_records: list[dict],
    output_dir: Path,
    *,
    threshold: int = 3,
) -> tuple[int, int]:
    """Detect suppressions from *approval_records* and persist to prefs.

    Returns ``(total_suppressed, newly_added)`` counts for the 1-line CLI summary.
    """
    path = prefs_path(output_dir)
    existing = load_prefs(path)
    existing_auto_keys = {
        (s["action_type"], s["target_context"])
        for s in existing.get("suppressions", [])
        if not s.get("manual")
    }

    new_hints = detect_suppressions(approval_records, threshold=threshold)
    new_keys = {(h.action_type, h.target_context) for h in new_hints}
    newly_added = len(new_keys - existing_auto_keys)

    merged = merge_with_existing(existing, new_hints)
    _write_atomic(path, merged)

    total = len(merged.get("suppressions", []))
    return total, newly_added


# ── Rejection event log ───────────────────────────────────────────────────────

REJECTION_LOG_FILENAME = "rejection_log.json"
REJECTION_LOG_VERSION = 1


def rejection_log_path(output_dir: Path) -> Path:
    return Path(output_dir) / REJECTION_LOG_FILENAME


def load_rejection_events(output_dir: Path) -> list[dict]:
    """Load persisted rejection events from *output_dir/rejection_log.json*.

    Returns ``[]`` if the file is missing or malformed.
    """
    path = rejection_log_path(output_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        events = data.get("events", [])
        if not isinstance(events, list):
            return []
        return [e for e in events if isinstance(e, dict)]
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("rejection_log: could not load %s: %s", path, exc)
        return []


def save_rejection_event(
    output_dir: Path,
    action_type: str,
    target_context: str,
    *,
    timestamp: str | None = None,
) -> None:
    """Append a rejection event to *output_dir/rejection_log.json* atomically."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    path = rejection_log_path(output_dir)
    existing = load_rejection_events(output_dir)
    existing.append(
        {
            "action_type": action_type,
            "target_context": target_context,
            "decision": "rejected",
            "timestamp": timestamp,
        }
    )
    data = {"version": REJECTION_LOG_VERSION, "events": existing}
    _write_atomic(path, data)
