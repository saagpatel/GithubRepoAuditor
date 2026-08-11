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

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.github_security_coverage import (
    GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
    _remote_repository_result,
)
from src.portfolio_repository_state import _observed_result
from src.portfolio_pathing import build_operating_path_entry
from src.portfolio_truth_coverage import build_coverage_envelope
from src.portfolio_truth_decisions import build_project_decision
from src.portfolio_truth_metadata import (
    build_exclusions,
    build_input_envelope,
    build_source_summary,
    build_warnings,
)
from src.portfolio_truth_precedence import build_precedence_matrix
from src.portfolio_truth_provenance import REQUIRED_PROJECT_PROVENANCE_KEYS
from src.portfolio_truth_types import DERIVATION_POLICY_VERSION, SCHEMA_VERSION
from src.security_admission import derive_security_admission

# The demo workspace is deliberately not a real filesystem path.
DEMO_WORKSPACE_ROOT = "/demo-workspace"
DEMO_ORG = "demo-org"
COHORT_POLICY = "portfolio-default-attention-v1"
DEMO_SECURITY_PRODUCER_COMMIT = "a" * 40

# Hours between the fixture timestamp and generation time. Comfortably inside
# the consumer's 48h "fresh" band, and far enough from zero to look like a real
# overnight run rather than a synthetic instant.
FRESH_OFFSET_HOURS = 6
STALE_RECEIPT_AGE_HOURS = 25

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

_GROUP_CATEGORIES = {
    "flagship": "commercial",
    "platform": "infrastructure",
    "studio": "fun",
    "lab": "learning",
    "archive": "it-work",
}


def _category_for(spec: DemoProject) -> str:
    if spec.attention == "active-infra":
        return "infrastructure"
    if spec.attention == "active-product":
        return "commercial"
    return _GROUP_CATEGORIES[spec.group]


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
        "reason": None,
        "reason_code": "observed",
        "http_status": 200,
        "http_classification": "success",
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


