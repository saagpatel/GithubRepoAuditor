"""Synthetic public-safe portfolio fixture at the current truth schema.

The public demo lane must show the app as it actually behaves today: current
schema, receipt-backed security coverage, a fresh timestamp, and enough breadth
that the portfolio table, risk/security views, and trends curve are worth
looking at. Nothing here is derived from the operator's real workspace — every
project is a closed-pool codename over invented counts, so the output is safe to
publish and safe to screenshot.

Schema currency is sourced from the producer constant rather than restated, so
a schema bump can never leave the demo fixture silently behind.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.github_security_coverage import GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION
from src.portfolio_truth_types import DERIVATION_POLICY_VERSION, SCHEMA_VERSION

# The demo workspace is deliberately not a real filesystem path.
DEMO_WORKSPACE_ROOT = "/demo-workspace"
DEMO_ORG = "demo-org"
COHORT_POLICY = "portfolio-default-attention-v1"

# Hours between the fixture timestamp and generation time. Comfortably inside
# the consumer's 48h "fresh" band, and far enough from zero to look like a real
# overnight run rather than a synthetic instant.
FRESH_OFFSET_HOURS = 6

# Number of timestamped snapshots emitted for the trends view, newest first.
HISTORY_POINTS = 9
HISTORY_INTERVAL_DAYS = 7

_CONTEXT_QUALITY_CYCLE = ("full", "standard", "minimum-viable", "boilerplate")

# Days since the last meaningful commit, per observed activity band.
_ACTIVITY_AGE_DAYS = {"active": 2, "recent": 21, "stale": 190}

# attention_state -> (operating_path, lifecycle_state)
_ATTENTION_INTENT = {
    "active-product": ("maintain", "active"),
    "active-infra": ("maintain", "active"),
    "decision-needed": ("finish", "active"),
    "experiment": ("experiment", "active"),
    "manual-only": ("maintain", "manual-only"),
    "parked": ("maintain", "dormant"),
    "archived": ("archive", "archived"),
}


@dataclass(frozen=True)
class DemoProject:
    """The axes that make a demo row interesting; everything else is derived."""

    codename: str
    group: str
    stack: tuple[str, ...]
    attention: str
    activity: str
    # complete | partial | stale | unknown — the receipt-backed coverage state.
    coverage: str
    # dependabot critical/high/medium/low, code-scanning critical/high, secrets.
    alerts: tuple[int, int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0, 0)
    has_tests: bool = True
    has_ci: bool = True


# A closed codename pool. These names exist only here; none of them shadows a
# real repository, and the group labels describe the demo, not a real portfolio.
DEMO_PROJECTS: tuple[DemoProject, ...] = (
    # Receipt-backed complete coverage — the 0.11 headline state.
    DemoProject(
        "Aurora Ledger",
        "flagship",
        ("TypeScript", "Next.js"),
        "active-product",
        "active",
        "complete",
        (1, 4, 2, 3, 0, 2, 0),
    ),
    DemoProject(
        "Basalt Relay",
        "flagship",
        ("Rust", "Tauri 2"),
        "active-product",
        "active",
        "complete",
        (0, 2, 1, 0, 0, 1, 0),
    ),
    DemoProject(
        "Cinder Atlas",
        "flagship",
        ("Python", "FastAPI"),
        "decision-needed",
        "active",
        "complete",
        (2, 3, 0, 1, 1, 0, 1),
    ),
    DemoProject(
        "Dovetail Forge",
        "platform",
        ("Go",),
        "active-infra",
        "active",
        "complete",
        (0, 0, 2, 4, 0, 0, 0),
    ),
    DemoProject(
        "Ember Conduit",
        "platform",
        ("Rust",),
        "active-infra",
        "active",
        "complete",
        (0, 1, 0, 0, 0, 0, 0),
    ),
    DemoProject(
        "Fathom Beacon",
        "platform",
        ("TypeScript", "Node"),
        "active-infra",
        "recent",
        "complete",
        (0, 0, 0, 0, 0, 0, 0),
    ),
    DemoProject(
        "Glacier Quill",
        "studio",
        ("Swift", "SwiftUI"),
        "decision-needed",
        "active",
        "complete",
        (1, 2, 3, 1, 0, 1, 0),
    ),
    DemoProject(
        "Harbor Lantern",
        "studio",
        ("TypeScript", "React"),
        "active-product",
        "recent",
        "complete",
        (0, 0, 1, 2, 0, 0, 0),
    ),
    DemoProject(
        "Ivory Sextant",
        "platform",
        ("Python",),
        "manual-only",
        "recent",
        "complete",
        (0, 1, 1, 0, 0, 0, 0),
    ),
    DemoProject(
        "Juniper Kiln",
        "studio",
        ("Kotlin",),
        "experiment",
        "active",
        "complete",
        (0, 0, 0, 1, 0, 0, 0),
    ),
    # Partial coverage — Dependabot observed, the other providers unavailable.
    DemoProject(
        "Kestrel Loom",
        "studio",
        ("Ruby",),
        "decision-needed",
        "recent",
        "partial",
        (0, 3, 1, 0, 0, 0, 0),
    ),
    DemoProject(
        "Lumen Ferry",
        "platform",
        ("Go",),
        "manual-only",
        "recent",
        "partial",
        (1, 1, 0, 2, 0, 0, 0),
    ),
    DemoProject(
        "Meridian Vault",
        "flagship",
        ("Python", "Django"),
        "active-infra",
        "active",
        "partial",
        (0, 2, 4, 1, 0, 0, 0),
    ),
    DemoProject(
        "Nimbus Charter",
        "studio",
        ("JavaScript",),
        "parked",
        "stale",
        "partial",
        (0, 0, 2, 3, 0, 0, 0),
    ),
    DemoProject(
        "Onyx Placard",
        "lab",
        ("Elixir",),
        "experiment",
        "recent",
        "partial",
        (0, 1, 0, 0, 0, 0, 0),
    ),
    DemoProject(
        "Pallas Runner",
        "lab",
        ("Rust",),
        "experiment",
        "active",
        "partial",
        (0, 0, 1, 1, 0, 0, 0),
        has_ci=False,
    ),
    # Stale receipts — the observation aged out of the producer's window.
    DemoProject("Quartz Signal", "lab", ("Python",), "parked", "stale", "stale"),
    DemoProject(
        "Rialto Pennant", "studio", ("TypeScript",), "manual-only", "stale", "stale"
    ),
    # Unknown coverage — outside the security cohort, no receipt at all.
    DemoProject(
        "Solstice Cairn",
        "lab",
        ("C",),
        "manual-only",
        "recent",
        "unknown",
        has_tests=False,
    ),
    DemoProject(
        "Tabard Anvil", "lab", ("Zig",), "experiment", "recent", "unknown", has_ci=False
    ),
    DemoProject(
        "Umbra Trellis",
        "studio",
        ("Lua",),
        "parked",
        "stale",
        "unknown",
        has_tests=False,
    ),
    DemoProject(
        "Vellum Compass",
        "lab",
        ("Haskell",),
        "experiment",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
    DemoProject("Wicker Obelisk", "studio", ("PHP",), "parked", "stale", "unknown"),
    DemoProject(
        "Xenon Parapet",
        "lab",
        ("Shell",),
        "manual-only",
        "recent",
        "unknown",
        has_ci=False,
    ),
    DemoProject(
        "Yarrow Spindle",
        "studio",
        ("Java",),
        "parked",
        "stale",
        "unknown",
        has_tests=False,
    ),
    DemoProject(
        "Zephyr Bastion",
        "lab",
        ("Perl",),
        "manual-only",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
    DemoProject(
        "Amber Thicket", "studio", ("Dart", "Flutter"), "parked", "recent", "unknown"
    ),
    DemoProject(
        "Bramble Cistern",
        "lab",
        ("R",),
        "experiment",
        "stale",
        "unknown",
        has_tests=False,
    ),
    DemoProject(
        "Cobalt Wharf",
        "studio",
        ("Scala",),
        "manual-only",
        "recent",
        "unknown",
        has_ci=False,
    ),
    DemoProject(
        "Dusk Pergola",
        "lab",
        ("OCaml",),
        "experiment",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
    DemoProject(
        "Errant Fathom", "studio", ("TypeScript",), "parked", "stale", "unknown"
    ),
    DemoProject(
        "Foxglove Mast",
        "lab",
        ("Nim",),
        "experiment",
        "recent",
        "unknown",
        has_tests=False,
    ),
    # Archived — present in the catalog, deferred by policy.
    DemoProject(
        "Gossamer Ridge",
        "archive",
        ("Python",),
        "archived",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
    DemoProject(
        "Hollow Tessera",
        "archive",
        ("JavaScript",),
        "archived",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
    DemoProject(
        "Indigo Palisade",
        "archive",
        ("Go",),
        "archived",
        "stale",
        "unknown",
        has_ci=False,
    ),
    DemoProject(
        "Jetty Marquee",
        "archive",
        ("Ruby",),
        "archived",
        "stale",
        "unknown",
        has_tests=False,
    ),
    DemoProject(
        "Kindling Arbor",
        "archive",
        ("C++",),
        "archived",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
    DemoProject(
        "Lattice Bezel",
        "archive",
        ("Swift",),
        "archived",
        "stale",
        "unknown",
        has_ci=False,
    ),
    DemoProject(
        "Mica Turnstile",
        "archive",
        ("Rust",),
        "archived",
        "stale",
        "unknown",
        has_tests=False,
    ),
    DemoProject(
        "Nocturne Spar",
        "archive",
        ("TypeScript",),
        "archived",
        "stale",
        "unknown",
        has_tests=False,
        has_ci=False,
    ),
)

_GROUP_LABELS = {
    "flagship": "Flagship Products",
    "platform": "Platform and Infrastructure",
    "studio": "Studio Projects",
    "lab": "Experiments Lab",
    "archive": "Archived",
}

_PURPOSES = {
    "flagship": "Operator-facing product surface with an active release lane.",
    "platform": "Shared platform service other demo projects depend on.",
    "studio": "Product experiment maintained on a manual cadence.",
    "lab": "Exploratory prototype kept for reference only.",
    "archive": "Archived project retained for historical continuity.",
}


def _slug(codename: str) -> str:
    return codename.lower().replace(" ", "-")


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def fixture_generated_at(now: datetime | None = None) -> datetime:
    """The fixture timestamp: recent enough that the consumer reads it fresh."""
    reference = now or datetime.now(timezone.utc)
    return reference.astimezone(timezone.utc) - timedelta(hours=FRESH_OFFSET_HOURS)


def _observed_provider(
    counts: dict[str, int], observed_at: str, *, zero_findings: bool
) -> dict[str, Any]:
    return {
        "state": "observed",
        "completed": True,
        "reason": "observed",
        "reason_code": "observed",
        "http_status": 200,
        "http_classification": "ok",
        "conditional": {"requested": True, "result": "modified"},
        "etag": None,
        "last_modified": None,
        "observed_at": observed_at,
        "pagination_complete": True,
        "counts": counts,
        "zero_findings": zero_findings,
    }


def _unavailable_provider(observed_at: str) -> dict[str, Any]:
    return {
        "state": "not_found",
        "completed": False,
        "reason": "github_not_found",
        "reason_code": "endpoint_unsupported",
        "http_status": 404,
        "http_classification": "github_not_found",
        "conditional": {"requested": False, "result": "failed"},
        "etag": None,
        "last_modified": None,
        "observed_at": observed_at,
        "pagination_complete": False,
        "counts": None,
        "zero_findings": None,
    }


def _security_block(
    spec: DemoProject, alerts: tuple[int, ...], observed_at: str
) -> dict[str, Any]:
    """Emit the 0.11 receipt-backed security block for one project."""
    dep_crit, dep_high, dep_med, dep_low, cs_crit, cs_high, secrets = alerts

    if spec.coverage == "unknown":
        return {
            "alerts_available": False,
            "coverage_state": "unknown",
            "cohort_member": False,
            "cohort_policy": "",
            "receipt_schema_version": "",
            "receipt_state": "unknown",
            "source_produced_at": "",
            "providers": {},
            "dependabot_critical": None,
            "dependabot_high": None,
            "dependabot_medium": None,
            "dependabot_low": None,
            "code_scanning_critical": None,
            "code_scanning_high": None,
            "secret_scanning_open": None,
            "open_high_critical": 0,
        }

    if spec.coverage == "stale":
        return {
            "alerts_available": False,
            "coverage_state": "stale",
            "cohort_member": True,
            "cohort_policy": COHORT_POLICY,
            "receipt_schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
            "receipt_state": "stale",
            "source_produced_at": observed_at,
            "providers": {},
            "dependabot_critical": None,
            "dependabot_high": None,
            "dependabot_medium": None,
            "dependabot_low": None,
            "code_scanning_critical": None,
            "code_scanning_high": None,
            "secret_scanning_open": None,
            "open_high_critical": 0,
        }

    dependabot = _observed_provider(
        {"critical": dep_crit, "high": dep_high, "medium": dep_med, "low": dep_low},
        observed_at,
        zero_findings=not any((dep_crit, dep_high, dep_med, dep_low)),
    )

    if spec.coverage == "partial":
        # Dependabot is observed; the other two endpoints are unavailable, which
        # is exactly why the combined coverage state stays partial.
        return {
            "alerts_available": False,
            "coverage_state": "partial",
            "cohort_member": True,
            "cohort_policy": COHORT_POLICY,
            "receipt_schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
            "receipt_state": "fresh",
            "source_produced_at": observed_at,
            "providers": {
                "dependabot": dependabot,
                "code_scanning": _unavailable_provider(observed_at),
                "secret_scanning": _unavailable_provider(observed_at),
            },
            "dependabot_critical": dep_crit,
            "dependabot_high": dep_high,
            "dependabot_medium": dep_med,
            "dependabot_low": dep_low,
            "code_scanning_critical": None,
            "code_scanning_high": None,
            "secret_scanning_open": None,
            "open_high_critical": dep_crit + dep_high,
        }

    return {
        "alerts_available": True,
        "coverage_state": "complete",
        "cohort_member": True,
        "cohort_policy": COHORT_POLICY,
        "receipt_schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
        "receipt_state": "fresh",
        "source_produced_at": observed_at,
        "providers": {
            "dependabot": dependabot,
            "code_scanning": _observed_provider(
                {"critical": cs_crit, "high": cs_high, "note": 0, "warning": 0},
                observed_at,
                zero_findings=not any((cs_crit, cs_high)),
            ),
            "secret_scanning": _observed_provider(
                {"open": secrets}, observed_at, zero_findings=secrets == 0
            ),
        },
        "dependabot_critical": dep_crit,
        "dependabot_high": dep_high,
        "dependabot_medium": dep_med,
        "dependabot_low": dep_low,
        "code_scanning_critical": cs_crit,
        "code_scanning_high": cs_high,
        "secret_scanning_open": secrets,
        "open_high_critical": dep_crit + dep_high + cs_crit + cs_high,
    }


def resolved_coverage_state(security: dict[str, Any]) -> str:
    """Mirror of the consumer's receipt gate, used to keep rollups honest.

    The consumer refuses to trust a declared coverage state whose receipt or
    provider evidence does not hold up. Computing rollups through the same gate
    means a malformed row can never produce a rollup the consumer disagrees
    with (which would surface as an operator-visible warning).
    """
    declared = (security.get("coverage_state") or "").strip()
    if declared == "stale":
        return "stale"
    if declared not in {"complete", "partial"}:
        return "unknown"
    if (
        security.get("receipt_schema_version") != GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION
        or security.get("receipt_state") != "fresh"
    ):
        return "unknown"

    required = {
        "dependabot": ("critical", "high"),
        "code_scanning": ("critical", "high"),
        "secret_scanning": ("open",),
    }
    providers = security.get("providers") or {}

    def observed(name: str) -> bool:
        provider = providers.get(name)
        if not isinstance(provider, dict):
            return False
        counts = provider.get("counts")
        if (
            provider.get("state") != "observed"
            or provider.get("pagination_complete") is not True
            or not isinstance(counts, dict)
        ):
            return False
        return all(
            isinstance(counts.get(key), int) and counts[key] >= 0
            for key in required[name]
        )

    if declared == "complete":
        return "complete" if all(observed(name) for name in required) else "unknown"
    return "partial" if any(observed(name) for name in required) else "unknown"


def _risk(
    spec: DemoProject, security: dict[str, Any], context_quality: str
) -> dict[str, Any]:
    open_high_critical = security.get("open_high_critical") or 0
    factors: list[str] = []
    if open_high_critical:
        factors.append(f"{open_high_critical} open high/critical security alerts")
    if not spec.has_tests:
        factors.append("no automated tests")
    if not spec.has_ci:
        factors.append("no CI workflow")
    if context_quality in {"minimum-viable", "boilerplate"}:
        factors.append("thin project context")
    if spec.activity == "stale" and spec.attention != "archived":
        factors.append("no meaningful activity in the recent window")
    if resolved_coverage_state(security) in {"stale", "unknown"}:
        factors.append("security coverage unobserved")

    if spec.attention == "archived":
        tier = "deferred"
    elif open_high_critical:
        tier = "elevated"
    elif spec.attention == "decision-needed" or len(factors) >= 3:
        tier = "moderate"
    else:
        tier = "baseline"

    summaries = {
        "elevated": "Open high or critical alerts need an operator decision.",
        "moderate": "Context or coverage gaps are worth closing this cycle.",
        "baseline": "No elevated pressure; routine cadence is sufficient.",
        "deferred": "Archived project; risk is accepted and not tracked.",
    }
    return {
        "risk_tier": tier,
        "risk_factors": factors,
        "risk_summary": summaries[tier],
        "security_risk": open_high_critical > 0,
        "doctor_gap": not spec.has_ci,
        "context_risk": context_quality in {"minimum-viable", "boilerplate"},
        "path_risk": spec.attention == "decision-needed",
    }


def _pressure_alerts(spec: DemoProject, index: int, pressure: int) -> tuple[int, ...]:
    """Scale a project's alert counts by historical backlog pressure.

    Older snapshots carry more open high alerts, so the trends view shows a real
    burndown curve instead of a flat line. Only receipt-backed rows can move —
    a row with no observation has no counts to scale.
    """
    if pressure <= 0 or spec.coverage not in {"complete", "partial"}:
        return spec.alerts
    extra = max(0, pressure - (index % 3))
    dep_crit, dep_high, dep_med, dep_low, cs_crit, cs_high, secrets = spec.alerts
    return (dep_crit, dep_high + extra, dep_med, dep_low, cs_crit, cs_high, secrets)


def build_projects(
    generated_at: datetime,
    *,
    pressure: int = 0,
    project_specs: tuple[DemoProject, ...] = DEMO_PROJECTS,
) -> list[dict[str, Any]]:
    """Build the synthetic project records for one point in time."""
    stamp = _iso(generated_at)
    projects: list[dict[str, Any]] = []
    for index, spec in enumerate(project_specs):
        slug = _slug(spec.codename)
        context_quality = (
            "none"
            if spec.attention == "archived"
            else _CONTEXT_QUALITY_CYCLE[index % len(_CONTEXT_QUALITY_CYCLE)]
        )
        operating_path, lifecycle_state = _ATTENTION_INTENT[spec.attention]
        security = _security_block(spec, _pressure_alerts(spec, index, pressure), stamp)
        context_files = ["AGENTS.md"]
        if context_quality in {"full", "standard"}:
            context_files.append("docs/current-state.md")
        if context_quality == "full":
            context_files.append("docs/architecture.md")
        has_minimum_context = context_quality in {
            "minimum-viable",
            "standard",
            "full",
        }

        projects.append(
            {
                "identity": {
                    "project_key": f"{spec.group}/{slug}",
                    "repo_full_name": f"{DEMO_ORG}/{slug}",
                    "display_name": spec.codename,
                    "path": f"{spec.group}/{slug}",
                    "section_marker": f"{spec.group}/",
                    "has_git": True,
                    "top_level_dir": spec.group,
                    "group_key": spec.group,
                    "group_label": _GROUP_LABELS[spec.group],
                    "section_label": _GROUP_LABELS[spec.group],
                    "default_branch": "main",
                },
                "declared": {
                    "operating_path": operating_path,
                    "category": spec.group,
                    "tool_provenance": "codex" if index % 2 else "claude-code",
                    "lifecycle_state": lifecycle_state,
                    "purpose": _PURPOSES[spec.group],
                    "owner": "demo-operator",
                    "team": "",
                    "criticality": "high" if spec.group == "flagship" else "medium",
                    "review_cadence": "weekly"
                    if spec.group == "flagship"
                    else "monthly",
                    "intended_disposition": "",
                    "maturity_program": "maintain",
                    "target_maturity": "operating",
                    "notes": "",
                    "doctor_standard": "",
                    "automation_eligible": context_quality
                    in {"minimum-viable", "boilerplate"},
                },
                "derived": {
                    "context_quality": context_quality,
                    "attention_state": spec.attention,
                    "activity_status": spec.activity,
                    "archived": spec.attention == "archived",
                    "stack": list(spec.stack),
                    "stack_present": has_minimum_context,
                    "context_files": context_files,
                    "context_file_count": len(context_files),
                    "primary_context_file": "AGENTS.md",
                    "project_summary_present": context_quality != "none",
                    "current_state_present": has_minimum_context,
                    "run_instructions_present": has_minimum_context,
                    "known_risks_present": has_minimum_context,
                    "next_recommended_move_present": has_minimum_context,
                    "last_meaningful_activity_at": _iso(
                        generated_at - timedelta(days=_ACTIVITY_AGE_DAYS[spec.activity])
                    ),
                    "has_tests": spec.has_tests,
                    "has_ci": spec.has_ci,
                    "has_license": spec.attention != "archived",
                    "readme_char_count": 900 + index * 137,
                    "release_count": 3 if spec.group == "flagship" else 0,
                    "path_override": "",
                    "path_confidence": "high" if spec.group == "flagship" else "medium",
                    "path_rationale": f"Stable path is {operating_path} from explicit operating path.",
                },
                "risk": _risk(spec, security, context_quality),
                "security": security,
                "advisory": {
                    "notion_portfolio_call": "",
                    "notion_momentum": "",
                    "notion_current_state": "",
                    "legacy_status": lifecycle_state,
                    "legacy_context_quality": context_quality,
                    "legacy_category": spec.group,
                    "legacy_tool_provenance": "",
                },
            }
        )
    return projects



def build_snapshot(
    generated_at: datetime,
    *,
    pressure: int = 0,
    project_specs: tuple[DemoProject, ...] = DEMO_PROJECTS,
) -> dict[str, Any]:
    """Build a complete portfolio-truth snapshot at the current schema."""
    projects = build_projects(
        generated_at,
        pressure=pressure,
        project_specs=project_specs,
    )

    coverage_states = Counter(
        resolved_coverage_state(project["security"]) for project in projects
    )
    attention = Counter(project["derived"]["attention_state"] for project in projects)
    activity = Counter(project["derived"]["activity_status"] for project in projects)
    context_quality = Counter(
        project["derived"]["context_quality"] for project in projects
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "derivation_policy_version": DERIVATION_POLICY_VERSION,
        "generated_at": _iso(generated_at),
        "workspace_root": DEMO_WORKSPACE_ROOT,
        # Synthetic demo output is not emitted by an attested producer checkout.
        # Canonical truth represents absent evidence as an empty object; partial
        # invented evidence would fail the publication contract.
        "producer": {},
        "source_summary": {
            "workspace_root": DEMO_WORKSPACE_ROOT,
            "project_count": len(projects),
            "catalog_errors": [],
            "catalog_warnings": [],
            "legacy_registry_rows": len(projects),
            "notion_context_rows": 0,
            "notion_context_carried_forward": 0,
            "context_quality_counts": dict(context_quality),
            "activity_status_counts": dict(activity),
            "attention_state_counts": dict(attention),
            "archived_count": attention.get("archived", 0),
            "github_archived_count": 0,
            "duplicate_display_names": [],
            "unresolved_duplicate_display_names": [],
        },
        "precedence_matrix": {
            "identity": ["demo fixture"],
            "declared": ["demo fixture"],
            "derived": ["demo fixture"],
            "risk": ["demo fixture"],
            "security": ["demo fixture receipt"],
        },
        "coverage": [
            {
                "source": "workspace",
                "state": "observed",
                "project_count": len(projects),
            },
            {
                "source": "github_security",
                "state": "partial",
                "project_count": len(projects),
                "complete_repo_count": coverage_states.get("complete", 0),
                "partial_repo_count": coverage_states.get("partial", 0),
                "stale_count": coverage_states.get("stale", 0),
                "unknown_count": coverage_states.get("unknown", 0),
            },
        ],
        "exclusions": {
            "policy_version": "workspace_discovery.v2",
            "counts": {},
        },
        "inputs": {
            "catalog": {
                "source_id": "portfolio-catalog",
                "sha256": None,
                "observed_at": _iso(generated_at),
            },
            "workspace": {
                "source_id": "projects-root",
                "observed_at": _iso(generated_at),
            },
            "notion": {
                "mode": "unavailable",
                "observed_at": None,
                "carried_from_generated_at": None,
            },
        },
        "warnings": [],
        "projects": projects,
    }
    from src.portfolio_truth_validate import canonicalize_truth_snapshot_payload

    return canonicalize_truth_snapshot_payload(payload)


def history_snapshots(generated_at: datetime) -> list[tuple[str, dict[str, Any]]]:
    """Timestamped snapshots for the trends view, oldest first.

    Filenames are stable across regenerations (the timestamp lives in the
    payload, which is what the consumer plots), so the proof package can
    reference them without breaking every time the fixture is rebuilt.
    """
    snapshots: list[tuple[str, dict[str, Any]]] = []
    for step in range(HISTORY_POINTS):
        age = HISTORY_POINTS - 1 - step
        moment = generated_at - timedelta(days=HISTORY_INTERVAL_DAYS * age)
        snapshots.append(
            (
                f"portfolio-truth-history-{step + 1:02d}.json",
                build_snapshot(moment, pressure=age),
            )
        )
    return snapshots


def build_weekly_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Operator weekly digest derived from the synthetic snapshot."""
    projects = snapshot["projects"]
    rollups = snapshot["rollups"]
    elevated = [p for p in projects if p["risk"]["risk_tier"] == "elevated"]
    open_alerts = sorted(
        (p for p in projects if (p["security"]["open_high_critical"] or 0) > 0),
        key=lambda p: p["security"]["open_high_critical"],
        reverse=True,
    )
    lead = (
        open_alerts[0]["identity"]["display_name"] if open_alerts else "the portfolio"
    )
    return {
        "username": "demo-operator",
        "generated_at": snapshot["generated_at"],
        "headline": f"{len(elevated)} projects carry open high or critical alerts.",
        "decision": f"Clear {lead} before starting lower-pressure cleanup.",
        "why_this_week": (
            f"{lead} holds the largest observed alert backlog and is the only "
            "flagship blocked on a security decision."
        ),
        "next_step": "Open the burndown view, confirm the grouped fix, then record the decision.",
        "risk_posture": {
            "elevated_count": len(elevated),
            "risk_tier_counts": rollups["risk_tier_counts"],
            "top_elevated": [
                {
                    "repo": p["identity"]["project_key"],
                    "risk_tier": p["risk"]["risk_tier"],
                    "risk_summary": p["risk"]["risk_summary"],
                }
                for p in elevated[:5]
            ],
        },
        "security_posture": {
            "scanned_count": rollups["security"]["scanned_count"],
            "repos_with_open_high_critical": rollups["security"][
                "repos_with_open_high_critical"
            ],
            "total_open_critical": rollups["security"]["total_open_critical"],
            "total_open_high": rollups["security"]["total_open_high"],
            "top_alerts": [
                {
                    "repo": p["identity"]["project_key"],
                    "risk_tier": p["risk"]["risk_tier"],
                    "dependabot_critical": p["security"]["dependabot_critical"],
                    "dependabot_high": p["security"]["dependabot_high"],
                }
                for p in open_alerts[:5]
            ],
        },
        "path_attention": [
            {
                "repo": p["identity"]["project_key"],
                "headline": p["risk"]["risk_summary"],
                "activity_status": p["derived"]["activity_status"],
                "context_quality": p["derived"]["context_quality"],
            }
            for p in projects
            if p["derived"]["attention_state"] == "decision-needed"
        ],
    }


