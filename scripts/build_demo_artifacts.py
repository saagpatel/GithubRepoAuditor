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
    _write_demo_portfolio_command_center_files(report_data)
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
    payload = _build_pcc_truth_snapshot(report_data, report_data.get("generated_at", ""))
    (OUTPUT_DIR / "portfolio-truth-latest.json").write_text(json.dumps(payload, indent=2))


def _risk_tier(audit: dict[str, Any]) -> str:
    score = float(audit.get("overall_score", 0))
    posture = (audit.get("security_posture") or {}).get("label", "")
    if posture in {"critical", "watch"} or score < 0.50:
        return "elevated"
    if score < 0.75:
        return "moderate"
    return "baseline"


def _context_quality(audit: dict[str, Any]) -> str:
    score = float((audit.get("lenses", {}).get("ship_readiness") or {}).get("score", 0))
    if score >= 0.85:
        return "full"
    if score >= 0.65:
        return "standard"
    if score >= 0.40:
        return "minimum-viable"
    return "boilerplate"


def _registry_status(audit: dict[str, Any]) -> str:
    tier = audit.get("completeness_tier", "")
    if tier == "shipped":
        return "active"
    if tier == "functional":
        return "recent"
    if tier == "wip":
        return "parked"
    return "deferred"


def _attention_state(audit: dict[str, Any], risk_tier: str, high_crit: int) -> str:
    name = (audit.get("metadata") or {}).get("name", "")
    if high_crit or risk_tier == "elevated":
        return "decision-needed"
    if name == "RepoA":
        return "active-product"
    return "manual-only"


def _security_fields(audit: dict[str, Any]) -> dict[str, Any]:
    name = (audit.get("metadata") or {}).get("name", "")
    if name == "RepoC":
        return {
            "alerts_available": True,
            "dependabot_critical": 1,
            "dependabot_high": 2,
            "dependabot_medium": 1,
            "dependabot_low": 0,
            "secret_scanning_open": 0,
            "code_scanning_critical": 0,
            "code_scanning_high": 1,
        }
    if name == "RepoB":
        return {
            "alerts_available": True,
            "dependabot_critical": 0,
            "dependabot_high": 1,
            "dependabot_medium": 2,
            "dependabot_low": 1,
            "secret_scanning_open": 0,
            "code_scanning_critical": 0,
            "code_scanning_high": 0,
        }
    return {
        "alerts_available": True,
        "dependabot_critical": 0,
        "dependabot_high": 0,
        "dependabot_medium": 0,
        "dependabot_low": 0,
        "secret_scanning_open": 0,
        "code_scanning_critical": 0,
        "code_scanning_high": 0,
    }


def _build_pcc_truth_snapshot(
    report_data: dict[str, Any],
    generated_at: str,
    *,
    risk_shift: int = 0,
) -> dict[str, Any]:
    projects = []
    for index, audit in enumerate(report_data.get("audits", []), start=1):
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        if not repo_name:
            continue
        language = metadata.get("language") or "Unknown"
        risk_tier = _risk_tier(audit)
        if risk_shift < 0 and risk_tier == "elevated":
            risk_tier = "moderate"
        security = _security_fields(audit)
        high_crit = security["dependabot_critical"] + security["dependabot_high"]
        attention_state = _attention_state(audit, risk_tier, high_crit)
        projects.append(
            {
                "identity": {
                    "project_key": repo_name,
                    "display_name": repo_name,
                    "path": f"fixtures/demo/{repo_name}",
                    "section_marker": "fixture-demo",
                    "has_git": True,
                    "top_level_dir": "fixtures",
                    "group_key": "demo",
                    "group_label": "Demo Portfolio",
                    "section_label": "Fixture Demo",
                },
                "declared": {
                    "operating_path": f"fixtures/demo/{repo_name}",
                    "category": "demo-product" if index == 1 else "demo-support",
                    "tool_provenance": "Codex" if index % 2 else "Claude Code",
                    "lifecycle_state": audit.get("completeness_tier", "unknown"),
                    "purpose": metadata.get("description") or "Fixture project",
                    "criticality": "demo",
                    "review_cadence": "weekly",
                    "intended_disposition": "keep",
                    "maturity_program": "operator-os-fixture",
                    "target_maturity": "public-demo",
                    "automation_eligible": index == 3,
                },
                "derived": {
                    "context_quality": _context_quality(audit),
                    "registry_status": _registry_status(audit),
                    "attention_state": attention_state,
                    "stack": [language],
                    "context_files": ["README.md", "docs/current-state.md"],
                    "context_file_count": 2,
                    "primary_context_file": "README.md",
                    "project_summary_present": True,
                    "current_state_present": index != 3,
                    "stack_present": True,
                    "run_instructions_present": index != 2,
                    "known_risks_present": risk_tier == "elevated",
                    "next_recommended_move_present": True,
                    "last_meaningful_activity_at": generated_at,
                    "activity_status": "current",
                    "has_tests": index != 3,
                    "has_ci": index == 1,
                    "has_license": True,
                    "readme_char_count": 2400 - index * 300,
                    "release_count": 2 if index == 1 else 0,
                },
                "risk": {
                    "risk_tier": risk_tier,
                    "risk_factors": [
                        "open high/critical alerts"
                    ]
                    if high_crit
                    else [],
                    "risk_summary": "Security follow-through needs operator review."
                    if high_crit
                    else "No elevated fixture risk.",
                    "security_risk": high_crit > 0,
                    "doctor_gap": index == 3,
                    "context_risk": _context_quality(audit) in {"minimum-viable", "boilerplate"},
                    "path_risk": False,
                },
                "security": security,
                "advisory": {
                    "legacy_status": audit.get("completeness_tier", ""),
                    "legacy_context_quality": _context_quality(audit),
                    "legacy_category": "fixture-demo",
                    "legacy_tool_provenance": "sample",
                },
            }
        )

    return {
        "schema_version": "demo-pcc-v1",
        "generated_at": generated_at,
        "workspace_root": "fixtures/demo",
        "projects": projects,
    }


