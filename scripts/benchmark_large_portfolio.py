from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from _bootstrap import ensure_project_root

ROOT = ensure_project_root()


def _load_export_tools() -> tuple[object, object, object]:
    from src.excel_export import export_excel
    from src.report_enrichment import build_score_explanation
    from src.web_export import export_html_dashboard

    return export_excel, build_score_explanation, export_html_dashboard

FIXTURE_PATH = ROOT / "fixtures" / "demo" / "sample-report.json"
OUTPUT_PATH = ROOT / "output" / "demo" / "benchmark-results.json"


def _large_fixture(target_repos: int = 90) -> dict:
    _, build_score_explanation, _ = _load_export_tools()
    base = json.loads(FIXTURE_PATH.read_text())
    template_audits = base.get("audits", [])
    audits = []
    for index in range(target_repos):
        seed = deepcopy(template_audits[index % len(template_audits)])
        repo_name = f"{seed['metadata']['name']}-{index + 1:03d}"
        seed["metadata"]["name"] = repo_name
        seed["metadata"]["full_name"] = f"sample-user/{repo_name}"
        seed["metadata"]["html_url"] = f"https://github.com/sample-user/{repo_name}"
        audits.append(seed)
    base["audits"] = audits
    base["repos_audited"] = len(audits)
    base["total_repos"] = len(audits)
    base["collections"]["showcase"]["repos"] = [
        {"name": audits[0]["metadata"]["name"], "reason": "Still the strongest example."},
        {"name": audits[1]["metadata"]["name"], "reason": "Solid follow-through."},
    ]
    for audit in audits:
        audit["score_explanation"] = build_score_explanation(audit)
    return base


def main() -> None:
    export_excel, _, export_html_dashboard = _load_export_tools()
    report_data = _large_fixture()
    start = perf_counter()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        report_path = temp_root / "benchmark-report.json"
        report_path.write_text(json.dumps(report_data, indent=2))

        workbook_start = perf_counter()
        export_excel(report_path, temp_root / "benchmark.xlsx", excel_mode="standard")
        workbook_seconds = perf_counter() - workbook_start

        html_start = perf_counter()
        export_html_dashboard(report_data, temp_root)
        html_seconds = perf_counter() - html_start

    total_seconds = perf_counter() - start
    results = {
        "fixture_repo_count": report_data["repos_audited"],
        "total_runtime_seconds": round(total_seconds, 3),
        "clone_fetch_seconds": None,
        "analyzer_seconds": None,
        "workbook_build_seconds": round(workbook_seconds, 3),
        "html_build_seconds": round(html_seconds, 3),
        "notes": "This benchmark uses a committed large-fixture report, so live clone and analyzer timing are intentionally not exercised here.",
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"Benchmark results written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
