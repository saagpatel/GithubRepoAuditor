import hashlib
import json
import os
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from github_repo_auditor import portfolio_truth_sources
from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot


@pytest.fixture(autouse=True)
def _restore_host_timezone() -> Iterator[None]:
    saved = os.environ.get("TZ")
    yield
    if saved is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = saved
    time.tzset()


def _set_host_timezone(name: str) -> None:
    os.environ["TZ"] = name
    time.tzset()


@pytest.mark.parametrize(
    ("minutes_ahead", "host_tz", "offsetless"),
    [
        (0, "UTC", False),
        (1, "UTC", False),
        (0, "UTC", True),
        (0, "America/Los_Angeles", True),
    ],
    ids=["current", "future", "offsetless-utc-host", "offsetless-pacific-host"],
)
def test_pinned_publication_clock_controls_cached_notion_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    minutes_ahead: int,
    host_tz: str,
    offsetless: bool,
) -> None:
    _set_host_timezone(host_tz)
    clock = datetime(2025, 2, 1, tzinfo=timezone.utc)
    receipt_time = clock + timedelta(minutes=minutes_ahead)
    if offsetless:
        receipt_time = receipt_time.replace(tzinfo=None)
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
                "generated_at": receipt_time.isoformat(),
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

    assert publications[0] == publications[1]
    published = json.loads(publications[0][0])
    if offsetless:
        assert published["inputs"]["notion"]["mode"] == "unavailable"
        assert published["source_summary"]["notion_context_rows"] == 0
    elif minutes_ahead:
        assert published["inputs"]["notion"]["mode"] == "unavailable"
        assert published["source_summary"]["notion_context_rows"] == 0
        assert "after the report clock" in caplog.text
    else:
        assert published["inputs"]["notion"]["mode"] == "verified-snapshot"
        assert published["source_summary"]["notion_context_rows"] == 1


def test_snapshot_builder_rejects_naive_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_reconcile.load_portfolio_catalog",
        lambda _: pytest.fail("loaded catalog before validating report clock"),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_portfolio_truth_snapshot(
            workspace_root=tmp_path, now=datetime(2025, 2, 1)
        )


def test_notion_verifier_rejects_naive_clock_before_loading_receipt(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        portfolio_truth_sources.verified_notion_snapshot(
            tmp_path / "missing.json", now=datetime(2025, 2, 1)
        )
