from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

from src.excel_export import CORE_VISIBLE_SHEETS, export_excel
from src.excel_template import DEFAULT_TEMPLATE_PATH

DEFAULT_GATE_DIR = Path("output") / "workbook-gate"


def _sample_report_data() -> dict:
    return {
        "username": "sample-user",
        "generated_at": "2026-04-07T12:00:00+00:00",
        "audits": [
            {
                "metadata": {
                    "name": "RepoA",
                    "html_url": "https://github.com/sample-user/RepoA",
                    "description": "Strong shipped project",
                    "language": "Python",
                },
                "overall_score": 0.87,
                "interest_score": 0.62,
                "grade": "A",
                "completeness_tier": "shipped",
                "badges": ["fresh", "tested"],
                "flags": [],
                "lenses": {
                    "ship_readiness": {"score": 0.88, "summary": "Ready"},
                    "showcase_value": {"score": 0.9, "summary": "Strong story"},
                    "security_posture": {"score": 0.82, "summary": "Healthy"},
                },
                "security_posture": {"label": "healthy", "score": 0.82},
                "hotspots": [{"title": "Keep momentum", "severity": 0.2, "category": "finish-line"}],
                "action_candidates": [{"title": "Protect current momentum"}],
                "analyzer_results": [],
            },
            {
                "metadata": {
                    "name": "RepoB",
                    "html_url": "https://github.com/sample-user/RepoB",
                    "description": "Functional but under-finished",
                    "language": "TypeScript",
                },
                "overall_score": 0.61,
                "interest_score": 0.35,
                "grade": "C",
                "completeness_tier": "functional",
                "badges": [],
                "flags": [],
                "lenses": {
                    "ship_readiness": {"score": 0.63, "summary": "Needs work"},
                    "showcase_value": {"score": 0.55, "summary": "Average"},
                    "security_posture": {"score": 0.66, "summary": "Watch"},
                },
                "security_posture": {"label": "watch", "score": 0.66},
                "hotspots": [{"title": "Finish testing", "severity": 0.54, "category": "quality"}],
                "action_candidates": [{"title": "Finish the remaining delivery work"}],
                "analyzer_results": [],
            },
            {
                "metadata": {
                    "name": "RepoC",
                    "html_url": "https://github.com/sample-user/RepoC",
                    "description": "Risky work in progress",
                    "language": "Python",
                },
                "overall_score": 0.41,
                "interest_score": 0.14,
                "grade": "D",
                "completeness_tier": "wip",
                "badges": [],
                "flags": ["no-tests"],
                "lenses": {
                    "ship_readiness": {"score": 0.41, "summary": "Thin"},
                    "showcase_value": {"score": 0.3, "summary": "Weak"},
                    "security_posture": {"score": 0.29, "summary": "Risky"},
                },
                "security_posture": {"label": "critical", "score": 0.29},
                "hotspots": [{"title": "Security posture needs attention", "severity": 0.83, "category": "security-debt"}],
                "action_candidates": [{"title": "Preview governance controls"}],
                "analyzer_results": [],
            },
        ],
        "repos_audited": 3,
        "total_repos": 3,
        "average_score": 0.63,
        "portfolio_grade": "B",
        "portfolio_health_score": 0.67,
        "tier_distribution": {"shipped": 1, "functional": 1, "wip": 1, "skeleton": 0, "abandoned": 0},
        "language_distribution": {"Python": 2, "TypeScript": 1},
        "collections": {
            "showcase": {"description": "Best examples", "repos": [{"name": "RepoA", "reason": "Strong showcase"}]},
        },
        "profiles": {"default": {"description": "Balanced"}},
        "lenses": {"ship_readiness": {"description": "Delivery readiness", "average_score": 0.71}},
        "scenario_summary": {
            "top_levers": [
                {
                    "key": "testing",
                    "title": "Strengthen tests",
                    "lens": "ship_readiness",
                    "repo_count": 2,
                    "average_expected_lens_delta": 0.1,
                    "projected_tier_promotions": 1,
                }
            ],
            "portfolio_projection": {
                "selected_repo_count": 3,
                "projected_average_score_delta": 0.04,
                "projected_tier_promotions": 1,
            },
        },
        "security_posture": {
            "average_score": 0.59,
            "critical_repos": ["RepoC"],
            "repos_with_secrets": ["RepoC"],
            "provider_coverage": {
                "github": {"available_repos": 2, "total_repos": 3},
                "scorecard": {"available_repos": 1, "total_repos": 3},
            },
            "open_alerts": {"code_scanning": 2, "secret_scanning": 1},
        },
        "security_governance_preview": [
            {
                "repo": "RepoC",
                "priority": "high",
                "title": "Enable CodeQL default setup",
                "expected_posture_lift": 0.12,
                "effort": "medium",
                "source": "github",
                "why": "Code scanning is not configured",
            }
        ],
        "campaign_summary": {
            "campaign_type": "security-review",
            "label": "Security Review",
            "action_count": 1,
            "repo_count": 1,
        },
        "writeback_preview": {
            "sync_mode": "reconcile",
            "repos": [
                {
                    "repo": "RepoC",
                    "topics": ["ghra-call-security-review"],
                    "issue_title": "[Repo Auditor] Security Review",
                    "notion_action_count": 1,
                }
            ],
        },
        "writeback_results": {
            "mode": "apply",
            "target": "github",
            "results": [
                {
                    "repo_full_name": "sample-user/RepoC",
                    "target": "github-issue",
                    "status": "created",
                    "url": "https://github.com/sample-user/RepoC/issues/1",
                }
            ],
        },
        "managed_state_drift": [
            {
                "repo_full_name": "sample-user/RepoC",
                "target": "github-issue",
                "drift_state": "managed-issue-edited",
            }
        ],
        "rollback_preview": {"available": True, "item_count": 1, "fully_reversible_count": 1},
        "review_summary": {
            "review_id": "sample-review-1",
            "status": "open",
            "source_run_id": "sample-user:2026-04-07T12:00:00+00:00",
        },
        "review_targets": [
            {
                "repo": "RepoC",
                "title": "Security posture needs attention",
                "severity": 0.83,
                "next_step": "Preview governance controls",
                "recommended_next_step": "Preview governance controls",
                "decision_hint": "ready-for-governance-approval",
                "safe_to_defer": False,
            }
        ],
        "review_history": [
            {
                "review_id": "sample-review-1",
                "generated_at": "2026-04-07T12:00:00+00:00",
                "material_change_count": 2,
                "status": "open",
                "decision_state": "needs-review",
                "sync_state": "local-only",
                "emitted": True,
            }
        ],
        "material_changes": [
            {
                "change_type": "security-change",
                "repo": "RepoC",
                "severity": 0.83,
                "title": "Security posture needs attention",
            }
        ],
        "operator_summary": {
            "headline": "There is live drift or high-severity change that needs attention now.",
            "counts": {"blocked": 0, "urgent": 2, "ready": 1, "deferred": 0},
            "watch_strategy": "adaptive",
            "watch_enabled": True,
            "watch_chosen_mode": "incremental",
            "watch_decision_reason": "adaptive-incremental",
            "watch_decision_summary": "The current baseline is still compatible, so incremental watch remains safe for the next run.",
            "next_recommended_run_mode": "incremental",
            "full_refresh_due": False,
            "source_run_id": "sample-user:2026-04-07T12:00:00+00:00",
        },
        "operator_queue": [
            {
                "item_id": "review-target:RepoC",
                "kind": "review",
                "lane": "urgent",
                "lane_label": "Needs Attention Now",
                "lane_reason": "This item shows live drift, high-severity change, or rollback exposure.",
                "priority": 83,
                "repo": "RepoC",
                "title": "Security posture needs attention",
                "summary": "Governance approval is ready.",
                "recommended_action": "Preview governance controls",
                "source_run_id": "sample-user:2026-04-07T12:00:00+00:00",
                "age_days": 0,
                "links": [],
            }
        ],
        "governance_preview": {"applyable_count": 1},
        "governance_drift": [{"repo": "RepoC", "control": "secret_scanning"}],
        "governance_summary": {
            "headline": "Governed control drift needs operator review.",
            "status": "ready",
            "needs_reapproval": False,
            "drift_count": 1,
            "applyable_count": 1,
            "applied_count": 0,
            "rollback_available_count": 1,
            "top_actions": [
                {
                    "repo": "RepoC",
                    "title": "Enable CodeQL default setup",
                    "operator_state": "ready",
                    "expected_posture_lift": 0.12,
                    "source": "github",
                    "why": "Code scanning is not configured",
                }
            ],
        },
        "watch_state": {
            "watch_enabled": True,
            "requested_strategy": "adaptive",
            "chosen_mode": "incremental",
            "next_recommended_run_mode": "incremental",
            "reason": "adaptive-incremental",
            "reason_summary": "The current baseline is still compatible, so incremental watch remains safe for the next run.",
            "full_refresh_due": False,
        },
    }


