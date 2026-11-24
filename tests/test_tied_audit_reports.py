import json
import os

from github_repo_auditor.portfolio_truth_status import (
    latest_audit_report_path,
    load_degraded_dimensions_by_name,
    load_release_count_by_name,
    load_repo_status_from_audit_by_name,
)


def test_tied_audit_reports_choose_the_same_path(tmp_path, monkeypatch):
    older, newer = [
        tmp_path / f"audit-report-fixture-{day}.json" for day in ("01", "02")
    ]
    for path, count, degraded in ((older, 1, []), (newer, 7, ["testing"])):
        audit = {
            "metadata": {"name": "example", "archived": path == newer},
            "degraded_dimensions": degraded,
            "analyzer_results": [
                {"dimension": "activity", "details": {"release_count": count}}
            ],
        }
        path.write_text(json.dumps({"audits": [audit]}))
        os.utime(path, ns=(1000000000, 1000000000))
    for order in ([older, newer], [newer, older]):
        monkeypatch.setattr(type(tmp_path), "glob", lambda self, pattern: iter(order))
        assert (
            latest_audit_report_path(output_dir=tmp_path, username="fixture") == newer
        )
        args = {"output_dir": tmp_path, "username": "fixture"}
        assert (
            load_repo_status_from_audit_by_name(**args)["example"]["archived"] is True
        )
        assert load_release_count_by_name(**args) == {"example": 7}
        assert load_degraded_dimensions_by_name(**args) == {"example": ["testing"]}
