from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.operator_control_center import control_center_artifact_payload, render_control_center_markdown
from src.report_enrichment import build_run_change_counts, build_run_change_summary, build_score_explanation
from src.web_export import export_html_dashboard
from src.excel_export import export_excel

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


if __name__ == "__main__":
    main()
