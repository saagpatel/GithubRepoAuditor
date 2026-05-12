"""Initiative tracker — set, persist, and derive status for tier-upgrade goals.

Persistence: ``output/initiatives.json`` (or a caller-supplied path).
Schema version: 1.

File layout::

    {
        "version": 1,
        "initiatives": [
            {
                "repo_name": "Wavelength",
                "target_tier": 3,
                "deadline": "2026-06-15",
                "set_at": "2026-05-12T10:00:00+00:00",
                "set_by": "operator",
                "closed_at": null,
                "closed_reason": null
            }
        ]
    }

Atomic writes use the same tmp-sibling-then-rename pattern as
``src/operator_prefs.py``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from src.maturity_tiers import compute_tier

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

# ── Dataclass ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Initiative:
    repo_name: str
    target_tier: int
    deadline: str  # ISO date YYYY-MM-DD
    set_at: str  # ISO timestamp
    set_by: str  # operator identity
    closed_at: str | None = None  # set when --close-initiative
    closed_reason: str | None = None  # "met" | "abandoned" | "deadline-extended"


# ── Path helper ──────────────────────────────────────────────────────────────


def initiatives_path(output_dir: Path) -> Path:
    """Return the canonical path ``output_dir/initiatives.json``."""
    return output_dir / "initiatives.json"


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _initiative_to_dict(i: Initiative) -> dict:
    return asdict(i)


def _initiative_from_dict(d: dict) -> Initiative:
    return Initiative(
        repo_name=str(d.get("repo_name", "")),
        target_tier=int(d.get("target_tier", 2)),
        deadline=str(d.get("deadline", "")),
        set_at=str(d.get("set_at", "")),
        set_by=str(d.get("set_by", "operator")),
        closed_at=d.get("closed_at") or None,
        closed_reason=d.get("closed_reason") or None,
    )


# ── Atomic write ─────────────────────────────────────────────────────────────


def _write_atomic(path: Path, data: dict) -> None:
    """Write *data* to *path* atomically using a sibling temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".initiatives_tmp_",
        suffix=".json",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
        json.dump(data, tmp, indent=2, sort_keys=True)
    tmp_path.replace(path)


# ── Public persistence API ────────────────────────────────────────────────────


def load_initiatives(path: Path) -> list[Initiative]:
    """Read initiatives from *path*.

    Missing file, empty file, or malformed JSON → returns ``[]`` and logs a
    warning rather than raising.
    """
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        items = data.get("initiatives", [])
        return [_initiative_from_dict(item) for item in items]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("initiatives.json malformed — returning empty list: %s", exc)
        return []


def save_initiatives(path: Path, initiatives: list[Initiative]) -> None:
    """Write *initiatives* to *path* atomically.

    Schema: ``{"version": 1, "initiatives": [...]}``.
    """
    data = {
        "version": _SCHEMA_VERSION,
        "initiatives": [_initiative_to_dict(i) for i in initiatives],
    }
    _write_atomic(path, data)


def upsert_initiative(path: Path, initiative: Initiative) -> None:
    """Add or replace the open initiative for ``initiative.repo_name``.

    "Open" means ``closed_at is None``.  If an open initiative already exists
    for the repo, it is replaced.  Closed initiatives are left untouched.
    """
    existing = load_initiatives(path)
    updated: list[Initiative] = []
    replaced = False
    for item in existing:
        if item.repo_name == initiative.repo_name and item.closed_at is None:
            updated.append(initiative)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(initiative)
    save_initiatives(path, updated)


def close_initiative(path: Path, repo_name: str, reason: str = "met") -> Initiative | None:
    """Set ``closed_at`` + ``closed_reason`` on the open initiative for *repo_name*.

    Returns the closed ``Initiative``, or ``None`` if no open initiative exists
    for that repo.
    """
    existing = load_initiatives(path)
    closed_item: Initiative | None = None
    updated: list[Initiative] = []
    now = datetime.now(tz=timezone.utc).isoformat()
    for item in existing:
        if item.repo_name == repo_name and item.closed_at is None and closed_item is None:
            closed_item = Initiative(
                repo_name=item.repo_name,
                target_tier=item.target_tier,
                deadline=item.deadline,
                set_at=item.set_at,
                set_by=item.set_by,
                closed_at=now,
                closed_reason=reason,
            )
            updated.append(closed_item)
        else:
            updated.append(item)
    if closed_item is not None:
        save_initiatives(path, updated)
    return closed_item


# ── Status derivation ────────────────────────────────────────────────────────


def derive_status(
    initiative: Initiative,
    repo: dict,
    today: str | None = None,
) -> str:
    """Return the status of *initiative* relative to *repo*'s current state.

    Returns one of: ``'on-track'`` | ``'at-risk'`` | ``'overdue'`` | ``'met'``.

    Rules (in priority order):
    1. If ``closed_at`` is set → ``'met'`` (terminal state regardless of reason).
    2. If current tier >= target tier → ``'met'`` (goal achieved; stays open
       until operator runs ``--close-initiative``).
    3. If deadline has passed → ``'overdue'``.
    4. If deadline is within 14 days → ``'at-risk'``.
    5. Otherwise → ``'on-track'``.

    Note: tier upgrades do NOT auto-close initiatives.  ``derive_status`` may
    return ``'met'`` while ``initiative.closed_at`` is still ``None``.
    """
    # 1. Already closed
    if initiative.closed_at is not None:
        return "met"

    # 2. Tier goal reached
    current = compute_tier(repo)
    if current >= initiative.target_tier:
        return "met"

    # Parse deadline
    today_date = date.fromisoformat(today) if today else date.today()
    try:
        deadline_date = date.fromisoformat(initiative.deadline)
    except (ValueError, TypeError):
        return "on-track"

    # 3. Overdue
    if today_date > deadline_date:
        return "overdue"

    # 4. At-risk (≤ 14 days remaining)
    delta = (deadline_date - today_date).days
    if delta <= 14:
        return "at-risk"

    # 5. On-track
    return "on-track"


# ── Operator identity helper ──────────────────────────────────────────────────


def operator_identity() -> str:
    """Return ``$USER`` env var, falling back to ``'operator'``."""
    return os.environ.get("USER") or "operator"
