from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from src.repo_improver import (
    apply_file_updates,
    apply_metadata_updates,
    apply_readme_updates,
    generate_execution_report,
    generate_manifest,
    load_improvements,
    partition_by_tier,
    partition_into_batches,
    write_manifest,
)


def _make_audit(name: str, tier: str, score: float, *, description: str | None = "A desc", topics: list[str] | None = None) -> dict:
    """Build a minimal audit dict for testing manifest generation."""
    return {
        "metadata": {
            "name": name,
            "full_name": f"user/{name}",
            "description": description,
            "language": "Python",
            "languages": {"Python": 5000},
            "topics": topics or [],
        },
        "completeness_tier": tier,
        "overall_score": score,
        "analyzer_results": [
            {
                "dimension": "readme",
                "score": 0.7,
                "details": {
                    "has_readme": True,
                    "has_badges": False,
                    "has_install_instructions": True,
                    "has_code_examples": False,
                },
            },
            {"dimension": "code_quality", "score": 0.6, "details": {"entry_point": "src/main.py"}},
            {"dimension": "cicd", "score": 0.8, "details": {}},
            {"dimension": "structure", "score": 0.7, "details": {"has_license": True, "config_files": ["pyproject.toml"]}},
            {"dimension": "dependencies", "score": 0.5, "details": {"dep_count": 3}},
            {"dimension": "testing", "score": 0.6, "details": {}},
        ],
        "badges": {"earned": ["ci-champion"]},
        "interest_tier": "notable",
    }


def _make_report(*audits: dict) -> dict:
    return {"audits": list(audits)}


class TestGenerateManifest:
    def test_sorts_by_tier_then_score(self):
        report = _make_report(
            _make_audit("wip-repo", "wip", 0.4),
            _make_audit("top-shipped", "shipped", 0.9),
            _make_audit("mid-shipped", "shipped", 0.8),
            _make_audit("func-repo", "functional", 0.7),
        )
        manifest = generate_manifest(report)
        names = [e["name"] for e in manifest]
        assert names == ["top-shipped", "mid-shipped", "func-repo", "wip-repo"]

    def test_detects_missing_description(self):
        report = _make_report(_make_audit("no-desc", "shipped", 0.8, description=None))
        manifest = generate_manifest(report)
        assert manifest[0]["actions"]["needs_description"] is True

    def test_detects_existing_description(self):
        report = _make_report(_make_audit("has-desc", "shipped", 0.8, description="My project"))
        manifest = generate_manifest(report)
        assert manifest[0]["actions"]["needs_description"] is False

    def test_detects_missing_topics(self):
        report = _make_report(_make_audit("no-topics", "functional", 0.6, topics=[]))
        manifest = generate_manifest(report)
        assert manifest[0]["actions"]["needs_topics"] is True

    def test_detects_existing_topics(self):
        report = _make_report(_make_audit("has-topics", "functional", 0.6, topics=["python", "cli"]))
        manifest = generate_manifest(report)
        assert manifest[0]["actions"]["needs_topics"] is False

    def test_detects_missing_badges(self):
        report = _make_report(_make_audit("repo", "shipped", 0.8))
        manifest = generate_manifest(report)
        assert manifest[0]["actions"]["needs_readme_badges"] is True

    def test_context_includes_project_metadata(self):
        report = _make_report(_make_audit("repo", "shipped", 0.8))
        manifest = generate_manifest(report)
        ctx = manifest[0]["context"]
        assert ctx["has_cicd"] is True
        assert ctx["has_license"] is True
        assert ctx["entry_point"] == "src/main.py"
        assert "ci-champion" in ctx["badges_earned"]


class TestPartitioning:
    def test_partition_by_tier(self):
        manifest = [
            {"tier": "shipped", "name": "a"},
            {"tier": "functional", "name": "b"},
            {"tier": "shipped", "name": "c"},
        ]
        tiers = partition_by_tier(manifest)
        assert len(tiers["shipped"]) == 2
        assert len(tiers["functional"]) == 1

    def test_partition_into_batches(self):
        entries = [{"name": f"repo-{i}"} for i in range(25)]
        batches = partition_into_batches(entries, batch_size=10)
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[2]) == 5