def _sheet_targets(workbook_path: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    with zipfile.ZipFile(workbook_path) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        workbook_rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
            for rel in workbook_rels
            if rel.attrib.get("Type", "").endswith("/worksheet")
        }
        visible: list[tuple[str, str]] = []
        hidden: list[tuple[str, str]] = []
        for sheet in workbook_root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
            title = sheet.attrib["name"]
            target = rel_targets[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            if sheet.attrib.get("state") == "hidden":
                hidden.append((title, target))
            else:
                visible.append((title, target))
        return visible, hidden


def _check_result(name: str, status: str, details: str) -> dict:
    return {
        "name": name,
        "status": status,
        "details": details,
    }


def _section_result(name: str, checks: list[dict]) -> dict:
    return {
        "name": name,
        "status": "passed" if all(check["status"] == "passed" for check in checks) else "failed",
        "checks": checks,
    }


def _validate_workbook_artifact(
    workbook_path: Path,
    *,
    workbook_mode: str,
    expected_visible: set[str],
) -> dict:
    checks: list[dict] = []
    wb = load_workbook(workbook_path)
    visible_sheets = {ws.title for ws in wb.worksheets if ws.sheet_state == "visible"}
    if visible_sheets != expected_visible:
        checks.append(
            _check_result(
                "visible-sheet-set",
                "failed",
                f"expected={sorted(expected_visible)} actual={sorted(visible_sheets)}",
            )
        )
    else:
        checks.append(
            _check_result(
                "visible-sheet-set",
                "passed",
                f"Visible sheets match the expected core set: {sorted(visible_sheets)}",
            )
        )

    hidden_data_sheets = [ws.title for ws in wb.worksheets if ws.title.startswith("Data_")]
    if not hidden_data_sheets:
        checks.append(_check_result("hidden-data-sheets", "failed", "No hidden Data_* sheets were found."))
    elif any(wb[name].sheet_state != "hidden" for name in hidden_data_sheets):
        checks.append(_check_result("hidden-data-sheets", "failed", "One or more Data_* sheets are visible."))
    else:
        checks.append(
            _check_result(
                "hidden-data-sheets",
                "passed",
                f"Hidden Data_* sheets stayed hidden: {sorted(hidden_data_sheets)}",
            )
        )

    visible_targets, hidden_targets = _sheet_targets(workbook_path)
    hidden_data_targets = [target for title, target in hidden_targets if title.startswith("Data_")]
    visible_table_parts: list[str] = []
    hidden_table_parts_ok = False
    with zipfile.ZipFile(workbook_path) as archive:
        for title, target in visible_targets:
            xml = archive.read(target).decode("utf-8", "ignore")
            if "<tableParts" in xml:
                visible_table_parts.append(title)
        if hidden_data_targets:
            hidden_table_parts_ok = any(
                "<tableParts" in archive.read(target).decode("utf-8", "ignore")
                for target in hidden_data_targets
            )
    if visible_table_parts:
        checks.append(
            _check_result(
                "visible-sheet-table-parts",
                "failed",
                f"Visible sheets contain table parts: {sorted(visible_table_parts)}",
            )
        )
    else:
        checks.append(
            _check_result(
                "visible-sheet-table-parts",
                "passed",
                "Visible sheets stayed filter-based with no structured table parts.",
            )
        )
    if hidden_data_targets and hidden_table_parts_ok:
        checks.append(
            _check_result(
                "hidden-data-table-parts",
                "passed",
                "Hidden Data_* sheets still contain workbook table parts for downstream bindings.",
            )
        )
    else:
        checks.append(
            _check_result(
                "hidden-data-table-parts",
                "failed",
                "Hidden Data_* sheets no longer contain workbook table parts.",
            )
        )
    return _section_result(f"{workbook_mode}-workbook-invariants", checks)


def _validate_parity(standard_path: Path, template_path: Path) -> dict:
    checks: list[dict] = []
    standard_wb = load_workbook(standard_path)
    template_wb = load_workbook(template_path)
    parity_checks = [
        ("Dashboard", "A1"),
        ("Review Queue", "B6"),
        ("Governance Controls", "B5"),
        ("Print Pack", "B9"),
    ]
    for sheet_name, cell in parity_checks:
        if standard_wb[sheet_name][cell].value != template_wb[sheet_name][cell].value:
            checks.append(
                _check_result(
                    f"{sheet_name}!{cell}",
                    "failed",
                    "Standard and template workbooks diverged on a shared top-line fact.",
                )
            )
        else:
            checks.append(
                _check_result(
                    f"{sheet_name}!{cell}",
                    "passed",
                    f"Matched value `{standard_wb[sheet_name][cell].value}` across both workbook modes.",
                )
            )
    return _section_result("cross-mode-parity", checks)


def _manual_signoff_template(standard_path: Path) -> dict:
    return {
        "status": "pending",
        "authority": "desktop-excel",
        "workbook": str(standard_path),
        "note": "Complete this manual signoff before releasing workbook-facing changes.",
        "checks": [
            {
                "id": "excel-open-no-repair",
                "label": "Open the standard workbook in desktop Excel with no repair prompt.",
                "status": "pending",
            },
            {
                "id": "visible-tabs-present",
                "label": "Confirm Index, Dashboard, Review Queue, Executive Summary, and Print Pack are present and readable.",
                "status": "pending",
            },
            {
                "id": "normal-zoom-readable",
                "label": "Confirm the standard workbook is readable at normal zoom on the core visible sheets.",
                "status": "pending",
            },
            {
                "id": "chart-placement-clean",
                "label": "Confirm charts and layout blocks are placed cleanly with no overlap.",
                "status": "pending",
            },
            {
                "id": "filters-work",
                "label": "Confirm visible filters work on the core operator sheets.",
                "status": "pending",
            },
        ],
    }


def _write_manual_checklist(output_dir: Path, manual_signoff: dict) -> Path:
    checklist_path = output_dir / "workbook-gate-checklist.md"
    checklist_path.write_text(
        "\n".join(
            [
                "# Workbook Gate Manual Checklist",
                "",
                "Open the standard workbook in desktop Excel before releasing workbook-facing changes.",
                "",
                f"- Workbook: `{manual_signoff['workbook']}`",
                f"- Status: `{manual_signoff['status']}`",
                "",
                "## Required Checks",
                "",
                *[f"- [ ] {item['label']}" for item in manual_signoff.get("checks", [])],
                "",
            ]
        )
    )
    return checklist_path


def _write_gate_summary(output_dir: Path, result: dict) -> Path:
    summary_path = output_dir / "workbook-gate-summary.md"
    automated = result.get("automated_checks", {})
    manual = result.get("manual_signoff", {})
    artifacts = result.get("artifacts", {})
    lines = [
        "# Workbook Gate Summary",
        "",
        f"- Status: `{result.get('status', 'error')}`",
        f"- Generated At: `{result.get('release_metadata', {}).get('generated_at', '')}`",
        f"- Workbook Modes Checked: `{', '.join(result.get('release_metadata', {}).get('workbook_modes', []))}`",
        f"- Standard Workbook: `{artifacts.get('standard_workbook', '')}`",
        f"- Template Workbook: `{artifacts.get('template_workbook', '')}`",
        f"- Manual Checklist: `{artifacts.get('manual_checklist', '')}`",
        "",
        "## Automated Checks",
        "",
        f"- Status: `{automated.get('status', 'failed')}`",
        "",
    ]
    for section in automated.get("sections", []):
        lines.append(f"### {section.get('name', 'section')}")
        lines.append("")
        for check in section.get("checks", []):
            marker = "PASS" if check.get("status") == "passed" else "FAIL"
            lines.append(f"- [{marker}] {check.get('name')}: {check.get('details')}")
        lines.append("")
    lines.extend(
        [
            "## Manual Excel Signoff",
            "",
            f"- Status: `{manual.get('status', 'pending')}`",
            f"- Authority: `{manual.get('authority', 'desktop-excel')}`",
            "",
        ]
    )
    for check in manual.get("checks", []):
        lines.append(f"- [ ] {check.get('label', '')}")
    lines.append("")
    summary_path.write_text("\n".join(lines))
    return summary_path


def _flatten_failed_checks(sections: list[dict]) -> list[str]:
    errors: list[str] = []
    for section in sections:
        for check in section.get("checks", []):
            if check.get("status") == "failed":
                errors.append(f"{section.get('name', 'section')}::{check.get('name', 'check')} - {check.get('details', '')}")
    return errors


def run_workbook_gate(output_dir: Path = DEFAULT_GATE_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "workbook-gate-report.json"
    report_path.write_text(json.dumps(_sample_report_data(), indent=2))

    standard_path = export_excel(report_path, output_dir / "workbook-gate-standard.xlsx", excel_mode="standard")
    template_path = export_excel(
        report_path,
        output_dir / "workbook-gate-template.xlsx",
        excel_mode="template",
        template_path=DEFAULT_TEMPLATE_PATH,
    )

    automated_sections = [
        _validate_workbook_artifact(standard_path, workbook_mode="standard", expected_visible=CORE_VISIBLE_SHEETS),
        _validate_workbook_artifact(template_path, workbook_mode="template", expected_visible=CORE_VISIBLE_SHEETS),
        _validate_parity(standard_path, template_path),
    ]
    validation_errors = _flatten_failed_checks(automated_sections)
    manual_signoff = _manual_signoff_template(standard_path)
    checklist_path = _write_manual_checklist(output_dir, manual_signoff)
    result = {
        "status": "ok" if not validation_errors else "error",
        "report_path": str(report_path),
        "standard_workbook": str(standard_path),
        "template_workbook": str(template_path),
        "manual_checklist": str(checklist_path),
        "artifacts": {
            "report_path": str(report_path),
            "standard_workbook": str(standard_path),
            "template_workbook": str(template_path),
            "manual_checklist": str(checklist_path),
        },
        "release_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workbook_modes": ["standard", "template"],
            "parity_status": automated_sections[2]["status"],
            "invariant_status": "passed" if all(section["status"] == "passed" for section in automated_sections[:2]) else "failed",
        },
        "automated_checks": {
            "status": "passed" if not validation_errors else "failed",
            "sections": automated_sections,
        },
        "manual_signoff": manual_signoff,
        "errors": validation_errors,
    }
    summary_path = _write_gate_summary(output_dir, result)
    result["gate_summary"] = str(summary_path)
    result["artifacts"]["gate_summary"] = str(summary_path)
    (output_dir / "workbook-gate-result.json").write_text(json.dumps(result, indent=2))
    return result


def format_gate_result(result: dict) -> str:
    artifacts = result.get("artifacts", {})
    lines = [
        f"Workbook gate status: {result.get('status', 'error')}",
        f"Sample report: {artifacts.get('report_path', '')}",
        f"Standard workbook: {artifacts.get('standard_workbook', '')}",
        f"Template workbook: {artifacts.get('template_workbook', '')}",
        f"Manual checklist: {artifacts.get('manual_checklist', '')}",
        f"Gate summary: {artifacts.get('gate_summary', '')}",
        f"Automated checks: {result.get('automated_checks', {}).get('status', 'failed')}",
        f"Manual signoff: {result.get('manual_signoff', {}).get('status', 'pending')}",
    ]
    errors = result.get("errors") or []
    if errors:
        lines.append("Validation errors:")
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("Validation checks passed. Final release step: complete the manual desktop Excel checklist.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="workbook-gate",
        description="Generate a canonical sample workbook pair and validate workbook release invariants.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_GATE_DIR),
        help="Directory for workbook gate artifacts (default: output/workbook-gate)",
    )
    args = parser.parse_args()
    result = run_workbook_gate(Path(args.output_dir))
    print(format_gate_result(result))
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
