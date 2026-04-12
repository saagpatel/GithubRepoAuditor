from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.models import RepoAudit, RepoMetadata
from src.registry_parser import _normalize, parse_registry, reconcile


def _make_audit(name: str, tier: str = "functional", score: float = 0.6) -> RepoAudit:
    meta = RepoMetadata(
        name=name, full_name=f"user/{name}", description=None,
        language="Python", languages={}, private=False, fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=0, forks=0, open_issues=0,
        size_kb=100, html_url=f"https://github.com/user/{name}",
        clone_url="", topics=[],
    )
    return RepoAudit(
        metadata=meta,
        analyzer_results=[],
        overall_score=score,
        completeness_tier=tier,
        flags=[],
    )


class TestNormalize:
    def test_basic(self):
        assert _normalize("MyProject") == "myproject"

    def test_strips_hyphens_underscores(self):
        assert _normalize("My-Project_Name") == "myprojectname"

    def test_strips_prod_suffix(self):
        assert _normalize("PomGambler-prod") == "pomgambler"

    def test_strips_ready_suffix(self):
        assert _normalize("DesktopPEt-ready") == "desktoppet"

    def test_strips_readiness_suffix(self):
        assert _normalize("EarthPulse-readiness") == "earthpulse"


class TestParseRegistry:
    def test_parses_simple_table(self, tmp_path):
        registry = tmp_path / "registry.md"
        registry.write_text(
            "# Projects\n\n"
            "| Project | Status | Notes |\n"
            "|---------|--------|-------|\n"
            "| Alpha | active | Good |\n"
            "| Beta | parked | Stale |\n"
            "| Gamma | archived | Legacy |\n"
        )
        result = parse_registry(registry)
        assert result == {"Alpha": "active", "Beta": "parked", "Gamma": "archived"}

    def test_skips_invalid_status(self, tmp_path):
        registry = tmp_path / "registry.md"
        registry.write_text(
            "| Project | Status |\n"
            "|---------|--------|\n"
            "| Good | active |\n"
            "| Bad | unknown_status |\n"
        )
        result = parse_registry(registry)
        assert "Good" in result
        assert "Bad" not in result

    def test_skips_summary_rows(self, tmp_path):
        registry = tmp_path / "registry.md"
        registry.write_text(
            "| Metric | Count |\n"
            "|--------|-------|\n"
            "| Total projects | 64 |\n"
            "| Active | active |\n"
        )
        result = parse_registry(registry)
        # "Total projects" should be skipped (status is "64", a digit)
        assert "Total projects" not in result

    def test_real_registry(self):
        """Test against the actual registry file if it exists."""
        path = Path.home() / "Projects" / "project-registry.md"
        if not path.exists():
            return
        result = parse_registry(path)
        assert len(result) > 50
        assert "AssistSupport" in result
        assert result["AssistSupport"] == "active"


class TestReconcile:
    def test_exact_match(self):
        registry = {"Alpha": "active", "Beta": "parked"}
        audits = [_make_audit("Alpha"), _make_audit("Beta")]
        recon = reconcile(registry, audits)
        assert len(recon.matched) == 2
        assert len(recon.on_github_not_registry) == 0
        assert len(recon.in_registry_not_github) == 0

    def test_case_insensitive_match(self):
        registry = {"alpha": "active"}
        audits = [_make_audit("Alpha")]
        recon = reconcile(registry, audits)
        assert len(recon.matched) == 1

    def test_normalized_match(self):
        registry = {"PomGambler-prod": "parked"}
        audits = [_make_audit("PomGambler")]
        recon = reconcile(registry, audits)
        # PomGambler normalizes to "pomgambler", PomGambler-prod also normalizes to "pomgambler"
        assert len(recon.matched) == 1

    def test_unmatched_github(self):
        registry = {"Alpha": "active"}
        audits = [_make_audit("Alpha"), _make_audit("NewRepo")]
        recon = reconcile(registry, audits)
        assert "NewRepo" in recon.on_github_not_registry

    def test_unmatched_registry(self):
        registry = {"Alpha": "active", "OldProject": "archived"}
        audits = [_make_audit("Alpha")]
        recon = reconcile(registry, audits)
        assert "OldProject" in recon.in_registry_not_github