def _write_demo_portfolio_command_center_files(report_data: dict[str, Any]) -> None:
    generated_at = report_data.get("generated_at", "2026-04-12T12:00:00+00:00")
    projects = _build_pcc_truth_snapshot(report_data, generated_at)["projects"]
    elevated = [p for p in projects if p["risk"]["risk_tier"] == "elevated"]
    open_alerts = [
        p
        for p in projects
        if p["security"]["dependabot_critical"] + p["security"]["dependabot_high"] > 0
    ]
    total_critical = sum(p["security"]["dependabot_critical"] for p in projects)
    total_high = sum(p["security"]["dependabot_high"] for p in projects)
    digest = {
        "username": report_data.get("username", "sample-user"),
        "generated_at": generated_at,
        "headline": "Fixture portfolio has one security-driven next move.",
        "decision": "Review RepoC before expanding lower-pressure cleanup.",
        "why_this_week": "RepoC carries the only critical fixture alert and demonstrates the operator-approved review lane.",
        "next_step": "Open the burndown view, confirm the grouped fix, then record the decision.",
        "risk_posture": {
            "elevated_count": len(elevated),
            "risk_tier_counts": {
                "elevated": len(elevated),
                "moderate": len([p for p in projects if p["risk"]["risk_tier"] == "moderate"]),
                "baseline": len([p for p in projects if p["risk"]["risk_tier"] == "baseline"]),
                "deferred": len([p for p in projects if p["risk"]["risk_tier"] == "deferred"]),
            },
            "top_elevated": [
                {
                    "repo": p["identity"]["project_key"],
                    "risk_tier": p["risk"]["risk_tier"],
                    "risk_summary": p["risk"]["risk_summary"],
                }
                for p in elevated
            ],
        },
        "security_posture": {
            "scanned_count": len(projects),
            "repos_with_open_high_critical": len(open_alerts),
            "total_open_critical": total_critical,
            "total_open_high": total_high,
            "top_alerts": [
                {
                    "repo": p["identity"]["project_key"],
                    "risk_tier": p["risk"]["risk_tier"],
                    "dependabot_critical": p["security"]["dependabot_critical"],
                    "dependabot_high": p["security"]["dependabot_high"],
                }
                for p in open_alerts
            ],
        },
        "path_attention": [
            {
                "repo": p["identity"]["project_key"],
                "headline": "Fixture context is intentionally compact.",
                "registry_status": p["derived"]["registry_status"],
                "context_quality": p["derived"]["context_quality"],
            }
            for p in projects
        ],
    }
    (OUTPUT_DIR / "weekly-command-center-sample-user-2026-04-12.json").write_text(
        json.dumps(digest, indent=2)
    )

    burndown = {
        "distinct_advisories": 2,
        "total_repo_instances": 3,
        "repos_touched": 2,
        "entries": [
            {
                "package": "demo-runtime",
                "ecosystem": "pip",
                "severity": "critical",
                "ghsa_id": "GHSA-DEMO-0001",
                "first_patched_version": "2.0.0",
                "affected_repos": ["RepoC"],
                "affected_repo_count": 1,
            },
            {
                "package": "demo-ui-kit",
                "ecosystem": "npm",
                "severity": "high",
                "ghsa_id": "GHSA-DEMO-0002",
                "first_patched_version": "4.1.0",
                "affected_repos": ["RepoB", "RepoC"],
                "affected_repo_count": 2,
            },
        ],
    }
    (OUTPUT_DIR / "security-burndown-sample-user-2026-04-12.json").write_text(
        json.dumps(burndown, indent=2)
    )

    (OUTPUT_DIR / "pending-proposals.json").write_text(
        json.dumps({"contract_version": "automation_proposals_v1", "proposals": []}, indent=2)
    )

    previous = _build_pcc_truth_snapshot(
        report_data,
        "2026-04-05T12:00:00+00:00",
        risk_shift=-1,
    )
    current = _build_pcc_truth_snapshot(report_data, generated_at)
    (OUTPUT_DIR / "portfolio-truth-2026-04-05T120000Z.json").write_text(
        json.dumps(previous, indent=2)
    )
    (OUTPUT_DIR / "portfolio-truth-2026-04-12T120000Z.json").write_text(
        json.dumps(current, indent=2)
    )


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
