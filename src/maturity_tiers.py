"""Maturity tier model for portfolio repos.

Tiers (Bronze → Platinum) are computed deterministically from fields in
``output/portfolio-truth-latest.json``.  Where the strict criterion isn't
directly available in portfolio-truth, the check *degrades gracefully* using a
proxy field.  Every degraded criterion is documented inline and in the
``requirements`` strings below.

Degraded criteria (v1 — proxy-only, pre-Sprint-8 snapshots):
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

Sprint 8.3 upgrade — strict-then-proxy:
Each of the six criteria above now checks for Sprint-8.2 strict signals first.
Detection: if the key ``"has_tests"`` exists in ``derived``, the dict was built
with the Sprint-8.2 schema and all strict signals are trusted.  Pre-Sprint-8
snapshots lack those keys and fall through to the proxy logic unchanged.

Strict fields (populated by Sprint 8.2):
- derived.has_tests: bool            — replaces run_instructions_present proxy
- derived.has_ci: bool               — replaces run_instructions+doctor_gap proxy
- derived.readme_char_count: int     — replaces context_quality != "boilerplate" proxy
- derived.release_count: int | None  — replaces context_quality proxy (opt-in only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Literal

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
    requirement_sources: list[Literal["strict", "proxy"]] = field(default_factory=list)


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


def _is_sprint8_snapshot(derived: dict) -> bool:
    """Return True if *derived* contains Sprint-8.2 strict signals.

    Detection: the key ``"has_tests"`` only exists in snapshots built with the
    Sprint-8.2 schema (``DerivedFields`` added it).  Pre-Sprint-8 portfolio-truth
    JSON files never contain this key, so its presence is a reliable sentinel.
    """
    return "has_tests" in derived


# ── Strict-then-proxy check helpers ─────────────────────────────────────────
# Each function returns (passed: bool, source: Literal["strict", "proxy"]).
# *derived* and *risk* are the sub-dicts extracted from the repo dict.


def _check_readme_chars(derived: dict) -> tuple[bool, Literal["strict", "proxy"]]:
    """README ≥ 200 chars — strict if readme_char_count present, else proxy."""
    if _is_sprint8_snapshot(derived) and "readme_char_count" in derived:
        count = derived.get("readme_char_count", 0)
        return (isinstance(count, int) and count >= 200, "strict")
    # Proxy: context_quality != "boilerplate"
    return (derived.get("context_quality") != "boilerplate", "proxy")


def _check_has_tests(derived: dict) -> tuple[bool, Literal["strict", "proxy"]]:
    """Tests present — strict has_tests bool if Sprint-8 snapshot, else proxy."""
    if _is_sprint8_snapshot(derived):
        return (derived.get("has_tests") is True, "strict")
    # Proxy: run_instructions_present
    return (bool(derived.get("run_instructions_present")), "proxy")


def _check_has_ci(derived: dict, risk: dict) -> tuple[bool, Literal["strict", "proxy"]]:
    """CI workflow present — strict has_ci bool if Sprint-8 snapshot, else proxy."""
    if _is_sprint8_snapshot(derived):
        return (derived.get("has_ci") is True, "strict")
    # Proxy: run_instructions_present AND NOT doctor_gap
    run_ok = bool(derived.get("run_instructions_present"))
    doctor_gap = bool(risk.get("doctor_gap", True))
    return (run_ok and not doctor_gap, "proxy")


def _check_release_shipped(derived: dict) -> tuple[bool, Literal["strict", "proxy"]]:
    """Shipped ≥ 1 release — strict release_count if present, else proxy."""
    if _is_sprint8_snapshot(derived) and "release_count" in derived:
        rc = derived.get("release_count")
        if rc is not None:
            return (isinstance(rc, int) and rc >= 1, "strict")
    # Proxy: context_quality in ("strong", "operating", "shipped")
    cq = str(derived.get("context_quality") or "")
    return (cq in ("strong", "operating", "shipped"), "proxy")


def _check_release_recent(derived: dict) -> tuple[bool, Literal["strict", "proxy"]]:
    """≥ 2 releases in last 365d — strict release_count if present, else proxy."""
    if _is_sprint8_snapshot(derived) and "release_count" in derived:
        rc = derived.get("release_count")
        if rc is not None:
            return (isinstance(rc, int) and rc >= 2, "strict")
    # Proxy: activity_status == "active" AND context_quality in strong set
    activity_status = str(derived.get("activity_status") or "")
    cq = str(derived.get("context_quality") or "")
    return (
        activity_status == "active" and cq in ("strong", "operating", "shipped"),
        "proxy",
    )


def _check_readme_not_stale(derived: dict) -> tuple[bool, Literal["strict", "proxy"]]:
    """README staleness ≤ 5x — no strict signal, always proxy."""
    activity_status = str(derived.get("activity_status") or "")
    return (activity_status != "stale", "proxy")


# ── Tier check functions (return missing requirement strings) ─────────────


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
    derived = repo.get("derived") or {}
    risk = repo.get("risk") or {}
    if not isinstance(derived, dict):
        derived = {}
    if not isinstance(risk, dict):
        risk = {}

    missing: list[str] = []

    readme_ok, _ = _check_readme_chars(derived)
    if not readme_ok:
        missing.append("Non-boilerplate README (proxy: context_quality != 'boilerplate')")

    tests_ok, _ = _check_has_tests(derived)
    if not tests_ok:
        missing.append("Tests present (proxy: derived.run_instructions_present == True)")

    ci_ok, _ = _check_has_ci(derived, risk)
    if not ci_ok:
        missing.append(
            "CI workflow present (proxy: run_instructions_present AND risk.doctor_gap == False)"
        )

    days = _days_since_activity(repo)
    if days is None or days > 365:
        missing.append("Last commit ≤ 365 days ago")

    return missing


def _check_gold(repo: dict) -> list[str]:
    """Return list of unmet Gold requirements (beyond Silver)."""
    derived = repo.get("derived") or {}
    risk = repo.get("risk") or {}
    if not isinstance(derived, dict):
        derived = {}
    if not isinstance(risk, dict):
        risk = {}

    missing: list[str] = []

    shipped_ok, _ = _check_release_shipped(derived)
    if not shipped_ok:
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

    stale_ok, _ = _check_readme_not_stale(derived)
    if not stale_ok:
        missing.append("README not stale (proxy: derived.activity_status != 'stale')")

    return missing


def _check_platinum(repo: dict) -> list[str]:
    """Return list of unmet Platinum requirements (beyond Gold)."""
    derived = repo.get("derived") or {}
    if not isinstance(derived, dict):
        derived = {}

    missing: list[str] = []

    days = _days_since_activity(repo)
    if days is None or days > 90:
        missing.append("Last commit ≤ 90 days ago")

    recent_ok, _ = _check_release_recent(derived)
    if not recent_ok:
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


# ── Source-annotated check helpers (for tier_gap requirement_sources) ────────


def _check_silver_with_sources(
    repo: dict,
) -> tuple[list[str], list[Literal["strict", "proxy"]]]:
    """Like _check_silver but also returns parallel source annotations."""
    derived = repo.get("derived") or {}
    risk = repo.get("risk") or {}
    if not isinstance(derived, dict):
        derived = {}
    if not isinstance(risk, dict):
        risk = {}

    missing: list[str] = []
    sources: list[Literal["strict", "proxy"]] = []

    readme_ok, readme_src = _check_readme_chars(derived)
    if not readme_ok:
        missing.append("Non-boilerplate README (proxy: context_quality != 'boilerplate')")
        sources.append(readme_src)

    tests_ok, tests_src = _check_has_tests(derived)
    if not tests_ok:
        missing.append("Tests present (proxy: derived.run_instructions_present == True)")
        sources.append(tests_src)

    ci_ok, ci_src = _check_has_ci(derived, risk)
    if not ci_ok:
        missing.append(
            "CI workflow present (proxy: run_instructions_present AND risk.doctor_gap == False)"
        )
        sources.append(ci_src)

    days = _days_since_activity(repo)
    if days is None or days > 365:
        missing.append("Last commit ≤ 365 days ago")
        sources.append("proxy")  # no strict signal for commit age

    return missing, sources


def _check_gold_with_sources(
    repo: dict,
) -> tuple[list[str], list[Literal["strict", "proxy"]]]:
    """Like _check_gold but also returns parallel source annotations."""
    derived = repo.get("derived") or {}
    risk = repo.get("risk") or {}
    if not isinstance(derived, dict):
        derived = {}
    if not isinstance(risk, dict):
        risk = {}

    missing: list[str] = []
    sources: list[Literal["strict", "proxy"]] = []

    shipped_ok, shipped_src = _check_release_shipped(derived)
    if not shipped_ok:
        missing.append(
            "Shipped release (proxy: context_quality in ('strong','operating','shipped'))"
        )
        sources.append(shipped_src)

    risk_tier = str(_get(repo, "risk", "risk_tier", default="") or "")
    doctor_gap = bool(_get(repo, "risk", "doctor_gap", default=True))
    if risk_tier not in ("baseline", "") or doctor_gap:
        missing.append(
            "Security clean (risk.risk_tier in ('baseline','') AND risk.doctor_gap == False)"
        )
        sources.append("proxy")  # security check is always proxy-based

    if not _has_license(repo):
        missing.append("LICENSE present (LICENSE in derived.context_files, case-insensitive)")
        sources.append("proxy")  # LICENSE presence is file-based, no strict signal change

    stale_ok, stale_src = _check_readme_not_stale(derived)
    if not stale_ok:
        missing.append("README not stale (proxy: derived.activity_status != 'stale')")
        sources.append(stale_src)

    return missing, sources


def _check_platinum_with_sources(
    repo: dict,
) -> tuple[list[str], list[Literal["strict", "proxy"]]]:
    """Like _check_platinum but also returns parallel source annotations."""
    derived = repo.get("derived") or {}
    if not isinstance(derived, dict):
        derived = {}

    missing: list[str] = []
    sources: list[Literal["strict", "proxy"]] = []

    days = _days_since_activity(repo)
    if days is None or days > 90:
        missing.append("Last commit ≤ 90 days ago")
        sources.append("proxy")  # commit age has no strict signal

    recent_ok, recent_src = _check_release_recent(derived)
    if not recent_ok:
        missing.append(
            "≥ 2 releases in last 365d "
            "(proxy: activity_status == 'active' AND Gold-level context_quality)"
        )
        sources.append(recent_src)

    risk_factors = _get(repo, "risk", "risk_factors", default=[])
    if not isinstance(risk_factors, list):
        risk_factors = []
    if len(risk_factors) > 0:
        missing.append("No abandoned dependency flags (len(risk.risk_factors) == 0)")
        sources.append("proxy")  # risk_factors list is always proxy-based

    return missing, sources


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

    The returned ``TierGap.requirement_sources`` is a parallel list to
    ``missing_requirements`` indicating whether each gap was detected via a
    strict signal (``"strict"``) or a proxy field (``"proxy"``).  Callers
    that don't need source provenance can ignore this field; it defaults to
    an empty list when no missing requirements exist.
    """
    if target not in TIER_DEFINITIONS:
        raise ValueError(f"target tier must be 1-4, got {target!r}")

    current = compute_tier(repo)

    if current >= target:
        return TierGap(current_tier=current, target_tier=target, missing_requirements=[])

    missing: list[str] = []
    sources: list[Literal["strict", "proxy"]] = []

    # Collect all unmet requirements up to and including target tier
    if target >= 1 and current < 1:
        bronze_missing = _check_bronze(repo)
        missing.extend(bronze_missing)
        sources.extend(["proxy"] * len(bronze_missing))  # bronze checks are all proxy

    if target >= 2:
        silver_missing, silver_sources = _check_silver_with_sources(repo)
        if silver_missing or current < 1:
            missing.extend(silver_missing)
            sources.extend(silver_sources)

    if target >= 3:
        gold_missing, gold_sources = _check_gold_with_sources(repo)
        if gold_missing or current < 2:
            missing.extend(gold_missing)
            sources.extend(gold_sources)

    if target >= 4:
        plat_missing, plat_sources = _check_platinum_with_sources(repo)
        if plat_missing or current < 3:
            missing.extend(plat_missing)
            sources.extend(plat_sources)

    # Deduplicate while preserving order and keeping sources in sync
    seen: set[str] = set()
    deduped: list[str] = []
    deduped_sources: list[Literal["strict", "proxy"]] = []
    for item, src in zip(missing, sources):
        if item not in seen:
            seen.add(item)
            deduped.append(item)
            deduped_sources.append(src)

    return TierGap(
        current_tier=current,
        target_tier=target,
        missing_requirements=deduped,
        requirement_sources=deduped_sources,
    )


def tier_name(tier: int) -> str:
    """Return display name for a tier integer (0 → 'Untracked', 1-4 → name)."""
    if tier == 0:
        return "Untracked"
    return TIER_DEFINITIONS.get(tier, TierCriteria(tier, str(tier), [])).name
