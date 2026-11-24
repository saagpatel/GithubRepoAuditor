import os

from github_repo_auditor.portfolio_truth_status import latest_audit_report_path


def test_tied_audit_reports_choose_the_same_path(tmp_path, monkeypatch):
    older, newer = [
        tmp_path / f"audit-report-fixture-{day}.json" for day in ("01", "02")
    ]
    for path in (older, newer):
        path.write_text("{}")
        os.utime(path, ns=(1000000000, 1000000000))
    for order in ([older, newer], [newer, older]):
        monkeypatch.setattr(type(tmp_path), "glob", lambda self, pattern: iter(order))
        assert (
            latest_audit_report_path(output_dir=tmp_path, username="fixture") == newer
        )
