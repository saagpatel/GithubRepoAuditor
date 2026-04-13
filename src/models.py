from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _parse_dt(value: str | None) -> Optional[datetime]:
    """Parse GitHub API datetime string to timezone-aware datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class RepoMetadata:
    name: str
    full_name: str
    description: Optional[str]
    language: Optional[str]
    languages: dict[str, int]
    private: bool
    fork: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    pushed_at: Optional[datetime]
    default_branch: str
    stars: int
    forks: int
    open_issues: int
    size_kb: int
    html_url: str
    clone_url: str
    topics: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict, languages: dict[str, int] | None = None) -> RepoMetadata:
        """Build RepoMetadata from a GitHub API repo object."""
        return cls(
            name=data["name"],
            full_name=data["full_name"],
            description=data.get("description"),
            language=data.get("language"),
            languages=languages or {},
            private=data["private"],
            fork=data["fork"],
            archived=data["archived"],
            created_at=_parse_dt(data["created_at"]),  # type: ignore[arg-type]
            updated_at=_parse_dt(data["updated_at"]),  # type: ignore[arg-type]
            pushed_at=_parse_dt(data.get("pushed_at")),
            default_branch=data["default_branch"],
            stars=data["stargazers_count"],
            forks=data["forks_count"],
            open_issues=data["open_issues_count"],
            size_kb=data["size"],
            html_url=data["html_url"],
            clone_url=data["clone_url"],
            topics=data.get("topics", []),
        )

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict (datetimes as ISO strings)."""
        raw = dataclasses.asdict(self)
        for key in ("created_at", "updated_at", "pushed_at"):
            val = raw[key]
            if isinstance(val, datetime):
                raw[key] = val.isoformat()
            elif val is None:
                raw[key] = None
        return raw


@dataclass
class AnalyzerResult:
    dimension: str
    score: float
    max_score: float
    findings: list[str]
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class RepoAudit:
    metadata: RepoMetadata
    analyzer_results: list[AnalyzerResult]
    overall_score: float
    completeness_tier: str
    interest_score: float = 0.0
    interest_tier: str = "mundane"
    grade: str = "F"
    interest_grade: str = "F"
    badges: list[str] = field(default_factory=list)
    next_badges: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    lenses: dict[str, dict] = field(default_factory=dict)
    hotspots: list[dict] = field(default_factory=list)
    action_candidates: list[dict] = field(default_factory=list)
    security_posture: dict = field(default_factory=dict)
    score_explanation: dict = field(default_factory=dict)
    portfolio_catalog: dict = field(default_factory=dict)
    scorecard: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "analyzer_results": [r.to_dict() for r in self.analyzer_results],
            "overall_score": round(self.overall_score, 3),
            "interest_score": round(self.interest_score, 3),
            "completeness_tier": self.completeness_tier,
            "interest_tier": self.interest_tier,
            "grade": self.grade,
            "interest_grade": self.interest_grade,
            "badges": self.badges,
            "next_badges": self.next_badges,
            "flags": self.flags,
            "lenses": self.lenses,
            "hotspots": self.hotspots,
            "action_candidates": self.action_candidates,
            "security_posture": self.security_posture,
            "score_explanation": self.score_explanation,
            "portfolio_catalog": self.portfolio_catalog,
            "scorecard": self.scorecard,
        }


