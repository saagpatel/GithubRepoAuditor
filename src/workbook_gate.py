from __future__ import annotations

import argparse
import json
import zipfile
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


def _validate_workbook_artifact(workbook_path: Path, *, expected_visible: set[str]) -> list[str]:
    errors: list[str] = []
    wb = load_workbook(workbook_path)
    visible_sheets = {ws.title for ws in wb.worksheets if ws.sheet_state == "visible"}
    if visible_sheets != expected_visible:
        errors.append(
            "Visible sheet set mismatch: "
            f"expected={sorted(expected_visible)} actual={sorted(visible_sheets)}"
        )

    hidden_data_sheets = [ws.title for ws in wb.worksheets if ws.title.startswith("Data_")]
    if not hidden_data_sheets:
        errors.append("No hidden Data_* sheets were found.")
    elif any(wb[name].sheet_state != "hidden" for name in hidden_data_sheets):
        errors.append("One or more Data_* sheets are visible.")

    visible_targets, hidden_targets = _sheet_targets(workbook_path)
    hidden_data_targets = [target for title, target in hidden_targets if title.startswith("Data_")]
    with zipfile.ZipFile(workbook_path) as archive:
        for title, target in visible_targets:
            xml = archive.read(target).decode("utf-8", "ignore")
            if "<tableParts" in xml:
                errors.append(f"Visible sheet {title} contains table parts.")
        if hidden_data_targets:
            if not any("<tableParts" in archive.read(target).decode("utf-8", "ignore") for target in hidden_data_targets):
                errors.append("Hidden Data_* sheets no longer contain workbook table parts.")
    return errors


def _validate_parity(standard_path: Path, template_path: Path) -> list[str]:
    errors: list[str] = []
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
            errors.append(f"Parity mismatch at {sheet_name}!{cell}.")
    return errors


def _write_manual_checklist(output_dir: Path, standard_path: Path) -> Path:
    checklist_path = output_dir / "workbook-gate-checklist.md"
    checklist_path.write_text(
        "\n".join(
            [
                "# Workbook Gate Manual Checklist",
                "",
                "Open the standard workbook in desktop Excel before releasing workbook-facing changes.",
                "",
                f"- Workbook: `{standard_path}`",
                "- Confirm Excel opens the file without a repair prompt.",
                "- Confirm `Index`, `Dashboard`, `Review Queue`, `Executive Summary`, and `Print Pack` are readable at normal zoom.",
                "- Confirm visible filters work on the core operator sheets.",
                "- Confirm charts and layout blocks are placed cleanly and do not overlap.",
                "",
            ]
        )
    )
    return checklist_path


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

    validation_errors = []
    validation_errors.extend(_validate_workbook_artifact(standard_path, expected_visible=CORE_VISIBLE_SHEETS))
    validation_errors.extend(_validate_workbook_artifact(template_path, expected_visible=CORE_VISIBLE_SHEETS))
    validation_errors.extend(_validate_parity(standard_path, template_path))

    checklist_path = _write_manual_checklist(output_dir, standard_path)
    result = {
        "status": "ok" if not validation_errors else "error",
        "report_path": str(report_path),
        "standard_workbook": str(standard_path),
        "template_workbook": str(template_path),
        "manual_checklist": str(checklist_path),
        "errors": validation_errors,
    }
    (output_dir / "workbook-gate-result.json").write_text(json.dumps(result, indent=2))
    return result


def format_gate_result(result: dict) -> str:
    lines = [
        f"Workbook gate status: {result.get('status', 'error')}",
        f"Sample report: {result.get('report_path', '')}",
        f"Standard workbook: {result.get('standard_workbook', '')}",
        f"Template workbook: {result.get('template_workbook', '')}",
        f"Manual checklist: {result.get('manual_checklist', '')}",
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
