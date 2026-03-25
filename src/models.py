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
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "analyzer_results": [r.to_dict() for r in self.analyzer_results],
            "overall_score": round(self.overall_score, 3),
            "completeness_tier": self.completeness_tier,
            "flags": self.flags,
        }
