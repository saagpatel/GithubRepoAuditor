from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "0.4.0"

VALID_CONTEXT_QUALITY = {"full", "standard", "minimum-viable", "boilerplate", "none"}
VALID_ACTIVITY_STATUS = {"active", "recent", "stale", "archived"}
VALID_REGISTRY_STATUS = {"active", "recent", "parked", "archived"}
VALID_LIFECYCLE_STATES = {"active", "maintenance", "dormant", "experimental", "archived"}
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
    intended_disposition: str = ""
    maturity_program: str = ""
    target_maturity: str = ""
    operating_path: str = ""
    category: str = ""
    tool_provenance: str = ""
    notes: str = ""
    doctor_standard: str = ""

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
    registry_status: str = "parked"
    path_override: str = ""
    path_confidence: str = "legacy"
    path_rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["last_meaningful_activity_at"] = _serialize_datetime(self.last_meaningful_activity_at)
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

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class PortfolioTruthProject:
    identity: IdentityFields
    declared: DeclaredFields
    derived: DerivedFields
    risk: RiskFields = field(default_factory=RiskFields)
    advisory: AdvisoryFields = field(default_factory=AdvisoryFields)
    provenance: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "declared": self.declared.to_dict(),
            "derived": self.derived.to_dict(),
            "risk": self.risk.to_dict(),
            "advisory": self.advisory.to_dict(),
            "provenance": self.provenance,
            "warnings": list(self.warnings),
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": _serialize_datetime(self.generated_at),
            "workspace_root": self.workspace_root,
            "source_summary": self.source_summary,
            "precedence_matrix": self.precedence_matrix,
            "warnings": list(self.warnings),
            "projects": [project.to_dict() for project in self.projects],
        }