@dataclass
class AuditReport:
    username: str
    generated_at: datetime
    total_repos: int
    repos_audited: int
    tier_distribution: dict[str, int]
    average_score: float
    language_distribution: dict[str, int]
    audits: list[RepoAudit]
    errors: list[dict]
    portfolio_grade: str = "F"
    portfolio_health_score: float = 0.0
    tech_stack: dict = field(default_factory=dict)
    best_work: list[str] = field(default_factory=list)
    most_active: list[str] = field(default_factory=list)
    most_neglected: list[str] = field(default_factory=list)
    highest_scored: list[str] = field(default_factory=list)
    lowest_scored: list[str] = field(default_factory=list)
    scoring_profile: str = "default"
    run_mode: str = "full"
    portfolio_baseline_size: int = 0
    baseline_signature: str = ""
    baseline_context: dict = field(default_factory=dict)
    schema_version: str = "3.7"
    lenses: dict[str, dict] = field(default_factory=dict)
    hotspots: list[dict] = field(default_factory=list)
    security_posture: dict = field(default_factory=dict)
    security_governance_preview: list[dict] = field(default_factory=list)
    collections: dict[str, dict] = field(default_factory=dict)
    profiles: dict[str, dict] = field(default_factory=dict)
    scenario_summary: dict = field(default_factory=dict)
    action_backlog: list[dict] = field(default_factory=list)
    campaign_summary: dict = field(default_factory=dict)
    writeback_preview: dict = field(default_factory=dict)
    writeback_results: dict = field(default_factory=dict)
    action_runs: list[dict] = field(default_factory=list)
    external_refs: dict[str, dict] = field(default_factory=dict)
    managed_state_drift: list[dict] = field(default_factory=list)
    rollback_preview: dict = field(default_factory=dict)
    campaign_history: list[dict] = field(default_factory=list)
    governance_preview: dict = field(default_factory=dict)
    governance_approval: dict = field(default_factory=dict)
    governance_results: dict = field(default_factory=dict)
    governance_history: list[dict] = field(default_factory=list)
    governance_drift: list[dict] = field(default_factory=list)
    governance_summary: dict = field(default_factory=dict)
    preflight_summary: dict = field(default_factory=dict)
    review_summary: dict = field(default_factory=dict)
    review_alerts: list[dict] = field(default_factory=list)
    material_changes: list[dict] = field(default_factory=list)
    review_targets: list[dict] = field(default_factory=list)
    review_history: list[dict] = field(default_factory=list)
    watch_state: dict = field(default_factory=dict)
    operator_summary: dict = field(default_factory=dict)
    operator_queue: list[dict] = field(default_factory=list)
    portfolio_catalog_summary: dict = field(default_factory=dict)
    intent_alignment_summary: dict = field(default_factory=dict)
    scorecards_summary: dict = field(default_factory=dict)
    scorecard_programs: dict = field(default_factory=dict)
    run_change_summary: str = ""
    run_change_counts: dict = field(default_factory=dict)
    runtime_breakdown: dict = field(default_factory=dict)
    reconciliation: object | None = None  # RegistryReconciliation when --registry used

    @classmethod
    def from_audits(
        cls,
        username: str,
        audits: list[RepoAudit],
        errors: list[dict],
        total_repos: int,
        *,
        scoring_profile: str = "default",
        run_mode: str = "full",
        portfolio_baseline_size: int | None = None,
        baseline_signature: str = "",
        baseline_context: dict | None = None,
    ) -> AuditReport:
        """Construct an AuditReport with all derived statistics."""
        now = datetime.now(tz=__import__("datetime").timezone.utc)
        from src.portfolio_intelligence import (
            DEFAULT_PROFILES,
            REPORT_SCHEMA_VERSION,
            build_default_collections,
            build_portfolio_hotspots,
            build_portfolio_lens_summary,
            build_portfolio_security_governance_preview,
            build_portfolio_security_posture,
            build_scenario_summary,
        )

        # Tier distribution
        tier_dist: dict[str, int] = {}
        for a in audits:
            tier_dist[a.completeness_tier] = tier_dist.get(a.completeness_tier, 0) + 1

        # Average score
        avg = sum(a.overall_score for a in audits) / len(audits) if audits else 0.0

        # Language distribution
        from collections import Counter
        lang_dist = dict(
            Counter(
                a.metadata.language or "Unknown" for a in audits
            ).most_common()
        )

        # Summary lists (top/bottom 5)
        sorted_by_score = sorted(audits, key=lambda a: a.overall_score, reverse=True)
        highest = [a.metadata.name for a in sorted_by_score[:5]]
        lowest = [a.metadata.name for a in sorted_by_score[-5:]]

        # Most active: sort by activity dimension score
        def _activity_score(audit: RepoAudit) -> float:
            for r in audit.analyzer_results:
                if r.dimension == "activity":
                    return r.score
            return 0.0

        sorted_by_activity = sorted(audits, key=_activity_score, reverse=True)
        most_active = [a.metadata.name for a in sorted_by_activity[:5]]
        most_neglected = [a.metadata.name for a in sorted_by_activity[-5:]]

        # Portfolio grade (nuanced formula)
        from src.scorer import compute_portfolio_grade
        p_grade, p_health = compute_portfolio_grade(audits)

        # Tech stack summary
        tech_stack: dict[str, dict] = {}
        for a in audits:
            for lang, byte_count in a.metadata.languages.items():
                if lang not in tech_stack:
                    tech_stack[lang] = {"bytes": 0, "repos": 0, "total_score": 0.0}
                tech_stack[lang]["bytes"] += byte_count
                tech_stack[lang]["repos"] += 1
                tech_stack[lang]["total_score"] += a.overall_score
        for data in tech_stack.values():
            data["avg_score"] = round(data["total_score"] / data["repos"], 3) if data["repos"] else 0
            data["proficiency"] = round(data["bytes"] * data["avg_score"])
            del data["total_score"]
        # Sort by proficiency descending
        tech_stack = dict(sorted(tech_stack.items(), key=lambda x: x[1]["proficiency"], reverse=True))

        # Best work: top 5 by weighted combo
        best = sorted(audits, key=lambda a: a.overall_score * 0.6 + a.interest_score * 0.4, reverse=True)
        best_work = [a.metadata.name for a in best[:5]]
        portfolio_lenses = build_portfolio_lens_summary(audits)
        portfolio_hotspots = build_portfolio_hotspots(audits)
        portfolio_security = build_portfolio_security_posture(audits)
        security_governance_preview = build_portfolio_security_governance_preview(audits)
        collections = build_default_collections(audits)
        scenario_summary = build_scenario_summary(audits)
        action_backlog = sorted(
            [
                {
                    "repo": audit.metadata.name,
                    **action,
                }
                for audit in audits
                for action in audit.action_candidates
            ],
            key=lambda action: (action["confidence"], action["expected_lens_delta"]),
            reverse=True,
        )[:20]

        return cls(
            username=username,
            generated_at=now,
            total_repos=total_repos,
            repos_audited=len(audits),
            tier_distribution=tier_dist,
            average_score=round(avg, 3),
            language_distribution=lang_dist,
            portfolio_grade=p_grade,
            portfolio_health_score=p_health,
            tech_stack=tech_stack,
            best_work=best_work,
            audits=audits,
            errors=errors,
            most_active=most_active,
            most_neglected=most_neglected,
            highest_scored=highest,
            lowest_scored=lowest,
            scoring_profile=scoring_profile,
            run_mode=run_mode,
            portfolio_baseline_size=portfolio_baseline_size if portfolio_baseline_size is not None else len(audits),
            baseline_signature=baseline_signature,
            baseline_context=baseline_context or {},
            schema_version=REPORT_SCHEMA_VERSION,
            lenses=portfolio_lenses,
            hotspots=portfolio_hotspots,
            security_posture=portfolio_security,
            security_governance_preview=security_governance_preview,
            collections=collections,
            profiles=DEFAULT_PROFILES,
            scenario_summary=scenario_summary,
            action_backlog=action_backlog,
            campaign_summary={},
            writeback_preview={},
            writeback_results={},
            action_runs=[],
            external_refs={},
            managed_state_drift=[],
            rollback_preview={},
            campaign_history=[],
            governance_preview={},
            governance_approval={},
            governance_results={},
            governance_history=[],
            governance_drift=[],
            governance_summary={},
            preflight_summary={},
            review_summary={},
            review_alerts=[],
            material_changes=[],
            review_targets=[],
            review_history=[],
            watch_state={},
            operator_summary={},
            operator_queue=[],
            portfolio_catalog_summary={},
            intent_alignment_summary={},
            scorecards_summary={},
            scorecard_programs={},
            run_change_summary="",
            run_change_counts={},
            runtime_breakdown={},
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "username": self.username,
            "generated_at": self.generated_at.isoformat(),
            "total_repos": self.total_repos,
            "repos_audited": self.repos_audited,
            "average_score": self.average_score,
            "portfolio_grade": self.portfolio_grade,
            "portfolio_health_score": self.portfolio_health_score,
            "scoring_profile": self.scoring_profile,
            "run_mode": self.run_mode,
            "portfolio_baseline_size": self.portfolio_baseline_size,
            "baseline_signature": self.baseline_signature,
            "baseline_context": self.baseline_context,
            "lenses": self.lenses,
            "hotspots": self.hotspots,
            "security_posture": self.security_posture,
            "security_governance_preview": self.security_governance_preview,
            "collections": self.collections,
            "profiles": self.profiles,
            "scenario_summary": self.scenario_summary,
            "action_backlog": self.action_backlog,
            "campaign_summary": self.campaign_summary,
            "writeback_preview": self.writeback_preview,
            "writeback_results": self.writeback_results,
            "action_runs": self.action_runs,
            "external_refs": self.external_refs,
            "managed_state_drift": self.managed_state_drift,
            "rollback_preview": self.rollback_preview,
            "campaign_history": self.campaign_history,
            "governance_preview": self.governance_preview,
            "governance_approval": self.governance_approval,
            "governance_results": self.governance_results,
            "governance_history": self.governance_history,
            "governance_drift": self.governance_drift,
            "governance_summary": self.governance_summary,
            "preflight_summary": self.preflight_summary,
            "review_summary": self.review_summary,
            "review_alerts": self.review_alerts,
            "material_changes": self.material_changes,
            "review_targets": self.review_targets,
            "review_history": self.review_history,
            "watch_state": self.watch_state,
            "operator_summary": self.operator_summary,
            "operator_queue": self.operator_queue,
            "portfolio_catalog_summary": self.portfolio_catalog_summary,
            "intent_alignment_summary": self.intent_alignment_summary,
            "scorecards_summary": self.scorecards_summary,
            "scorecard_programs": self.scorecard_programs,
            "run_change_summary": self.run_change_summary,
            "run_change_counts": self.run_change_counts,
            "runtime_breakdown": self.runtime_breakdown,
            "tech_stack": self.tech_stack,
            "best_work": self.best_work,
            "tier_distribution": self.tier_distribution,
            "language_distribution": self.language_distribution,
            "summary": {
                "most_active": self.most_active,
                "most_neglected": self.most_neglected,
                "highest_scored": self.highest_scored,
                "lowest_scored": self.lowest_scored,
            },
            "audits": [a.to_dict() for a in self.audits],
            "errors": self.errors,
            "reconciliation": self.reconciliation.to_dict() if self.reconciliation else None,
        }
