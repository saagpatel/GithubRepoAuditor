from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.12.0"
# 0.12.0: additive contract envelope identifies the canonical artifact and
# compatibility class while retaining schema_version for legacy consumers.
# 0.11.0: provenance-bearing GitHub security receipts preserve per-provider
# states and expose complete/partial/stale/unknown coverage denominators.
# 0.10.0: canonical producer receipts bind the exact checkout; coverage and
# repository/worktree observation envelopes fail closed on unavailable evidence.
# 0.8.0: derived.registry_status removed (was a stale->parked synonym table over
# activity_status); derived.archived added as a first-class lifecycle boolean;
# source_summary.registry_status_counts replaced by activity_status_counts + archived_count.
LEGACY_SCHEMA_VERSIONS = {"0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0"}
DERIVATION_POLICY_VERSION = "portfolio_attention.v3"
PORTFOLIO_TRUTH_CONTRACT_ID = "ghra.portfolio_truth"
PORTFOLIO_TRUTH_COMPATIBILITY = "additive"

# The published "latest" portfolio-truth artifact. The producer
# (portfolio_truth_publish) writes it; every reader resolves it through
# truth_latest_path() so the filename lives in exactly one place.
TRUTH_LATEST_FILENAME = "portfolio-truth-latest.json"


def truth_latest_path(output_dir: Path) -> Path:
    """Resolve the canonical portfolio-truth-latest.json under an output dir."""
    return output_dir / TRUTH_LATEST_FILENAME


VALID_CONTEXT_QUALITY = {"full", "standard", "minimum-viable", "boilerplate", "none"}
# Pure recency observation. Lifecycle intent (archived) is a separate axis —
# see DerivedFields.archived and display_activity_status() below.
VALID_ACTIVITY_STATUS = {"active", "recent", "stale"}
VALID_ATTENTION_STATES = {
    "active-product",
    "active-infra",
    "decision-needed",
    "parked",
    "archived",
    "experiment",
    "evidence-history",
    "manual-only",
}
VALID_LIFECYCLE_STATES = {
    "active",
    "maintenance",
    "manual-only",
    "dormant",
    "experimental",
    "archived",
}
VALID_CATEGORY_TAGS = {
    "commercial",
    "it-work",
    "vanity",
    "fun",
    "learning",
    "infrastructure",
    "unknown",
}
VALID_TOOL_PROVENANCE = {"claude-code", "codex", "gpt", "grok", "claude-ai", "unknown"}
VALID_RISK_TIERS = {"elevated", "moderate", "baseline", "deferred"}
VALID_DOCTOR_STANDARDS = {"full", "basic"}


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def display_activity_status(activity_status: str, *, archived: bool) -> str:
    """The single legitimate place `stale` (an observation) is relabeled `parked` (a
    lifecycle judgment) for human-facing surfaces. `archived` is a stored lifecycle fact,
    not a relabel, and always wins. Every renderer/report that used to read
    ``derived.registry_status`` for display calls this instead of re-deriving the label."""
    if archived:
        return "archived"
    if activity_status == "stale":
        return "parked"
    return activity_status


@dataclass(frozen=True)
class IdentityFields:
    project_key: str
    display_name: str
    path: str
    top_level_dir: str
    group_key: str
    group_label: str
    section_marker: str
    section_label: str
    has_git: bool
    # GitHub "owner/repo" from the local git remote, when present. Lets risk and
    # other truth-keyed overlays be matched by the GitHub repo name (audit
    # metadata.name) and not only the local-dir display_name, which often differ
    # (e.g. "Signal & Noise" vs "signal-noise").
    repo_full_name: str = ""
    # The repo's default branch (from local ``origin/HEAD``), when detectable.
    # Empty when not set locally; consumers fall back to the portfolio default.
    default_branch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class DeclaredFields:
    owner: str = ""
    team: str = ""
    purpose: str = ""
    lifecycle_state: str = ""
    criticality: str = ""
    review_cadence: str = ""
    # Deprecated vintage of `operating_path` (same axis, same value domain). The
    # catalog was migrated to declare `operating_path` directly in 0.9.x; this field
    # is kept as a read-compat fallback for one release and then deleted. See
    # portfolio_pathing.resolve_declared_operating_path and CHANGELOG.
    intended_disposition: str = ""
    maturity_program: str = ""
    target_maturity: str = ""
    operating_path: str = ""
    category: str = ""
    tool_provenance: str = ""
    notes: str = ""
    doctor_standard: str = ""
    automation_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class DerivedFields:
    stack: list[str] = field(default_factory=list)
    context_quality: str = "none"
    context_files: list[str] = field(default_factory=list)
    context_file_count: int = 0
    primary_context_file: str = "AGENTS.md"
    project_summary_present: bool = False
    current_state_present: bool = False
    stack_present: bool = False
    run_instructions_present: bool = False
    known_risks_present: bool = False
    next_recommended_move_present: bool = False
    last_meaningful_activity_at: datetime | None = None
    activity_status: str = "stale"
    # Lifecycle fact, not a recency observation: github_archived OR declared
    # lifecycle_state == "archived". Orthogonal to activity_status.
    archived: bool = False
    attention_state: str = "parked"
    path_override: str = ""
    path_confidence: str = "legacy"
    path_rationale: str = ""
    # Strict local-filesystem signals (Sprint 8.2)
    has_tests: bool = False
    has_ci: bool = False
    has_license: bool = False
    readme_char_count: int = 0
    # Opt-in: populated from prior warehouse audit via --portfolio-truth-include-release-count
    release_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["last_meaningful_activity_at"] = _serialize_datetime(
            self.last_meaningful_activity_at
        )
        return data


