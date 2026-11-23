import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from github_repo_auditor import portfolio_truth_sources
from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth


def test_pinned_publication_clock_controls_cached_notion_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2025, 2, 1, tzinfo=timezone.utc)
    workspace = tmp_path / "workspace"
    project = workspace / "sample"
    project.mkdir(parents=True)
    (project / "README.md").write_text("# Sample\n")
    snapshot = tmp_path / "advisory.json"
    projects = [{"title": "sample", "portfolio_call": "Maintain"}]
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "generated_at": clock.isoformat(),
                "project_count": 1,
                "projects": projects,
                "content_sha256": hashlib.sha256(
                    json.dumps(projects, separators=(",", ":")).encode()
                ).hexdigest(),
                "live_read_receipt": {"state": "verified", "page_count": 1},
                "attention_authority_receipt": {"state": "verified"},
            }
        )
    )
    monkeypatch.setenv("GHRA_NOTION_SNAPSHOT_PATH", str(snapshot))
    monkeypatch.setattr(
        portfolio_truth_sources, "load_notion_project_context", lambda _: {}
    )
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_publish.load_source_paths",
        lambda _: dict(bridge_db=None, notion_snapshot=None, memory_dir=None),
    )

    class WallClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return wall_time.astimezone(tz)

    monkeypatch.setattr(portfolio_truth_sources, "datetime", WallClock)
    publications = []
    for elapsed_days in (0, 30):
        wall_time = clock + timedelta(days=elapsed_days)
        generation = publish_portfolio_truth(
            workspace_root=workspace,
            output_dir=tmp_path / f"published-{elapsed_days}",
            registry_output=workspace / "registry.md",
            portfolio_report_output=workspace / "report.md",
            catalog_path=tmp_path / "missing.yaml",
            include_notion=True,
            now=clock,
        )
        publications.append(
            (
                generation.latest_path.read_bytes(),
                generation.portfolio_report_output.read_bytes(),
            )
        )

    assert [
        json.loads(payload)["source_summary"]["notion_context_rows"]
        for payload, _ in publications
    ] == [1, 1]
    assert publications[0] == publications[1]
