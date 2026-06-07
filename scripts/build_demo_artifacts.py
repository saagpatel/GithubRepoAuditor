from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from _bootstrap import ensure_project_root

ROOT = ensure_project_root()


def _load_demo_tools() -> tuple[object, object, object, object, object, object, object]:
    from src.excel_export import export_excel
    from src.operator_control_center import (
        control_center_artifact_payload,
        render_control_center_markdown,
    )
    from src.report_enrichment import (
        build_run_change_counts,
        build_run_change_summary,
        build_score_explanation,
    )
    from src.web_export import export_html_dashboard

    return (
        control_center_artifact_payload,
        render_control_center_markdown,
        build_run_change_counts,
        build_run_change_summary,
        build_score_explanation,
        export_html_dashboard,
        export_excel,
    )

FIXTURE_PATH = ROOT / "fixtures" / "demo" / "sample-report.json"
OUTPUT_DIR = ROOT / "output" / "demo"


def _demo_diff_data() -> dict:
    return {
        "previous_date": "2026-04-05T12:00:00+00:00",
        "current_date": "2026-04-12T12:00:00+00:00",
        "average_score_delta": 0.02,
        "lens_deltas": {
            "ship_readiness": 0.03,
            "security_posture": -0.01,
        },
        "tier_changes": [
            {
                "name": "RepoA",
                "old_tier": "functional",
                "new_tier": "shipped",
                "old_score": 0.79,
                "new_score": 0.88,
                "direction": "promotion",
            },
            {
                "name": "RepoC",
                "old_tier": "functional",
                "new_tier": "wip",
                "old_score": 0.52,
                "new_score": 0.44,
                "direction": "demotion",
            },
        ],
        "score_changes": [
            {"name": "RepoA", "old_score": 0.79, "new_score": 0.88, "delta": 0.09},
            {"name": "RepoB", "old_score": 0.68, "new_score": 0.62, "delta": -0.06},
            {"name": "RepoC", "old_score": 0.52, "new_score": 0.44, "delta": -0.08},
        ],
        "repo_changes": [
            {
                "name": "RepoA",
                "delta": 0.09,
                "old_tier": "functional",
                "new_tier": "shipped",
                "security_change": {"old_label": "watch", "new_label": "healthy"},
                "hotspot_change": {"old_count": 2, "new_count": 1},
                "collection_change": {"old": [], "new": ["showcase"]},
            },
            {
                "name": "RepoC",
                "delta": -0.08,
                "old_tier": "functional",
                "new_tier": "wip",
                "security_change": {"old_label": "watch", "new_label": "critical"},
                "hotspot_change": {"old_count": 1, "new_count": 1},
                "collection_change": {"old": [], "new": []},
            },
        ],
        "security_changes": [
            {"name": "RepoC", "old_label": "watch", "new_label": "critical"},
        ],
        "hotspot_changes": [
            {"name": "RepoA", "old_count": 2, "new_count": 1},
            {"name": "RepoB", "old_count": 0, "new_count": 1},
        ],
        "collection_changes": [
            {"name": "RepoA", "old": [], "new": ["showcase"]},
        ],
    }


def main() -> None:
    (
        control_center_artifact_payload,
        render_control_center_markdown,
        build_run_change_counts,
        build_run_change_summary,
        build_score_explanation,
        export_html_dashboard,
        export_excel,
    ) = _load_demo_tools()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_data = json.loads(FIXTURE_PATH.read_text())
    diff_data = _demo_diff_data()

    for audit in report_data.get("audits", []):
        audit["score_explanation"] = build_score_explanation(audit)
    report_data["run_change_counts"] = build_run_change_counts(diff_data)
    report_data["run_change_summary"] = build_run_change_summary(diff_data)

    report_path = OUTPUT_DIR / "demo-report.json"
    report_path.write_text(json.dumps(report_data, indent=2))

    export_html_dashboard(report_data, OUTPUT_DIR, diff_data=diff_data)
    export_excel(report_path, OUTPUT_DIR / "demo-workbook.xlsx", diff_data=diff_data, excel_mode="standard")
    _write_demo_portfolio_truth(report_data)
    _write_demo_warehouse(report_data, report_path)

    control_center_json = OUTPUT_DIR / "operator-control-center-demo.json"
    control_center_md = OUTPUT_DIR / "operator-control-center-demo.md"
    artifact_payload = control_center_artifact_payload(report_data, report_data)
    control_center_json.write_text(json.dumps(artifact_payload, indent=2))
    control_center_md.write_text(
        render_control_center_markdown(
            artifact_payload,
            username=report_data.get("username", "sample-user"),
            generated_at=report_data.get("generated_at", ""),
        )
    )

    print(f"Demo artifacts written to {OUTPUT_DIR}")