@dataclass(frozen=True)
class AdvisoryFields:
    notion_portfolio_call: str = ""
    notion_momentum: str = ""
    notion_current_state: str = ""
    legacy_status: str = ""
    legacy_context_quality: str = ""
    legacy_category: str = ""
    legacy_tool_provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class RiskFields:
    risk_tier: str = "baseline"
    risk_factors: list[str] = field(default_factory=list)
    risk_summary: str = ""
    doctor_gap: bool = False
    context_risk: bool = False
    path_risk: bool = False
    security_risk: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class SecurityFields:
    """Receipt-backed GitHub security coverage with compatibility count fields.

    ``alerts_available`` remains for older consumers, but now means all three
    providers were freshly and completely observed.  Provider-specific states in
    ``providers`` are the authority for partial or unavailable coverage.
    """

    alerts_available: bool = False
    coverage_state: str = "unknown"
    cohort_member: bool = False
    cohort_policy: str = ""
    receipt_schema_version: str = ""
    receipt_state: str = "unknown"
    source_produced_at: str = ""
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    dependabot_critical: int | None = None
    dependabot_high: int | None = None
    dependabot_medium: int | None = None
    dependabot_low: int | None = None
    code_scanning_critical: int | None = None
    code_scanning_high: int | None = None
    secret_scanning_open: int | None = None

    @property
    def open_high_critical(self) -> int:
        """Dependabot high + critical — the security-risk-factor trigger surface."""
        return (self.dependabot_high or 0) + (self.dependabot_critical or 0)

    def provider_state(self, provider: str) -> str:
        data = self.providers.get(provider) or {}
        state = data.get("state")
        return state if isinstance(state, str) else "not_requested"

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["open_high_critical"] = self.open_high_critical
        return data