class TestManifestIO:
    def test_write_and_load(self, tmp_path):
        manifest = [{"repo": "user/repo1", "name": "repo1", "tier": "shipped"}]
        path = write_manifest(manifest, tmp_path)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded[0]["name"] == "repo1"

    def test_load_improvements_dict_format(self, tmp_path):
        data = {"user/repo1": {"description": "Cool project", "topics": ["python"]}}
        path = tmp_path / "improvements.json"
        path.write_text(json.dumps(data))
        result = load_improvements(path)
        assert result["user/repo1"]["description"] == "Cool project"

    def test_load_improvements_list_format(self, tmp_path):
        data = [{"repo": "user/repo1", "description": "Cool project"}]
        path = tmp_path / "improvements.json"
        path.write_text(json.dumps(data))
        result = load_improvements(path)
        assert "user/repo1" in result


class TestApplyMetadata:
    def test_dry_run_creates_no_api_calls(self):
        class FakeClient:
            calls = []
            def update_repo_metadata(self, *a, **kw):
                self.calls.append(("metadata", a, kw))
            def replace_repo_topics(self, *a, **kw):
                self.calls.append(("topics", a, kw))

        client = FakeClient()
        updates = [{"name": "repo1", "description": "New desc", "topics": ["python"]}]
        results = apply_metadata_updates(client, "owner", updates, dry_run=True)
        assert len(client.calls) == 0
        assert len(results[0]["actions"]) == 2
        assert results[0]["actions"][0]["dry_run"] is True

    def test_applies_description_and_topics(self):
        class FakeClient:
            def update_repo_metadata(self, owner, repo, *, description=None, homepage=None):
                return {"ok": True}
            def replace_repo_topics(self, owner, repo, topics):
                return {"ok": True}

        results = apply_metadata_updates(
            FakeClient(), "owner",
            [{"name": "repo1", "description": "New desc", "topics": ["python"]}],
        )
        assert len(results[0]["actions"]) == 2
        assert all(a["ok"] for a in results[0]["actions"])


class TestApplyReadmes:
    def test_dry_run_skips_api(self):
        class FakeClient:
            calls = []
            def get_file_sha(self, *a, **kw):
                self.calls.append("get_sha")
            def update_repo_file(self, *a, **kw):
                self.calls.append("update_file")

        client = FakeClient()
        updates = [{"name": "repo1", "readme": "# Hello\n\nCool project."}]
        results = apply_readme_updates(client, "owner", updates, dry_run=True)
        assert len(client.calls) == 0
        assert results[0]["dry_run"] is True
        assert results[0]["readme_length"] > 0

    def test_pushes_readme_with_sha(self):
        class FakeClient:
            def get_file_sha(self, owner, repo, path):
                return "abc123"
            def update_repo_file(self, owner, repo, path, content_b64, message, *, sha=None):
                decoded = base64.b64decode(content_b64).decode("utf-8")
                return {"ok": True, "sha": "new_sha", "decoded": decoded}

        results = apply_readme_updates(
            FakeClient(), "owner",
            [{"name": "repo1", "readme": "# Updated README"}],
        )
        assert results[0]["ok"] is True

    def test_skips_empty_readme(self):
        results = apply_readme_updates(
            None, "owner",  # client not used since readme is empty
            [{"name": "repo1", "readme": ""}],
        )
        assert len(results) == 0


class TestApplyFileUpdates:
    def test_dry_run_skips_api(self):
        updates = [{"name": "repo1", "path": "SECURITY.md", "content": "# Security"}]
        results = apply_file_updates(None, "owner", updates, dry_run=True)
        assert results[0]["dry_run"] is True
        assert results[0]["path"] == "SECURITY.md"

    def test_pushes_file(self):
        class FakeClient:
            def get_file_sha(self, owner, repo, path):
                return None
            def update_repo_file(self, owner, repo, path, content_b64, message, *, sha=None):
                return {"ok": True}

        updates = [{"name": "repo1", "path": "LICENSE", "content": "MIT License", "message": "chore: add LICENSE"}]
        results = apply_file_updates(FakeClient(), "owner", updates)
        assert results[0]["ok"] is True


class TestExecutionReport:
    def test_writes_summary(self, tmp_path):
        results = [
            {"repo": "repo1", "ok": True},
            {"repo": "repo2", "ok": False},
            {"repo": "repo3", "dry_run": True},
        ]
        path = generate_execution_report(results, tmp_path)
        data = json.loads(path.read_text())
        assert data["total"] == 3
        assert data["successful"] == 1
        assert data["failed"] == 1
        assert data["dry_run"] == 1
