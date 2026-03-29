from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.models import AnalyzerResult, RepoMetadata
from src.scorer import WEIGHTS, score_repo
from src.warehouse import write_warehouse_snapshot


def _make_metadata() -> RepoMetadata:
    return RepoMetadata(
        name="warehouse-repo",
        full_name="user/warehouse-repo",
        description="Warehouse test repo",
        language="Python",
        languages={"Python": 1000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=4,
        forks=1,
        open_issues=0,
        size_kb=128,
        html_url="https://github.com/user/warehouse-repo",
        clone_url="https://github.com/user/warehouse-repo.git",
        topics=["python"],
    )


def _make_results() -> list[AnalyzerResult]:
    results = []
    for dimension, score in WEIGHTS.items():
        details = {}
        if dimension == "structure":
            details = {"config_files": ["pyproject.toml"], "source_dirs": ["src"]}
        if dimension == "code_quality":
            details = {"entry_point": "main.py", "total_loc": 200}
        results.append(
            AnalyzerResult(
                dimension=dimension,
                score=0.75 if dimension != "testing" else 0.45,
                max_score=1.0,
                findings=[],
                details=details,
            )
        )
    results.append(
        AnalyzerResult(
            dimension="interest",
            score=0.55,
            max_score=1.0,
            findings=[],
            details={"tech_novelty": 0.10},
        )
    )
    results.append(
        AnalyzerResult(
            dimension="security",
            score=0.50,
            max_score=1.0,
            findings=["No SECURITY.md"],
            details={
                "secrets_found": 0,
                "dangerous_files": [],
                "has_security_md": False,
                "has_dependabot": True,
            },
        )
    )
    return results


def test_write_warehouse_snapshot_persists_core_entities(tmp_path):
    audit = score_repo(_make_metadata(), _make_results())

    from src.models import AuditReport

    report = AuditReport.from_audits("user", [audit], [], 1)
    db_path = write_warehouse_snapshot(report, tmp_path)

    conn = sqlite3.connect(db_path)
    try:
        audit_runs = conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0]
        repo_rows = conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
        lens_rows = conn.execute("SELECT COUNT(*) FROM lens_scores").fetchone()[0]
        action_rows = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        collection_rows = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        scenario_rows = conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]
        control_rows = conn.execute("SELECT COUNT(*) FROM security_controls").fetchone()[0]
        provider_rows = conn.execute("SELECT COUNT(*) FROM security_providers").fetchone()[0]
        recommendation_rows = conn.execute("SELECT COUNT(*) FROM security_recommendations").fetchone()[0]
    finally:
        conn.close()

    assert audit_runs == 1
    assert repo_rows == 1
    assert lens_rows >= 5
    assert action_rows >= 1
    assert collection_rows >= 1
    assert scenario_rows >= 1
    assert control_rows >= 4
    assert provider_rows >= 1
    assert recommendation_rows >= 1
