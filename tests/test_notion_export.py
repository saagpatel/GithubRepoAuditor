from __future__ import annotations

import json

from src.notion_export import (
    _build_event_key,
    _find_biggest_drag,
    _normalize_audit_event,
    _severity_from_grade,
    export_notion_events,
)


def _make_report(**overrides) -> dict:
    defaults = {
        "username": "testuser",
        "generated_at": "2026-03-28T12:00:00Z",
        "repos_audited": 2,
        "average_score": 0.60,
        "portfolio_grade": "C",
        "tier_distribution": {"shipped": 1, "wip": 1},
        "audits": [
            {
                "metadata": {"name": "MappedRepo", "html_url": "https://github.com/user/MappedRepo"},
                "overall_score": 0.80,
                "interest_score": 0.50,
                "grade": "B",
                "completeness_tier": "shipped",
                "badges": ["fresh", "fully-tested"],
                "flags": [],
                "analyzer_results": [
                    {"dimension": "testing", "score": 0.9, "max_score": 1.0, "findings": [], "details": {}},
                    {"dimension": "readme", "score": 0.4, "max_score": 1.0, "findings": [], "details": {}},
                ],
            },
            {
                "metadata": {"name": "UnmappedRepo", "html_url": "https://github.com/user/UnmappedRepo"},
                "overall_score": 0.30,
                "interest_score": 0.10,
                "grade": "F",
                "completeness_tier": "wip",
                "badges": [],
                "flags": ["no-tests"],
                "analyzer_results": [
                    {"dimension": "testing", "score": 0.0, "max_score": 1.0, "findings": [], "details": {}},
                ],
            },
        ],
    }
    defaults.update(overrides)
    return defaults


def _write_map(tmp_path, mapping):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "notion-project-map.json").write_text(json.dumps(mapping))
    return config_dir


class TestSeverityMapping:
    def test_a_is_info(self):
        assert _severity_from_grade("A") == "Info"

    def test_b_is_info(self):
        assert _severity_from_grade("B") == "Info"

    def test_c_is_watch(self):
        assert _severity_from_grade("C") == "Watch"

    def test_d_is_watch(self):
        assert _severity_from_grade("D") == "Watch"

    def test_f_is_risk(self):
        assert _severity_from_grade("F") == "Risk"


class TestEventKey:
    def test_format(self):
        key = _build_event_key("MyRepo", "2026-03-28", "B")
        assert key == "audit::report::myrepo::2026-03-28::b"

    def test_lowercased(self):
        key = _build_event_key("CryptForge", "2026-01-01", "A")
        assert "cryptforge" in key
        assert "a" == key.split("::")[-1]


class TestNormalizeEvent:
    def test_mapped_repo_produces_event(self):
        audit = _make_report()["audits"][0]
        mapping = {"MappedRepo": {"localProjectId": "uuid-123"}}
        event = _normalize_audit_event(audit, "2026-03-28", mapping)
        assert event is not None
        assert event["provider"] == "Audit"
        assert event["signalType"] == "Audit Report"
        assert event["localProjectId"] == "uuid-123"
        assert "Grade B" in event["title"]
        assert event["machineData"]["overall_score"] == 0.8
        assert event["machineData"]["interest_score"] == 0.5
        assert event["machineData"]["completeness_tier"] == "shipped"
        assert event["machineData"]["grade"] == "B"
        assert event["machineData"]["badges"] == ["fresh", "fully-tested"]
        assert event["machineData"]["flags"] == []
        assert "Dimensions:" in event["rawExcerpt"]
        assert not event["rawExcerpt"].lstrip().startswith("{")

    def test_raw_excerpt_truncates_safely(self):
        audit = _make_report()["audits"][0]
        audit["badges"] = [f"badge-{i}" for i in range(400)]
        audit["flags"] = [f"flag-{i}" for i in range(400)]
        audit["analyzer_results"] = [
            {"dimension": f"dim-{i}", "score": 0.5, "max_score": 1.0, "findings": [], "details": {}}
            for i in range(400)
        ]
        mapping = {"MappedRepo": {"localProjectId": "uuid-123"}}
        event = _normalize_audit_event(audit, "2026-03-28", mapping)
        assert event is not None
        assert len(event["rawExcerpt"]) <= 2000
        assert event["rawExcerpt"].endswith("...")
        assert event["machineData"]["dimension_scores"]["dim-0"] == 0.5

    def test_unmapped_repo_returns_none(self):
        audit = _make_report()["audits"][1]
        mapping = {"MappedRepo": {"localProjectId": "uuid-123"}}
        event = _normalize_audit_event(audit, "2026-03-28", mapping)
        assert event is None


class TestBiggestDrag:
    def test_finds_lowest(self):
        audit = _make_report()["audits"][0]
        dim, score = _find_biggest_drag(audit)
        assert dim == "readme"
        assert score == 0.4


class TestExportNotionEvents:
    def test_creates_json_file(self, tmp_path):
        config_dir = _write_map(tmp_path, {"MappedRepo": {"localProjectId": "uuid-123"}})
        result = export_notion_events(_make_report(), tmp_path / "output", config_dir)
        assert result["events_path"].is_file()

    def test_event_count_matches_mapped(self, tmp_path):
        config_dir = _write_map(tmp_path, {"MappedRepo": {"localProjectId": "uuid-123"}})
        result = export_notion_events(_make_report(), tmp_path / "output", config_dir)
        assert result["event_count"] == 1

    def test_unmapped_repos_collected(self, tmp_path):
        config_dir = _write_map(tmp_path, {"MappedRepo": {"localProjectId": "uuid-123"}})
        result = export_notion_events(_make_report(), tmp_path / "output", config_dir)
        assert "UnmappedRepo" in result["unmapped"]

    def test_json_has_correct_structure(self, tmp_path):
        config_dir = _write_map(tmp_path, {"MappedRepo": {"localProjectId": "uuid-123"}})
        result = export_notion_events(_make_report(), tmp_path / "output", config_dir)
        data = json.loads(result["events_path"].read_text())
        assert data["version"] == 1
        assert "events" in data
        assert "stats" in data
        assert data["stats"]["mapped_repos"] == 1
        assert data["stats"]["unmapped_repos"] == 1

    def test_exported_events_include_machine_data(self, tmp_path):
        config_dir = _write_map(tmp_path, {"MappedRepo": {"localProjectId": "uuid-123"}})
        result = export_notion_events(_make_report(), tmp_path / "output", config_dir)
        data = json.loads(result["events_path"].read_text())
        event = data["events"][0]
        assert event["machineData"]["overall_score"] == 0.8
        assert event["machineData"]["interest_score"] == 0.5
        assert event["machineData"]["grade"] == "B"
        assert event["machineData"]["badges"] == ["fresh", "fully-tested"]

    def test_empty_map_produces_zero_events(self, tmp_path):
        config_dir = _write_map(tmp_path, {})
        result = export_notion_events(_make_report(), tmp_path / "output", config_dir)
        assert result["event_count"] == 0
        assert len(result["unmapped"]) == 2
