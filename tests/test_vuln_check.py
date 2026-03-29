"""Tests for OSV.dev vulnerability checking."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.vuln_check import (
    ECOSYSTEM_MAP,
    check_vulnerabilities,
    format_vuln_summary,
)


def _make_audit(repo_name: str, dep_versions: list[tuple]) -> dict:
    """Build a minimal audit dict with dependency dep_versions."""
    return {
        "metadata": {"name": repo_name},
        "analyzer_results": [
            {
                "dimension": "dependencies",
                "score": 0.5,
                "details": {
                    "dep_versions": dep_versions,
                },
            }
        ],
    }


def _osv_response(vulns_per_query: list[list[dict]]) -> MagicMock:
    """Build a mock requests.post response with OSV batch format."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [{"vulns": v} for v in vulns_per_query]
    }
    return mock_resp


class TestCheckVulnerabilities:
    def test_returns_empty_when_no_audits(self) -> None:
        result = check_vulnerabilities([])
        assert result == {}

    def test_returns_empty_when_no_dep_versions(self) -> None:
        audit = {
            "metadata": {"name": "empty-repo"},
            "analyzer_results": [
                {"dimension": "dependencies", "score": 1.0, "details": {}}
            ],
        }
        with patch("src.vuln_check.requests.post") as mock_post:
            result = check_vulnerabilities([audit])
        mock_post.assert_not_called()
        assert result == {}

    def test_skips_non_dependency_dimensions(self) -> None:
        audit = {
            "metadata": {"name": "repo"},
            "analyzer_results": [
                {
                    "dimension": "testing",
                    "score": 1.0,
                    "details": {"dep_versions": [("requests", "2.0", "pypi")]},
                }
            ],
        }
        with patch("src.vuln_check.requests.post") as mock_post:
            result = check_vulnerabilities([audit])
        mock_post.assert_not_called()
        assert result == {}

    def test_returns_vulns_for_affected_dep(self) -> None:
        audit = _make_audit("my-repo", [("requests", "2.0.0", "pypi")])
        vuln = {
            "id": "GHSA-xxxx-yyyy-zzzz",
            "summary": "Remote code execution in requests",
            "severity": [{"type": "CVSS_V3", "score": "9.8"}],
        }
        mock_resp = _osv_response([[vuln]])
        with patch("src.vuln_check.requests.post", return_value=mock_resp):
            result = check_vulnerabilities([audit])

        assert "my-repo" in result
        assert len(result["my-repo"]) == 1
        entry = result["my-repo"][0]
        assert entry["dep"] == "requests"
        assert entry["vuln_id"] == "GHSA-xxxx-yyyy-zzzz"
        assert entry["severity"] == "9.8"

    def test_empty_vulns_list_not_included(self) -> None:
        audit = _make_audit("clean-repo", [("flask", "2.0.0", "pypi")])
        mock_resp = _osv_response([[]])  # no vulns
        with patch("src.vuln_check.requests.post", return_value=mock_resp):
            result = check_vulnerabilities([audit])
        assert result == {}

    def test_ecosystem_mapping_applied(self) -> None:
        """Ensure npm/pypi/crates are mapped to OSV ecosystem names."""
        audit = _make_audit("repo", [
            ("lodash", "4.17.0", "npm"),
            ("django", "3.0", "pypi"),
            ("serde", "1.0.0", "crates"),
        ])
        captured_body: list[dict] = []

        def fake_post(url, json, timeout):
            captured_body.append(json)
            return _osv_response([[], [], []])

        with patch("src.vuln_check.requests.post", side_effect=fake_post):
            check_vulnerabilities([audit])

        assert captured_body
        queries = captured_body[0]["queries"]
        ecosystems = [q["package"]["ecosystem"] for q in queries]
        assert "npm" in ecosystems
        assert "PyPI" in ecosystems
        assert "crates.io" in ecosystems

    def test_api_error_returns_empty(self, capsys) -> None:
        audit = _make_audit("repo", [("requests", "2.0", "pypi")])
        with patch("src.vuln_check.requests.post", side_effect=Exception("network error")):
            result = check_vulnerabilities([audit])
        assert result == {}
        captured = capsys.readouterr()
        assert "failed" in captured.err.lower() or "OSV" in captured.err

    def test_non_200_response_skipped(self, capsys) -> None:
        audit = _make_audit("repo", [("requests", "2.0", "pypi")])
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("src.vuln_check.requests.post", return_value=mock_resp):
            result = check_vulnerabilities([audit])
        assert result == {}

    def test_uses_cache_on_second_call(self, tmp_path: Path) -> None:
        from src.cache import ResponseCache

        cache = ResponseCache(cache_dir=tmp_path / ".cache", ttl=3600)
        audit = _make_audit("repo", [("requests", "2.0", "pypi")])
        vuln = {"id": "CVE-001", "summary": "bug", "severity": []}
        mock_resp = _osv_response([[vuln]])

        with patch("src.vuln_check.requests.post", return_value=mock_resp) as mock_post:
            result1 = check_vulnerabilities([audit], cache=cache)
        assert mock_post.call_count == 1

        # Second call should use cache — no new HTTP request
        with patch("src.vuln_check.requests.post", return_value=mock_resp) as mock_post2:
            result2 = check_vulnerabilities([audit], cache=cache)
        assert mock_post2.call_count == 0
        assert result2 == result1

    def test_summary_truncated_to_200_chars(self) -> None:
        long_summary = "x" * 500
        audit = _make_audit("repo", [("pkg", "1.0", "pypi")])
        vuln = {"id": "CVE-001", "summary": long_summary, "severity": []}
        mock_resp = _osv_response([[vuln]])
        with patch("src.vuln_check.requests.post", return_value=mock_resp):
            result = check_vulnerabilities([audit])
        assert len(result["repo"][0]["summary"]) <= 200


class TestFormatVulnSummary:
    def test_no_vulns_message(self) -> None:
        msg = format_vuln_summary({})
        assert "No known vulnerabilities" in msg

    def test_single_repo_listed(self) -> None:
        vulns = {
            "my-repo": [
                {"dep": "requests", "vuln_id": "CVE-001", "summary": "RCE bug", "severity": "9.8"}
            ]
        }
        msg = format_vuln_summary(vulns)
        assert "my-repo" in msg
        assert "CVE-001" in msg
        assert "1 vuln" in msg

    def test_sorted_by_vuln_count_descending(self) -> None:
        vulns = {
            "low-risk": [{"dep": "a", "vuln_id": "X", "summary": "", "severity": ""}],
            "high-risk": [
                {"dep": "b", "vuln_id": "Y", "summary": "", "severity": ""},
                {"dep": "c", "vuln_id": "Z", "summary": "", "severity": ""},
            ],
        }
        msg = format_vuln_summary(vulns)
        assert msg.index("high-risk") < msg.index("low-risk")

    def test_shows_total_count(self) -> None:
        vulns = {
            "repo": [
                {"dep": "x", "vuln_id": "A", "summary": "", "severity": ""},
                {"dep": "y", "vuln_id": "B", "summary": "", "severity": ""},
            ]
        }
        msg = format_vuln_summary(vulns)
        assert "2 vulnerabilities" in msg
        assert "1 repos" in msg