def _parse_generated_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _write_demo_portfolio_truth(report_data: dict[str, Any]) -> None:
    repos = []
    for audit in report_data.get("audits", []):
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        if not repo_name:
            continue
        risk_score = round((1.0 - float(audit.get("overall_score", 0))) * 100, 1)
        ship_readiness = (audit.get("lenses", {}).get("ship_readiness") or {}).get("score", 0)
        repos.append(
            {
                "name": repo_name,
                "full_name": metadata.get("full_name", repo_name),
                "language": metadata.get("language") or "Unknown",
                "tier": audit.get("completeness_tier", ""),
                "total_score": round(float(audit.get("overall_score", 0)) * 100, 1),
                "risk_score": risk_score,
                "completeness_score": round(float(ship_readiness) * 100, 1),
                "interest_score": round(float(audit.get("interest_score", 0)) * 100, 1),
            }
        )

    payload = {
        "schema_version": "demo",
        "generated_at": report_data.get("generated_at", ""),
        "workspace_root": "fixtures/demo",
        "repos": repos,
    }
    (OUTPUT_DIR / "portfolio-truth-latest.json").write_text(json.dumps(payload, indent=2))


def _write_demo_warehouse(report_data: dict[str, Any], report_path) -> None:
    from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
    from src.warehouse import WAREHOUSE_FILENAME, write_warehouse_snapshot

    generated_at = _parse_generated_at(report_data.get("generated_at"))
    warehouse_path = OUTPUT_DIR / WAREHOUSE_FILENAME
    if warehouse_path.exists():
        warehouse_path.unlink()
    audits: list[RepoAudit] = []
    for item in report_data.get("audits", []):
        metadata = item.get("metadata", {})
        language = metadata.get("language") or "Unknown"
        repo_name = metadata.get("name", "")
        full_name = metadata.get("full_name") or f"{report_data.get('username', 'sample-user')}/{repo_name}"
        analyzer_results = [
            AnalyzerResult(
                dimension=result.get("dimension", ""),
                score=float(result.get("score", 0)),
                max_score=float(result.get("max_score", 1.0) or 1.0),
                findings=list(result.get("findings", [])),
                details=dict(result.get("details", {})),
            )
            for result in item.get("analyzer_results", [])
            if result.get("dimension")
        ]
        audits.append(
            RepoAudit(
                metadata=RepoMetadata(
                    name=repo_name,
                    full_name=full_name,
                    description=metadata.get("description"),
                    language=language,
                    languages={language: 1},
                    private=bool(metadata.get("private", False)),
                    fork=bool(metadata.get("fork", False)),
                    archived=bool(metadata.get("archived", False)),
                    created_at=generated_at,
                    updated_at=generated_at,
                    pushed_at=generated_at,
                    default_branch=metadata.get("default_branch", "main"),
                    stars=int(metadata.get("stars", 0)),
                    forks=int(metadata.get("forks", 0)),
                    open_issues=int(metadata.get("open_issues", 0)),
                    size_kb=int(metadata.get("size_kb", 0)),
                    html_url=metadata.get("html_url", ""),
                    clone_url=metadata.get("clone_url", ""),
                    topics=list(metadata.get("topics", [])),
                ),
                analyzer_results=analyzer_results,
                overall_score=float(item.get("overall_score", 0)),
                completeness_tier=item.get("completeness_tier", ""),
                interest_score=float(item.get("interest_score", 0)),
                grade=item.get("grade", "F"),
                badges=list(item.get("badges", [])),
                flags=list(item.get("flags", [])),
                lenses=dict(item.get("lenses", {})),
                hotspots=list(item.get("hotspots", [])),
                action_candidates=list(item.get("action_candidates", [])),
                security_posture=dict(item.get("security_posture", {})),
                score_explanation=dict(item.get("score_explanation", {})),
            )
        )

    report = AuditReport(
        username=report_data.get("username", "sample-user"),
        generated_at=generated_at,
        total_repos=int(report_data.get("total_repos", len(audits))),
        repos_audited=int(report_data.get("repos_audited", len(audits))),
        tier_distribution=dict(report_data.get("tier_distribution", {})),
        average_score=float(report_data.get("average_score", 0)),
        language_distribution=dict(report_data.get("language_distribution", {})),
        audits=audits,
        errors=[],
        portfolio_grade=report_data.get("portfolio_grade", "F"),
        portfolio_health_score=float(report_data.get("portfolio_health_score", 0)),
        lenses=dict(report_data.get("lenses", {})),
        security_posture=dict(report_data.get("security_posture", {})),
        security_governance_preview=list(report_data.get("security_governance_preview", [])),
        collections=dict(report_data.get("collections", {})),
        profiles=dict(report_data.get("profiles", {})),
        scenario_summary=dict(report_data.get("scenario_summary", {})),
        campaign_summary=dict(report_data.get("campaign_summary", {})),
        writeback_preview=dict(report_data.get("writeback_preview", {})),
        writeback_results=dict(report_data.get("writeback_results", {})),
        managed_state_drift=list(report_data.get("managed_state_drift", [])),
        governance_drift=list(report_data.get("governance_drift", [])),
        governance_summary=dict(report_data.get("governance_summary", {})),
        review_summary=dict(report_data.get("review_summary", {})),
        review_targets=list(report_data.get("review_targets", [])),
        review_history=list(report_data.get("review_history", [])),
        material_changes=list(report_data.get("material_changes", [])),
        operator_summary=dict(report_data.get("operator_summary", {})),
        operator_queue=list(report_data.get("operator_queue", [])),
        run_change_summary=report_data.get("run_change_summary", ""),
        run_change_counts=dict(report_data.get("run_change_counts", {})),
    )
    write_warehouse_snapshot(report, OUTPUT_DIR, report_path)


if __name__ == "__main__":
    main()
