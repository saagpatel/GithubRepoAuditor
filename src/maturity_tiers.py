"""Maturity tier model for portfolio repos.

Tiers (Bronze → Platinum) are computed deterministically from fields in
``output/portfolio-truth-latest.json``.  Where the strict criterion isn't
directly available in portfolio-truth, the check *degrades gracefully* using a
proxy field.  Every degraded criterion is documented inline and in the
``requirements`` strings below.

Degraded criteria (v1):
- README ≥ 200 chars          → context_quality != "boilerplate"
- Has tests                   → run_instructions_present == True
                                (proxy: repos with run instructions almost
                                 always have a test step documented)
- Has CI workflow              → run_instructions_present == True AND
                                 risk.doctor_gap == False
                                (CI presence is not a distinct portfolio-truth
                                 field; doctor_gap False means the repo health
                                 check found nothing critically missing)
- Shipped release              → context_quality in ("strong","operating","shipped")
                                (portfolio-truth doesn't carry release counts;
                                 high context quality is a reliable proxy)
- README staleness ≤ 5x       → activity_status != "stale"
                                (stale activity strongly correlates with stale
                                 README; exact ratio not tracked)
- ≥ 2 releases in last 365d   → activity_status == "active" AND
                                 context_quality in ("strong","operating","shipped")
                                (release count not in portfolio-truth; active
                                 repos with strong context are reasonable proxies)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TierCriteria:
    tier: int  # 1-4
    name: str  # "Bronze" | "Silver" | "Gold" | "Platinum"
    requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TierGap:
    current_tier: int
    target_tier: int
    missing_requirements: list[str] = field(default_factory=list)


# ── Tier definitions ─────────────────────────────────────────────────────────

TIER_DEFINITIONS: dict[int, TierCriteria] = {
    1: TierCriteria(
        tier=1,
        name="Bronze",
        requirements=[
            "Has git history (identity.has_git == True)",
            "At least one commit (derived.last_meaningful_activity_at non-empty)",
            "README present (README.md in derived.context_files)",
        ],
    ),
    2: TierCriteria(
        tier=2,
        name="Silver",
        requirements=[
            "All Bronze criteria",
            "Non-boilerplate README (proxy: context_quality != 'boilerplate')",
            "Tests present (proxy: derived.run_instructions_present == True)",
            "CI workflow present (proxy: run_instructions_present AND risk.doctor_gap == False)",
            "Last commit ≤ 365 days ago",
        ],
    ),
    3: TierCriteria(
        tier=3,
        name="Gold",
        requirements=[
            "All Silver criteria",
            "Shipped release (proxy: context_quality in ('strong','operating','shipped'))",
            "Security clean (risk.risk_tier in ('baseline','') AND risk.doctor_gap == False)",
            "LICENSE present (LICENSE in derived.context_files, case-insensitive)",
            "README not stale (proxy: derived.activity_status != 'stale')",
        ],
    ),
    4: TierCriteria(
        tier=4,
        name="Platinum",
        requirements=[
            "All Gold criteria",
            "Last commit ≤ 90 days ago",
            "≥ 2 releases in last 365d (proxy: activity_status == 'active' AND Gold-level context_quality)",
            "No abandoned dependency flags (len(risk.risk_factors) == 0)",
        ],
    ),
}


# ── Internal helpers ─────────────────────────────────────────────────────────


def _get(repo: dict, *keys: str, default: object = None) -> object:
    """Safe nested dict access: _get(repo, 'derived', 'context_quality')."""
    cur: object = repo
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _context_files(repo: dict) -> list[str]:
    val = _get(repo, "derived", "context_files", default=[])
    if not isinstance(val, list):
        return []
    return [str(f) for f in val]


def _has_readme(repo: dict) -> bool:
    files = _context_files(repo)
    return any("readme" in f.lower() for f in files)


def _has_license(repo: dict) -> bool:
    files = _context_files(repo)
    return any("license" in f.lower() for f in files)


def _days_since_activity(repo: dict) -> int | None:
    """Return integer days since last_meaningful_activity_at, or None if unknown."""
    raw = _get(repo, "derived", "last_meaningful_activity_at", default=None)
    if not raw or not isinstance(raw, str):
        return None
    try:
        # Support both ISO datetime strings and plain dates
        ts = raw.replace("Z", "+00:00")
        if "T" in ts:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            today = datetime.now(tz=timezone.utc)
        else:
            dt_date = date.fromisoformat(ts[:10])
            today_date = date.today()
            return (today_date - dt_date).days
        return (today - dt).days
    except (ValueError, TypeError):
        return None


def _check_bronze(repo: dict) -> list[str]:
    """Return list of unmet Bronze requirements."""
    missing: list[str] = []
    has_git = _get(repo, "identity", "has_git", default=False)
    if not has_git:
        missing.append("Has git history (identity.has_git == True)")
    lma = _get(repo, "derived", "last_meaningful_activity_at", default=None)
    if not lma:
        missing.append("At least one commit (derived.last_meaningful_activity_at non-empty)")
    if not _has_readme(repo):
        missing.append("README present (README.md in derived.context_files)")
    return missing


def _check_silver(repo: dict) -> list[str]:
    """Return list of unmet Silver requirements (beyond Bronze)."""
    missing: list[str] = []
    cq = _get(repo, "derived", "context_quality", default="")
    if cq == "boilerplate":
        missing.append("Non-boilerplate README (proxy: context_quality != 'boilerplate')")
    run_ok = bool(_get(repo, "derived", "run_instructions_present", default=False))
    if not run_ok:
        missing.append("Tests present (proxy: derived.run_instructions_present == True)")
    doctor_gap = bool(_get(repo, "risk", "doctor_gap", default=True))
    if not run_ok or doctor_gap:
        missing.append(
            "CI workflow present (proxy: run_instructions_present AND risk.doctor_gap == False)"
        )
    days = _days_since_activity(repo)
    if days is None or days > 365:
        missing.append("Last commit ≤ 365 days ago")
    return missing


def _check_gold(repo: dict) -> list[str]:
    """Return list of unmet Gold requirements (beyond Silver)."""
    missing: list[str] = []
    cq = str(_get(repo, "derived", "context_quality", default="") or "")
    if cq not in ("strong", "operating", "shipped"):
        missing.append(
            "Shipped release (proxy: context_quality in ('strong','operating','shipped'))"
        )
    risk_tier = str(_get(repo, "risk", "risk_tier", default="") or "")
    doctor_gap = bool(_get(repo, "risk", "doctor_gap", default=True))
    if risk_tier not in ("baseline", "") or doctor_gap:
        missing.append(
            "Security clean (risk.risk_tier in ('baseline','') AND risk.doctor_gap == False)"
        )
    if not _has_license(repo):
        missing.append("LICENSE present (LICENSE in derived.context_files, case-insensitive)")
    activity_status = str(_get(repo, "derived", "activity_status", default="") or "")
    if activity_status == "stale":
        missing.append("README not stale (proxy: derived.activity_status != 'stale')")
    return missing


def _check_platinum(repo: dict) -> list[str]:
    """Return list of unmet Platinum requirements (beyond Gold)."""
    missing: list[str] = []
    days = _days_since_activity(repo)
    if days is None or days > 90:
        missing.append("Last commit ≤ 90 days ago")
    activity_status = str(_get(repo, "derived", "activity_status", default="") or "")
    cq = str(_get(repo, "derived", "context_quality", default="") or "")
    if activity_status != "active" or cq not in ("strong", "operating", "shipped"):
        missing.append(
            "≥ 2 releases in last 365d "
            "(proxy: activity_status == 'active' AND Gold-level context_quality)"
        )
    risk_factors = _get(repo, "risk", "risk_factors", default=[])
    if not isinstance(risk_factors, list):
        risk_factors = []
    if len(risk_factors) > 0:
        missing.append("No abandoned dependency flags (len(risk.risk_factors) == 0)")
    return missing


# ── Public API ───────────────────────────────────────────────────────────────


def compute_tier(repo: dict) -> int:
    """Return the highest tier (1-4) that *repo* satisfies.

    Falls back to 1 (Bronze) for any repo with ``identity.has_git == True``.
    Repos without git are not portfolio-tier-eligible and return 0, though
    callers should treat any non-zero value as meaningful.
    """
    has_git = _get(repo, "identity", "has_git", default=False)
    if not has_git:
        # Not even Bronze — report 0 to signal no-git
        # Callers that want "at least Bronze" should check has_git separately.
        return 0

    # Bronze: implicit for any repo with has_git == True
    # Check each tier in ascending order; stop when criteria aren't met.

    # Silver check
    if _check_silver(repo):
        return 1

    # Gold check
    if _check_gold(repo):
        return 2

    # Platinum check
    if _check_platinum(repo):
        return 3

    return 4


def tier_gap(repo: dict, target: int) -> TierGap:
    """Return the requirements missing for *repo* to reach *target* tier.

    If the repo is already at or above *target*, ``missing_requirements`` is
    empty.  *target* must be in 1-4.
    """
    if target not in TIER_DEFINITIONS:
        raise ValueError(f"target tier must be 1-4, got {target!r}")

    current = compute_tier(repo)

    missing: list[str] = []
    if current >= target:
        return TierGap(current_tier=current, target_tier=target, missing_requirements=[])

    # Collect all unmet requirements up to and including target tier
    if target >= 1 and current < 1:
        missing.extend(_check_bronze(repo))
    if target >= 2:
        silver_missing = _check_silver(repo)
        if silver_missing or current < 1:
            missing.extend(silver_missing)
    if target >= 3:
        gold_missing = _check_gold(repo)
        if gold_missing or current < 2:
            missing.extend(gold_missing)
    if target >= 4:
        plat_missing = _check_platinum(repo)
        if plat_missing or current < 3:
            missing.extend(plat_missing)

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return TierGap(
        current_tier=current,
        target_tier=target,
        missing_requirements=deduped,
    )


def tier_name(tier: int) -> str:
    """Return display name for a tier integer (0 → 'Untracked', 1-4 → name)."""
    if tier == 0:
        return "Untracked"
    return TIER_DEFINITIONS.get(tier, TierCriteria(tier, str(tier), [])).name
