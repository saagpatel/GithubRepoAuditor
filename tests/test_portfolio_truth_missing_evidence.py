from copy import deepcopy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth


@pytest.mark.parametrize("catalog_state", ["missing", "unreadable"])
def test_no_evidence_publishes_unknown_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_state: str
) -> None:
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_publish.load_source_paths",
        lambda _: dict(bridge_db=None, notion_snapshot=None, memory_dir=None),
    )
    workspace = tmp_path / "workspace"
    project = workspace / "sample"
    project.mkdir(parents=True)
    (project / "sample.bin").touch()
    catalog = tmp_path / "catalog.yaml"
    if catalog_state == "unreadable":
        catalog.write_text("repos:\n  sample:\n    lifecycle_state: archived\n")
        original_open = Path.open

        def open_catalog(path, *args, **kwargs):
            if path == catalog:
                raise PermissionError("fixture catalog unavailable")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", open_catalog)
    result = publish_portfolio_truth(
        workspace_root=workspace,
        output_dir=tmp_path / "published",
        registry_output=workspace / "registry.md",
        portfolio_report_output=workspace / "report.md",
        catalog_path=catalog,
        include_notion=False,
        now=datetime(2025, 1, 3, tzinfo=timezone.utc),
    )
    snapshot = json.loads(result.latest_path.read_bytes())
    assert snapshot["inputs"]["catalog"]["sha256"] is None
    if catalog_state == "unreadable":
        assert snapshot["source_summary"]["catalog_errors"]
    (row,) = snapshot["projects"]
    facts = row["derived"]
    assert facts["last_meaningful_activity_at"] is None
    assert (
        facts["activity_status"],
        facts["attention_state"],
        facts.get("archived"),
    ) == ("unknown", "unknown", None)
    assert "github.archived" not in row["provenance"]
    assert row["declared"]["lifecycle_state"] == ""
    assert "| unknown | unknown |" in result.portfolio_report_output.read_text()


def test_prior_012_snapshot_remains_readable_after_schema_upgrade(
    tmp_path: Path,
) -> None:
    from github_repo_auditor.portfolio_truth_reconcile import (
        build_portfolio_truth_snapshot,
    )
    from github_repo_auditor.portfolio_truth_validate import (
        canonicalize_prior_security_truth_payload,
    )

    workspace = tmp_path / "workspace"
    project = workspace / "sample"
    project.mkdir(parents=True)
    (project / "README.md").write_text("# Sample\n")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("repos:\n  sample:\n    lifecycle_state: archived\n")
    payload = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog,
        legacy_registry_path=tmp_path / "missing-registry.md",
        include_notion=False,
        now=datetime(2026, 8, 3, tzinfo=timezone.utc),
    ).snapshot.to_dict()
    payload["schema_version"] = "0.12.0"

    canonical = canonicalize_prior_security_truth_payload(payload)

    assert canonical["schema_version"] == "0.13.0"

    invalid_values = (
        ("archived", None, "boolean derived.archived"),
        ("activity_status", "unknown", "derived.activity_status"),
        ("attention_state", "unknown", "derived.attention_state"),
    )
    for field, value, message in invalid_values:
        legacy_payload = deepcopy(payload)
        legacy_payload["projects"][0]["derived"][field] = value
        with pytest.raises(ValueError, match=f"Prior PortfolioTruth 0.12.0.*{message}"):
            canonicalize_prior_security_truth_payload(legacy_payload)
