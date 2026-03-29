from __future__ import annotations

import json
from pathlib import Path

from src.badge_export import (
    ELIGIBLE_TIERS,
    GRADE_COLORS,
    TIER_COLORS,
    _make_shield_json,
    _shields_escape,
    _static_badge_url,
    _endpoint_badge_url,
    _write_badges_markdown,
    _write_portfolio_badges,
    _write_repo_badges,
    _load_gist_id,
    _save_gist_id,
    export_badges,
)


def _make_report_data(**overrides) -> dict:
    """Build a minimal report dict for testing."""
    defaults = {
        "username": "testuser",
        "generated_at": "2026-03-28T12:00:00Z",
        "repos_audited": 3,
        "average_score": 0.65,
        "portfolio_grade": "C",
        "tier_distribution": {"shipped": 1, "functional": 1, "wip": 1},
        "audits": [
            {
                "metadata": {"name": "shipped-repo", "html_url": ""},
                "overall_score": 0.80,
                "interest_score": 0.50,
                "grade": "B",
                "completeness_tier": "shipped",
                "badges": ["fresh", "fully-tested"],
            },
            {
                "metadata": {"name": "functional-repo", "html_url": ""},
                "overall_score": 0.60,
                "interest_score": 0.30,
                "grade": "C",
                "completeness_tier": "functional",
                "badges": ["fresh"],
            },
            {
                "metadata": {"name": "wip-repo", "html_url": ""},
                "overall_score": 0.40,
                "interest_score": 0.20,
                "grade": "D",
                "completeness_tier": "wip",
                "badges": [],
            },
        ],
    }
    defaults.update(overrides)
    return defaults


class TestMakeShieldJson:
    def test_schema_version(self):
        result = _make_shield_json("grade", "A", "brightgreen")
        assert result["schemaVersion"] == 1

    def test_all_fields_present(self):
        result = _make_shield_json("tier", "shipped", "green")
        assert set(result.keys()) == {"schemaVersion", "label", "message", "color"}
        assert result["label"] == "tier"
        assert result["message"] == "shipped"
        assert result["color"] == "green"


class TestStaticBadgeUrl:
    def test_simple_badge(self):
        url = _static_badge_url("grade", "A", "brightgreen")
        assert url == "https://img.shields.io/badge/grade-A-brightgreen"

    def test_dash_escaping(self):
        escaped = _shields_escape("well-documented")
        assert escaped == "well--documented"

    def test_space_encoding(self):
        url = _static_badge_url("avg score", "0.65", "yellow")
        assert "avg%20score" in url
        assert "0.65" in url

    def test_endpoint_url(self):
        url = _endpoint_badge_url("https://example.com/badge.json")
        assert url.startswith("https://img.shields.io/endpoint?url=")
        assert "example.com" in url


class TestExportBadges:
    def test_creates_badge_dirs(self, tmp_path):
        export_badges(_make_report_data(), tmp_path)
        assert (tmp_path / "badges").is_dir()
        assert (tmp_path / "badges" / "repos").is_dir()

    def test_portfolio_badges_written(self, tmp_path):
        export_badges(_make_report_data(), tmp_path)
        badges_dir = tmp_path / "badges"
        for name in ["portfolio-grade", "portfolio-repos", "portfolio-shipped", "portfolio-avg-score"]:
            path = badges_dir / f"{name}.json"
            assert path.is_file(), f"Missing {name}.json"
            data = json.loads(path.read_text())
            assert data["schemaVersion"] == 1

    def test_repo_badges_for_eligible_tiers(self, tmp_path):
        export_badges(_make_report_data(), tmp_path)
        repos_dir = tmp_path / "badges" / "repos"
        # shipped-repo and functional-repo should have grade + tier
        assert (repos_dir / "shipped-repo-grade.json").is_file()
        assert (repos_dir / "shipped-repo-tier.json").is_file()
        assert (repos_dir / "functional-repo-grade.json").is_file()
        assert (repos_dir / "functional-repo-tier.json").is_file()

    def test_skips_ineligible_tiers(self, tmp_path):
        export_badges(_make_report_data(), tmp_path)
        repos_dir = tmp_path / "badges" / "repos"
        assert not (repos_dir / "wip-repo-grade.json").exists()
        assert not (repos_dir / "wip-repo-tier.json").exists()

    def test_badges_md_created(self, tmp_path):
        result = export_badges(_make_report_data(), tmp_path)
        assert result["badges_md"].is_file()
        content = result["badges_md"].read_text()
        assert len(content) > 100

    def test_grade_color_mapping(self, tmp_path):
        export_badges(_make_report_data(), tmp_path)
        # shipped-repo has grade B
        data = json.loads((tmp_path / "badges" / "repos" / "shipped-repo-grade.json").read_text())
        assert data["message"] == "B"
        assert data["color"] == "green"
        # functional-repo has grade C
        data = json.loads((tmp_path / "badges" / "repos" / "functional-repo-grade.json").read_text())
        assert data["message"] == "C"
        assert data["color"] == "yellow"

    def test_files_written_count(self, tmp_path):
        result = export_badges(_make_report_data(), tmp_path)
        # 4 portfolio + 2 eligible repos * 2 each + 1 badges.md = 9
        assert result["files_written"] == 9


class TestBadgesMarkdown:
    def test_has_portfolio_section(self, tmp_path):
        _write_badges_markdown(_make_report_data(), tmp_path)
        content = (tmp_path / "badges.md").read_text()
        assert "## Portfolio Badges" in content

    def test_has_repo_section(self, tmp_path):
        _write_badges_markdown(_make_report_data(), tmp_path)
        content = (tmp_path / "badges.md").read_text()
        assert "## Per-Repo Badges" in content

    def test_static_urls_present(self, tmp_path):
        _write_badges_markdown(_make_report_data(), tmp_path)
        content = (tmp_path / "badges.md").read_text()
        assert "img.shields.io/badge/" in content

    def test_endpoint_urls_when_gist(self, tmp_path):
        gist_urls = {"portfolio-grade.json": "https://gist.githubusercontent.com/user/abc/raw/portfolio-grade.json"}
        _write_badges_markdown(_make_report_data(), tmp_path, gist_urls=gist_urls)
        content = (tmp_path / "badges.md").read_text()
        assert "img.shields.io/endpoint" in content
        assert "## Endpoint Badges" in content

    def test_no_endpoint_without_gist(self, tmp_path):
        _write_badges_markdown(_make_report_data(), tmp_path)
        content = (tmp_path / "badges.md").read_text()
        assert "Endpoint Badges" not in content


class TestGistIdPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        _save_gist_id(tmp_path, "abc123")
        assert _load_gist_id(tmp_path) == "abc123"

    def test_load_returns_none_when_missing(self, tmp_path):
        assert _load_gist_id(tmp_path) is None