def build_security_burndown(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Advisory-grouped fix list over the synthetic receipt-backed rows."""
    affected = [
        p["identity"]["display_name"]
        for p in snapshot["projects"]
        if (p["security"]["open_high_critical"] or 0) > 0
    ]
    entries = [
        {
            "package": "demo-crypto-core",
            "ecosystem": "pip",
            "severity": "critical",
            "ghsa_id": "GHSA-DEMO-0001",
            "first_patched_version": "3.1.0",
            "affected_repos": affected[:3],
            "affected_repo_count": len(affected[:3]),
        },
        {
            "package": "demo-ui-kit",
            "ecosystem": "npm",
            "severity": "high",
            "ghsa_id": "GHSA-DEMO-0002",
            "first_patched_version": "4.1.0",
            "affected_repos": affected[:5],
            "affected_repo_count": len(affected[:5]),
        },
        {
            "package": "demo-transport",
            "ecosystem": "cargo",
            "severity": "high",
            "ghsa_id": "GHSA-DEMO-0003",
            "first_patched_version": "0.9.2",
            "affected_repos": affected[2:6],
            "affected_repo_count": len(affected[2:6]),
        },
    ]
    return {
        "distinct_advisories": len(entries),
        "total_repo_instances": sum(entry["affected_repo_count"] for entry in entries),
        "repos_touched": len(affected),
        "entries": entries,
    }


def build_proposals(generated_at: datetime) -> dict[str, Any]:
    """A mixed-state bounded-automation queue for the triage view."""
    created = _iso(generated_at - timedelta(days=1))
    acted = _iso(generated_at - timedelta(hours=3))
    proposals = [
        {
            "proposal_id": "demo-proposal-0001",
            "action_type": "context-pr",
            "display_name": "Solstice Cairn",
            "repo_full_name": f"{DEMO_ORG}/solstice-cairn",
            "description": "Open an auto-PR improving the managed context block for Solstice Cairn.",
            "status": "pending",
            "created_at": created,
            "approved_at": "",
            "approved_by": "",
            "rejected_at": "",
            "executed_at": "",
            "execution_ref": "",
        },
        {
            "proposal_id": "demo-proposal-0002",
            "action_type": "catalog-seed",
            "display_name": "Tabard Anvil",
            "repo_full_name": f"{DEMO_ORG}/tabard-anvil",
            "description": "Apply catalog seed updates for Tabard Anvil.",
            "status": "approved",
            "created_at": created,
            "approved_at": acted,
            "approved_by": "demo-operator",
            "rejected_at": "",
            "executed_at": "",
            "execution_ref": "",
        },
        {
            "proposal_id": "demo-proposal-0003",
            "action_type": "context-pr",
            "display_name": "Umbra Trellis",
            "repo_full_name": f"{DEMO_ORG}/umbra-trellis",
            "description": "Open an auto-PR improving the managed context block for Umbra Trellis.",
            "status": "rejected",
            "created_at": created,
            "approved_at": "",
            "approved_by": "",
            "rejected_at": acted,
            "executed_at": "",
            "execution_ref": "",
        },
        {
            "proposal_id": "demo-proposal-0004",
            "action_type": "catalog-seed",
            "display_name": "Vellum Compass",
            "repo_full_name": f"{DEMO_ORG}/vellum-compass",
            "description": "Apply catalog seed updates for Vellum Compass.",
            "status": "executed",
            "created_at": created,
            "approved_at": acted,
            "approved_by": "demo-operator",
            "rejected_at": "",
            "executed_at": _iso(generated_at - timedelta(hours=2)),
            "execution_ref": "demo-run-0004",
        },
    ]
    return {"contract_version": "automation_proposals_v1", "proposals": proposals}
