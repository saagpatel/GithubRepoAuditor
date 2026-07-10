"""Leaf report-discovery and artifact-time helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.models import AnalyzerResult, RepoAudit, RepoMetadata


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit_from_dict(data: dict) -> RepoAudit:
    meta_data = data.get("metadata", {})
    metadata = RepoMetadata(
        name=meta_data["name"],
        full_name=meta_data["full_name"],
        description=meta_data.get("description"),
        language=meta_data.get("language"),
        languages=meta_data.get("languages", {}),
        private=meta_data["private"],
        fork=meta_data["fork"],
        archived=meta_data["archived"],
        created_at=parse_iso_datetime(meta_data.get("created_at")),  # type: ignore[arg-type]
        updated_at=parse_iso_datetime(meta_data.get("updated_at")),  # type: ignore[arg-type]
        pushed_at=parse_iso_datetime(meta_data.get("pushed_at")),
        default_branch=meta_data.get("default_branch", "main"),
        stars=meta_data.get("stars", 0),
        forks=meta_data.get("forks", 0),
        open_issues=meta_data.get("open_issues", 0),
        size_kb=meta_data.get("size_kb", 0),
        html_url=meta_data.get("html_url", ""),
        clone_url=meta_data.get("clone_url", ""),
        topics=meta_data.get("topics", []),
    )
    analyzer_results = [
        AnalyzerResult(
            dimension=result["dimension"],
            score=result["score"],
            max_score=result["max_score"],
            findings=result["findings"],
            details=result.get("details", {}),
        )
        for result in data.get("analyzer_results", [])
    ]
    return RepoAudit(
        metadata=metadata,
        analyzer_results=analyzer_results,
        overall_score=data.get("overall_score", 0),
        completeness_tier=data.get("completeness_tier", "abandoned"),
        interest_score=data.get("interest_score", 0),
        interest_tier=data.get("interest_tier", "mundane"),
        grade=data.get("grade", "F"),
        interest_grade=data.get("interest_grade", "F"),
        badges=data.get("badges", []),
        next_badges=data.get("next_badges", []),
        flags=data.get("flags", []),
        lenses=data.get("lenses", {}),
        hotspots=data.get("hotspots", []),
        action_candidates=data.get("action_candidates", []),
        security_posture=data.get("security_posture", {}),
        score_explanation=data.get("score_explanation", {}),
        portfolio_catalog=data.get("portfolio_catalog", {}),
        scorecard=data.get("scorecard", {}),
        ossf_scorecard=data.get("ossf_scorecard", {}),
    )

def load_latest_report(output_dir: Path) -> tuple[Path | None, dict | None]:
    reports = sorted(
        output_dir.glob("audit-report-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None, None
    latest = reports[0]
    return latest, json.loads(latest.read_text())


def report_artifact_datetime(report_path: Path | None, fallback: datetime) -> datetime:
    if report_path:
        stem = report_path.stem
        if len(stem) >= 10:
            parsed = datetime.fromisoformat(f"{stem[-10:]}T00:00:00+00:00")
            return parsed
    return fallback