@dataclass(frozen=True)
class PortfolioTruthProject:
    identity: IdentityFields
    declared: DeclaredFields
    derived: DerivedFields
    risk: RiskFields = field(default_factory=RiskFields)
    security: SecurityFields = field(default_factory=SecurityFields)
    advisory: AdvisoryFields = field(default_factory=AdvisoryFields)
    repository_state: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "declared": self.declared.to_dict(),
            "derived": self.derived.to_dict(),
            "risk": self.risk.to_dict(),
            "security": self.security.to_dict(),
            "advisory": self.advisory.to_dict(),
            "repository_state": dict(self.repository_state),
            "provenance": self.provenance,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PortfolioTruthRollups:
    """Portfolio-level aggregates derived from the project list, emitted so
    downstream consumers (command-center, dashboards) read them instead of
    re-deriving the auditor's risk/security logic, which is the #1 drift risk."""

    risk_tier_counts: dict[str, int]
    security: dict[str, int | str]
    decision: dict[str, int]

    @classmethod
    def from_projects(
        cls, projects: list[PortfolioTruthProject]
    ) -> PortfolioTruthRollups:
        risk_tier_counts = {
            "elevated": 0,
            "moderate": 0,
            "baseline": 0,
            "deferred": 0,
        }
        scanned_count = 0
        repos_with_open_high_critical = 0
        total_open_high = 0
        total_open_critical = 0
        unavailable_count = 0
        complete_repo_count = 0
        partial_repo_count = 0
        stale_count = 0
        unknown_count = 0
        cohort_repository_count = 0
        cohort_complete_count = 0
        cohort_partial_count = 0
        cohort_stale_count = 0
        cohort_unknown_count = 0
        dependabot_observed_count = 0
        code_scanning_observed_count = 0
        secret_scanning_observed_count = 0
        decision_needed_count = 0
        default_attention_count = 0
        for project in projects:
            tier = project.risk.risk_tier
            if tier in risk_tier_counts:
                risk_tier_counts[tier] += 1
            if not project.identity.project_key.startswith("supp:"):
                security = project.security
                if security.cohort_member:
                    cohort_repository_count += 1
                provider_states = {
                    provider: security.provider_state(provider)
                    for provider in ("dependabot", "code_scanning", "secret_scanning")
                }
                dependabot_observed = provider_states["dependabot"] == "observed"
                if dependabot_observed:
                    dependabot_observed_count += 1
                    if security.open_high_critical > 0:
                        repos_with_open_high_critical += 1
                    total_open_high += security.dependabot_high or 0
                    total_open_critical += security.dependabot_critical or 0
                if provider_states["code_scanning"] == "observed":
                    code_scanning_observed_count += 1
                if provider_states["secret_scanning"] == "observed":
                    secret_scanning_observed_count += 1
                if security.coverage_state == "complete":
                    complete_repo_count += 1
                    scanned_count += 1
                    if security.cohort_member:
                        cohort_complete_count += 1
                elif security.coverage_state == "partial":
                    partial_repo_count += 1
                    if security.cohort_member:
                        cohort_partial_count += 1
                elif security.coverage_state == "stale":
                    stale_count += 1
                    if security.cohort_member:
                        cohort_stale_count += 1
                else:
                    unknown_count += 1
                    if security.cohort_member:
                        cohort_unknown_count += 1
                if not security.alerts_available:
                    unavailable_count += 1
            attention = project.derived.attention_state
            if attention == "decision-needed":
                decision_needed_count += 1
                default_attention_count += 1
            elif attention in ("active-product", "active-infra"):
                default_attention_count += 1
        return cls(
            risk_tier_counts=risk_tier_counts,
            security={
                "scanned_count": scanned_count,
                "unavailable_count": unavailable_count,
                "complete_repo_count": complete_repo_count,
                "partial_repo_count": partial_repo_count,
                "stale_count": stale_count,
                "unknown_count": unknown_count,
                "cohort_repository_count": cohort_repository_count,
                "cohort_complete_count": cohort_complete_count,
                "cohort_partial_count": cohort_partial_count,
                "cohort_stale_count": cohort_stale_count,
                "cohort_unknown_count": cohort_unknown_count,
                "dependabot_observed_count": dependabot_observed_count,
                "code_scanning_observed_count": code_scanning_observed_count,
                "secret_scanning_observed_count": secret_scanning_observed_count,
                "coverage_state": (
                    "known"
                    if unavailable_count == 0
                    else "partial"
                    if complete_repo_count or partial_repo_count
                    else "unknown"
                ),
                "repos_with_open_high_critical": repos_with_open_high_critical,
                "total_open_high": total_open_high,
                "total_open_critical": total_open_critical,
            },
            decision={
                "decision_needed_count": decision_needed_count,
                "default_attention_count": default_attention_count,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_tier_counts": dict(self.risk_tier_counts),
            "security": dict(self.security),
            "decision": dict(self.decision),
        }


@dataclass(frozen=True)
class PortfolioTruthSnapshot:
    schema_version: str
    generated_at: datetime
    workspace_root: str
    source_summary: dict[str, Any]
    precedence_matrix: dict[str, list[str]]
    warnings: list[str]
    projects: list[PortfolioTruthProject]
    derivation_policy_version: str = DERIVATION_POLICY_VERSION
    producer: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    coverage: list[dict[str, Any]] = field(default_factory=list)
    exclusions: dict[str, Any] = field(
        default_factory=lambda: {
            "policy_version": "workspace_discovery.v2",
            "counts": {},
        }
    )
    rollups: PortfolioTruthRollups = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "rollups", PortfolioTruthRollups.from_projects(self.projects)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract": {
                "id": PORTFOLIO_TRUTH_CONTRACT_ID,
                "version": self.schema_version,
                "compatibility": PORTFOLIO_TRUTH_COMPATIBILITY,
            },
            "generated_at": _serialize_datetime(self.generated_at),
            "derivation_policy_version": self.derivation_policy_version,
            "producer": dict(self.producer),
            "inputs": dict(self.inputs),
            "coverage": list(self.coverage),
            "exclusions": dict(self.exclusions),
            "workspace_root": self.workspace_root,
            "source_summary": self.source_summary,
            "precedence_matrix": self.precedence_matrix,
            "warnings": list(self.warnings),
            "projects": [project.to_dict() for project in self.projects],
            "rollups": self.rollups.to_dict(),
        }