def _stale_provider(observed_at: str) -> dict[str, Any]:
    return {
        "state": "stale",
        "completed": False,
        "reason": "receipt_stale",
        "reason_code": "stale_observation",
        "http_status": 200,
        "http_classification": "success",
        "conditional": {"requested": True, "result": "modified"},
        "etag": None,
        "last_modified": None,
        "observed_at": observed_at,
        "pagination_complete": True,
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
        source_produced_at = _iso(
            datetime.fromisoformat(observed_at)
            - timedelta(hours=STALE_RECEIPT_AGE_HOURS)
        )
        return {
            "alerts_available": False,
            "coverage_state": "stale",
            "cohort_member": True,
            "cohort_policy": COHORT_POLICY,
            "receipt_schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
            "receipt_state": "stale",
            "source_produced_at": source_produced_at,
            "providers": {
                name: _stale_provider(source_produced_at)
                for name in ("dependabot", "code_scanning", "secret_scanning")
            },
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
        "open_high_critical": dep_crit + dep_high,
    }


def _repository_state(
    *,
    group: str,
    slug: str,
    observed_at: str,
    security: dict[str, Any],
) -> dict[str, Any]:
    source_produced_at = security["source_produced_at"]
    if security["receipt_state"] == "stale":
        remote = _remote_repository_result(
            state="stale",
            observed_at=source_produced_at,
            reason="receipt_stale",
        )
    elif security["receipt_schema_version"]:
        remote = _remote_repository_result(
            state="observed",
            observed_at=source_produced_at,
            reason=None,
            default_branch="main",
            head_sha=hashlib.sha256(f"{DEMO_ORG}/{slug}".encode()).hexdigest(),
            archived=False,
        )
    else:
        remote = {
            "state": "unknown",
            "reason_code": "not_requested",
            "reason": (
                "no independent live remote read was performed by portfolio generation"
            ),
        }
    path = f"{DEMO_WORKSPACE_ROOT}/{group}/{slug}"
    head = remote.get("head_sha") or hashlib.sha256(path.encode()).hexdigest()
    local = {
        "path": path,
        "head": head,
        "branch": "main",
        "dirty": False,
        "dirty_path_count": 0,
        "upstream": "origin/main",
        "upstream_branch": "main",
        "upstream_remote": "origin",
        "upstream_observation_source": "local_tracking_ref",
        "ahead": 0,
        "behind": 0,
    }
    worktree = {
        "state": "observed",
        **local,
        "detached": False,
        "bare": False,
    }
    if remote["state"] == "observed":
        selection = {
            "source": remote["source"],
            "state": "selected",
            "reason_code": "unique_remote_head_match",
            "reason": None,
            "candidate_count": 1,
            "path": path,
            "head": head,
            "branch": "main",
        }
    else:
        selection = {
            "source": remote.get("source", "remote_default_branch"),
            "state": "unknown",
            "reason_code": "remote_default_branch_unavailable",
            "reason": (
                "independent remote-default evidence is not observed "
                f"(state={remote['state']})"
            ),
            "candidate_count": 0,
        }
    topology = {
        "kind": "working_repository",
        "configured_path": path,
        "worktree_count": 1,
        "linked_worktree_count": 0,
        "selection": selection,
    }
    return _observed_result(
        observed_at=datetime.fromisoformat(observed_at),
        remote=remote,
        worktrees=[worktree],
        topology=topology,
        local=local,
    )


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
        declared_operating_path, lifecycle_state = _ATTENTION_INTENT[spec.attention]
        archived = spec.attention == "archived"
        security = _security_block(spec, _pressure_alerts(spec, index, pressure), stamp)
        repository_state = _repository_state(
            group=spec.group,
            slug=slug,
            observed_at=stamp,
            security=security,
        )
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
        declared = {
            "operating_path": declared_operating_path,
            "category": _category_for(spec),
            "tool_provenance": "codex" if index % 2 else "claude-code",
            "lifecycle_state": lifecycle_state,
            "purpose": _PURPOSES[spec.group],
            "owner": "demo-operator",
            "team": "",
            "criticality": "high" if spec.group == "flagship" else "medium",
            "review_cadence": "weekly" if spec.group == "flagship" else "monthly",
            "intended_disposition": "",
            "maturity_program": "maintain",
            "target_maturity": "operating",
            "notes": "",
            "doctor_standard": "",
            "automation_eligible": context_quality in {"minimum-viable", "boilerplate"},
        }
        path_entry = build_operating_path_entry(
            {**declared, "has_explicit_entry": True},
            context_quality=context_quality,
            archived=archived,
        )
        operating_path = str(path_entry["operating_path"])
        path_override = str(path_entry["path_override"])
        declared["operating_path"] = operating_path
        derived = {
            "context_quality": context_quality,
            "activity_status": spec.activity,
            "archived": archived,
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
            "path_override": path_override,
            "path_confidence": path_entry["path_confidence"],
            "path_rationale": path_entry["path_rationale"],
        }
        security_admission = derive_security_admission(security)
        risk, attention_state = build_project_decision(
            display_name=spec.codename,
            operating_path=operating_path,
            path_override=path_override,
            context_quality=context_quality,
            activity_status=spec.activity,
            archived=derived["archived"],
            lifecycle_state=lifecycle_state,
            category=declared["category"],
            criticality=declared["criticality"],
            doctor_standard=declared["doctor_standard"],
            known_risks_present=derived["known_risks_present"],
            run_instructions_present=derived["run_instructions_present"],
            security_coverage_state=security_admission.effective_coverage_state,
            security_high_alerts=security_admission.total_open_high,
            security_critical_alerts=(
                security_admission.total_open_critical
                + security_admission.total_open_secrets
            ),
        )
        derived["attention_state"] = attention_state
        provenance_values = {
            "declared": declared,
            "derived": derived,
            "risk": risk,
        }
        provenance: dict[str, dict[str, str]] = {}
        for key in sorted(REQUIRED_PROJECT_PROVENANCE_KEYS):
            section, field = key.split(".", 1)
            value = provenance_values[section][field]
            if key == "derived.context_files":
                detail = str(len(value))
            elif isinstance(value, bool):
                detail = str(value).lower()
            elif isinstance(value, list):
                detail = ", ".join(str(item) for item in value)
            else:
                detail = str(value)
            provenance[key] = {"source": "demo-fixture", "detail": detail}
        provenance.update(
            {
                "declared.operating_path": {
                    "source": "normalized",
                    "detail": str(path_entry["operating_path_source"]),
                },
                "derived.path_override": {
                    "source": "normalized",
                    "detail": path_override,
                },
                "derived.path_confidence": {
                    "source": "normalized",
                    "detail": str(path_entry["path_confidence"]),
                },
                "derived.path_rationale": {
                    "source": "normalized",
                    "detail": str(path_entry["path_rationale"]),
                },
                "risk.risk_tier": {
                    "source": "derived",
                    "detail": str(risk["risk_tier"]),
                },
                "risk.doctor_gap": {
                    "source": "derived",
                    "detail": str(risk["doctor_gap"]).lower(),
                },
            }
        )

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
                "declared": declared,
                "derived": derived,
                "risk": risk,
                "security": security,
                "repository_state": repository_state,
                "provenance": provenance,
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
    projects.sort(
        key=lambda item: (
            item["identity"]["section_marker"].lower(),
            item["identity"]["display_name"].lower(),
        )
    )

    source_summary = build_source_summary(
        workspace_root=DEMO_WORKSPACE_ROOT,
        projects=projects,
        catalog_errors=[],
        catalog_warnings=[],
        legacy_registry_rows=len(projects),
        notion_context_rows=0,
        notion_context_carried_forward=False,
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
        "source_summary": source_summary,
        "precedence_matrix": build_precedence_matrix(),
        "coverage": build_coverage_envelope(
            projects=projects,
            notion_context_carried_forward=False,
            notion_context_rows=0,
        ),
        "exclusions": build_exclusions({}),
        "inputs": build_input_envelope(
            workspace_root=DEMO_WORKSPACE_ROOT,
            catalog_path=None,
            now=generated_at,
            include_notion=False,
            notion_context_rows=0,
            notion_context_carried_forward=False,
            prior_notion_generated_at=None,
            notion_source_mode="unavailable",
            notion_observed_at=None,
            security_coverage_metadata={
                "source_id": "github-security-coverage-receipt",
                "schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
                "produced_at": _iso(generated_at),
                "state": "fresh",
                "age_hours": 0.0,
                "producer_commit": DEMO_SECURITY_PRODUCER_COMMIT,
                "cohort_policy": COHORT_POLICY,
                "cohort_repository_count": sum(
                    project["security"]["cohort_member"] for project in projects
                ),
                "path": "/demo-workspace/github-security-coverage.json",
                "receipt_id": "sha256:" + "b" * 64,
                "content_sha256": "b" * 64,
            },
        ),
        "warnings": build_warnings(
            catalog_errors=[],
            catalog_warnings=[],
            unresolved_duplicates=[],
        ),
        "projects": projects,
    }
    from src.portfolio_truth_validate import canonicalize_truth_snapshot_payload

    return canonicalize_truth_snapshot_payload(
        payload,
        allow_synthetic_security_matrix=True,
    )


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
    admitted_security = [
        (p, derive_security_admission(p["security"]))
        for p in projects
        if p["security"].get("cohort_member")
    ]
    blocking = sorted(
        (
            (p, admission)
            for p, admission in admitted_security
            if admission.has_findings
        ),
        key=lambda item: (
            -(
                item[1].total_open_critical
                + item[1].total_open_secrets
                + item[1].total_open_high
            ),
            item[0]["identity"]["display_name"],
        ),
    )
    lead = blocking[0][0]["identity"]["display_name"] if blocking else "the portfolio"
    admission_status_counts: dict[str, int] = {}
    for _, admission in admitted_security:
        admission_status_counts[admission.status] = (
            admission_status_counts.get(admission.status, 0) + 1
        )
    return {
        "username": "demo-operator",
        "generated_at": snapshot["generated_at"],
        "headline": (
            f"{len(blocking)} projects carry blocking GitHub security findings."
        ),
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
            "scanned_count": sum(
                admission.evidence_complete for _, admission in admitted_security
            ),
            "repos_with_open_high_critical": len(blocking),
            "repos_with_blocking_findings": len(blocking),
            "unadmitted_count": sum(
                not admission.evidence_complete for _, admission in admitted_security
            ),
            "admission_status_counts": admission_status_counts,
            "total_open_critical": sum(
                admission.total_open_critical for _, admission in admitted_security
            ),
            "total_open_high": sum(
                admission.total_open_high for _, admission in admitted_security
            ),
            "total_open_secrets": sum(
                admission.total_open_secrets for _, admission in admitted_security
            ),
            "top_alerts": [
                {
                    "repo": p["identity"]["project_key"],
                    "risk_tier": p["risk"]["risk_tier"],
                    "dependabot_critical": admission.dependabot_critical,
                    "dependabot_high": admission.dependabot_high,
                    "code_scanning_critical": admission.code_scanning_critical,
                    "code_scanning_high": admission.code_scanning_high,
                    "secret_scanning_open": admission.secret_scanning_open,
                    "total_open_critical": admission.total_open_critical,
                    "total_open_high": admission.total_open_high,
                    "security_admission_status": admission.status,
                    "security_admission_evidence_complete": (
                        admission.evidence_complete
                    ),
                    "security_admission_reason_codes": list(admission.reason_codes),
                }
                for p, admission in blocking[:5]
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
