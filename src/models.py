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
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "analyzer_results": [r.to_dict() for r in self.analyzer_results],
            "overall_score": round(self.overall_score, 3),
            "interest_score": round(self.interest_score, 3),
            "completeness_tier": self.completeness_tier,
            "interest_tier": self.interest_tier,
            "flags": self.flags,
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
    most_active: list[str] = field(default_factory=list)
    most_neglected: list[str] = field(default_factory=list)
    highest_scored: list[str] = field(default_factory=list)
    lowest_scored: list[str] = field(default_factory=list)
    reconciliation: object | None = None  # RegistryReconciliation when --registry used

    @classmethod
    def from_audits(
        cls,
        username: str,
        audits: list[RepoAudit],
        errors: list[dict],
        total_repos: int,
    ) -> AuditReport:
        """Construct an AuditReport with all derived statistics."""
        now = datetime.now(tz=__import__("datetime").timezone.utc)

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

        return cls(
            username=username,
            generated_at=now,
            total_repos=total_repos,
            repos_audited=len(audits),
            tier_distribution=tier_dist,
            average_score=round(avg, 3),
            language_distribution=lang_dist,
            audits=audits,
            errors=errors,
            most_active=most_active,
            most_neglected=most_neglected,
            highest_scored=highest,
            lowest_scored=lowest,
        )

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "generated_at": self.generated_at.isoformat(),
            "total_repos": self.total_repos,
            "repos_audited": self.repos_audited,
            "average_score": self.average_score,
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
