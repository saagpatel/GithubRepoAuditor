import json
import subprocess
from datetime import datetime, timezone

from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth


def test_snapshot_bytes_ignore_security_metadata_key_order(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_publish.load_source_paths",
        lambda _: dict(bridge_db=None, notion_snapshot=None, memory_dir=None),
    )
    workspace = tmp_path / "workspace"
    repo = workspace / "sample"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "README.md").write_text("Sample")
    clock = datetime(2025, 1, 3, tzinfo=timezone.utc)
    metadata = {
        "source_id": "github-security-coverage-receipt",
        "schema_version": "GitHubSecurityCoverageReceiptV1",
        "produced_at": clock.isoformat(),
        "state": "fresh",
        "age_hours": 0.0,
        "producer_commit": "a" * 40,
        "cohort_policy": "portfolio-default-attention-v1",
        "cohort_repository_count": 0,
        "path": "fixture-receipt.json",
    }
    publications = []
    for index, evidence in enumerate((metadata, dict(reversed(metadata.items())))):
        generation = publish_portfolio_truth(
            workspace_root=workspace,
            output_dir=tmp_path / f"generation-{index}",
            registry_output=workspace / "registry.md",
            portfolio_report_output=workspace / "report.md",
            catalog_path=tmp_path / "missing.yaml",
            include_notion=False,
            now=clock,
            security_coverage_metadata=evidence,
        )
        publications.append(generation.latest_path.read_bytes())
    assert json.loads(publications[0]) == json.loads(publications[1])
    assert publications[0] == publications[1]
