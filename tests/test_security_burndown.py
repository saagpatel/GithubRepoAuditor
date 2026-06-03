"""Tests for security_burndown module and ghas_alert_details detail capture."""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from src.cli import _run_security_burndown_mode
from src.ghas_alert_details import fetch_dependabot_details
from src.security_burndown import (
    BurndownEntry,
    BurndownReport,
    build_security_burndown,
    render_burndown_markdown,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audit(repo_name: str, owner: str = "octocat") -> dict:
    return {"metadata": {"name": repo_name, "full_name": f"{owner}/{repo_name}"}}


def _make_dep_alert(
    *,
    package: str = "lodash",
    ecosystem: str = "npm",
    scope: str = "runtime",
    severity: str = "critical",
    ghsa_id: str = "GHSA-0000-0000-0001",
    first_patched: str = "4.17.21",
    manifest_path: str = "package.json",
) -> dict:
    """Build a minimal GitHub Dependabot alert API dict (raw API shape)."""
    return {
        "security_advisory": {
            "ghsa_id": ghsa_id,
            "severity": severity,
        },
        "security_vulnerability": {
            "severity": severity,
            "first_patched_version": {"identifier": first_patched},
        },
        "dependency": {
            "package": {"name": package, "ecosystem": ecosystem},
            "scope": scope,
            "manifest_path": manifest_path,
        },
    }


def _mock_session_dep(alerts: list) -> MagicMock:
    """Return a mock session that serves alerts from the dependabot endpoint."""
    session = MagicMock(spec=requests.Session)

    def _get(url: str, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.links = {}
        resp.headers = {}
        if "dependabot" in url:
            resp.json.return_value = alerts
        else:
            resp.json.return_value = []
        return resp

    session.get.side_effect = _get
    return session


# ---------------------------------------------------------------------------
# Part 1 — fetch_dependabot_details: extraction + defensiveness + error path
# ---------------------------------------------------------------------------


class TestFetchDependabotDetails:
    def test_all_fields_extracted(self) -> None:
        session = _mock_session_dep(
            [
                _make_dep_alert(
                    package="axios",
                    ecosystem="npm",
                    scope="runtime",
                    severity="high",
                    ghsa_id="GHSA-1234-5678-9abc",
                    first_patched="1.6.0",
                    manifest_path="frontend/package.json",
                )
            ]
        )
        result = fetch_dependabot_details([_make_audit("my-repo")], token="tok", session=session)
        assert "my-repo" in result
        details = result["my-repo"]
        assert len(details) == 1
        d = details[0]
        assert d["package"] == "axios"
        assert d["ecosystem"] == "npm"
        assert d["scope"] == "runtime"
        assert d["severity"] == "high"
        assert d["ghsa_id"] == "GHSA-1234-5678-9abc"
        assert d["first_patched_version"] == "1.6.0"
        assert d["manifest_path"] == "frontend/package.json"

    def test_missing_fields_return_none_not_keyerror(self) -> None:
        """Completely bare alert dict — no KeyError, all detail fields are None."""
        session = _mock_session_dep([{}])
        result = fetch_dependabot_details([_make_audit("bare-repo")], token="tok", session=session)
        d = result["bare-repo"][0]
        assert d["package"] is None
        assert d["ecosystem"] is None
        assert d["scope"] is None
        assert d["ghsa_id"] is None
        assert d["first_patched_version"] is None
        assert d["severity"] is None

    def test_no_first_patched_version_gives_none(self) -> None:
        """Alert without first_patched_version → detail.first_patched_version is None."""
        alert = _make_dep_alert()
        del alert["security_vulnerability"]["first_patched_version"]
        session = _mock_session_dep([alert])
        result = fetch_dependabot_details([_make_audit("repo")], token="tok", session=session)
        assert result["repo"][0]["first_patched_version"] is None

    def test_severity_fallback_to_vulnerability_field(self) -> None:
        """When security_advisory.severity absent, falls back to security_vulnerability.severity."""
        alert = {
            "security_advisory": {},
            "security_vulnerability": {"severity": "medium", "first_patched_version": None},
            "dependency": {"package": {"name": "pkg", "ecosystem": "pip"}, "scope": "runtime"},
        }
        session = _mock_session_dep([alert])
        result = fetch_dependabot_details([_make_audit("repo")], token="tok", session=session)
        assert result["repo"][0]["severity"] == "medium"

    def test_http_error_expected_status_returns_empty_list_no_crash(self) -> None:
        """403/404/410 → repo gets empty list, no exception raised."""
        session = MagicMock(spec=requests.Session)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 403
        exc = requests.HTTPError(response=resp)
        session.get.side_effect = exc
        result = fetch_dependabot_details([_make_audit("private")], token="tok", session=session)
        assert result["private"] == []

    def test_http_error_unexpected_status_returns_empty_list_no_crash(self) -> None:
        """500 → repo gets empty list, no exception raised."""
        session = MagicMock(spec=requests.Session)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        exc = requests.HTTPError(response=resp)
        session.get.side_effect = exc
        result = fetch_dependabot_details([_make_audit("flaky")], token="tok", session=session)
        assert result["flaky"] == []

    def test_generic_exception_returns_empty_list_no_crash(self) -> None:
        """Any unexpected exception → repo gets empty list, no exception propagated."""
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = RuntimeError("network exploded")
        result = fetch_dependabot_details([_make_audit("broken")], token="tok", session=session)
        assert result["broken"] == []

    def test_no_token_returns_empty_dict(self) -> None:
        result = fetch_dependabot_details([_make_audit("repo")], token=None)
        assert result == {}

    def test_multiple_repos_partial_failure_continues(self) -> None:
        """A failure on one repo does not prevent other repos from being fetched."""
        call_count = {"n": 0}

        def _get(url: str, params=None, timeout=None):
            call_count["n"] += 1
            if "bad-repo" in url:
                raise RuntimeError("forced failure")
            resp = MagicMock(spec=requests.Response)
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.links = {}
            resp.headers = {}
            resp.json.return_value = [_make_dep_alert(package="pkg")]
            return resp

        session = MagicMock(spec=requests.Session)
        session.get.side_effect = _get
        audits = [_make_audit("good-repo"), _make_audit("bad-repo")]
        result = fetch_dependabot_details(audits, token="tok", session=session)
        assert result["good-repo"][0]["package"] == "pkg"
        assert result["bad-repo"] == []

    def test_error_handlers_log_no_interpolated_values(self) -> None:
        """Verify the module source has no format args in the except-handler log calls."""
        import inspect

        from src import ghas_alert_details

        source = inspect.getsource(ghas_alert_details)
        # Find the except blocks — they should only contain logger calls with
        # a plain string literal and no % or .format() interpolation.
        import re

        # Extract all logger.* call lines that appear after an 'except' keyword
        except_logger_calls = re.findall(
            r"except[^:]+:.*?logger\.[a-z]+\(([^)]+)\)", source, re.DOTALL
        )
        for call_args in except_logger_calls:
            # No %-formatting with a second argument
            assert "%" not in call_args, f"Found %-format in except logger: {call_args!r}"
            # No .format() chaining
            assert ".format(" not in call_args, f"Found .format() in except logger: {call_args!r}"


# ---------------------------------------------------------------------------
# Part 2 — burndown filtering
# ---------------------------------------------------------------------------


def _flat(
    *,
    package: str = "lodash",
    ecosystem: str = "npm",
    scope: str = "runtime",
    severity: str = "critical",
    ghsa_id: str = "GHSA-0000-0000-0001",
    first_patched_version: str = "4.17.21",
    manifest_path: str = "package.json",
) -> dict:
    """Build a flat detail dict as stored in dependabot_details (post-extraction)."""
    return {
        "package": package,
        "ecosystem": ecosystem,
        "scope": scope,
        "severity": severity,
        "ghsa_id": ghsa_id,
        "first_patched_version": first_patched_version,
        "manifest_path": manifest_path,
    }


def _ghas(repo: str, details: list[dict]) -> dict:
    """Build a minimal ghas_data entry for one repo with flat detail dicts."""
    return {
        repo: {
            "dependabot": {"critical": 0, "high": 0, "medium": 0, "low": 0, "available": True},
            "dependabot_details": details,
        }
    }


class TestBurndownFiltering:
    def test_development_scope_excluded(self) -> None:
        data = _ghas(
            "repo",
            [
                _flat(scope="development", severity="critical"),
                _flat(scope="runtime", severity="critical", ghsa_id="GHSA-keep"),
            ],
        )
        report = build_security_burndown(data)
        assert report.distinct_advisories == 1
        assert report.entries[0].ghsa_id == "GHSA-keep"

    def test_null_scope_excluded(self) -> None:
        data = _ghas("repo", [_flat(scope=None, severity="high")])
        report = build_security_burndown(data)
        assert report.distinct_advisories == 0

    def test_no_fix_excluded(self) -> None:
        """Alert with first_patched_version=None must be excluded."""
        data = _ghas(
            "repo", [_flat(scope="runtime", severity="critical", first_patched_version=None)]
        )
        report = build_security_burndown(data)
        assert report.distinct_advisories == 0

    def test_medium_severity_excluded(self) -> None:
        data = _ghas("repo", [_flat(severity="medium", ghsa_id="GHSA-med")])
        report = build_security_burndown(data)
        assert report.distinct_advisories == 0

    def test_low_severity_excluded(self) -> None:
        data = _ghas("repo", [_flat(severity="low", ghsa_id="GHSA-low")])
        report = build_security_burndown(data)
        assert report.distinct_advisories == 0

    def test_all_filters_pass_runtime_critical_fixable(self) -> None:
        data = _ghas(
            "repo",
            [
                {
                    "package": "axios",
                    "ecosystem": "npm",
                    "scope": "runtime",
                    "severity": "critical",
                    "ghsa_id": "GHSA-crit",
                    "first_patched_version": "1.6.0",
                    "manifest_path": "package.json",
                },
            ],
        )
        report = build_security_burndown(data)
        assert report.distinct_advisories == 1

    def test_repo_without_dependabot_details_skipped(self) -> None:
        """Entries missing the key (old counts-only files) are skipped gracefully."""
        data = {
            "repo": {
                "dependabot": {"critical": 5, "high": 0, "medium": 0, "low": 0, "available": True},
            }
        }
        report = build_security_burndown(data)
        assert report.distinct_advisories == 0


# ---------------------------------------------------------------------------
# Part 2 — grouping / deduplication
# ---------------------------------------------------------------------------


class TestBurndownGrouping:
    def test_same_ghsa_across_three_repos_collapses_to_one_entry(self) -> None:
        ghsa = "GHSA-same-1234-abcd"
        detail = {
            "package": "lodash",
            "ecosystem": "npm",
            "scope": "runtime",
            "severity": "high",
            "ghsa_id": ghsa,
            "first_patched_version": "4.17.21",
            "manifest_path": "package.json",
        }
        data = {
            "repo-a": {"dependabot": {}, "dependabot_details": [detail]},
            "repo-b": {"dependabot": {}, "dependabot_details": [detail]},
            "repo-c": {"dependabot": {}, "dependabot_details": [detail]},
        }
        report = build_security_burndown(data)
        assert report.distinct_advisories == 1
        entry = report.entries[0]
        assert entry.affected_repo_count == 3
        assert set(entry.affected_repos) == {"repo-a", "repo-b", "repo-c"}
        assert entry.ghsa_id == ghsa

    def test_affected_repos_sorted(self) -> None:
        detail = {
            "package": "pkg",
            "ecosystem": "pip",
            "scope": "runtime",
            "severity": "high",
            "ghsa_id": "GHSA-sort",
            "first_patched_version": "2.0",
            "manifest_path": "requirements.txt",
        }
        data = {
            "zeta": {"dependabot": {}, "dependabot_details": [detail]},
            "alpha": {"dependabot": {}, "dependabot_details": [detail]},
            "mango": {"dependabot": {}, "dependabot_details": [detail]},
        }
        report = build_security_burndown(data)
        assert list(report.entries[0].affected_repos) == ["alpha", "mango", "zeta"]

    def test_different_ghsa_ids_produce_separate_entries(self) -> None:
        data = {
            "repo": {
                "dependabot": {},
                "dependabot_details": [
                    {
                        "package": "a",
                        "ecosystem": "npm",
                        "scope": "runtime",
                        "severity": "high",
                        "ghsa_id": "GHSA-aaa1",
                        "first_patched_version": "1.0",
                        "manifest_path": "package.json",
                    },
                    {
                        "package": "b",
                        "ecosystem": "npm",
                        "scope": "runtime",
                        "severity": "critical",
                        "ghsa_id": "GHSA-bbb2",
                        "first_patched_version": "2.0",
                        "manifest_path": "package.json",
                    },
                ],
            }
        }
        report = build_security_burndown(data)
        assert report.distinct_advisories == 2

    def test_no_ghsa_groups_by_ecosystem_package_version(self) -> None:
        """When ghsa_id is absent, fallback key is (ecosystem, package, first_patched_version)."""
        detail = {
            "package": "requests",
            "ecosystem": "pip",
            "scope": "runtime",
            "severity": "high",
            "ghsa_id": None,
            "first_patched_version": "2.28.0",
            "manifest_path": "requirements.txt",
        }
        data = {
            "svc-a": {"dependabot": {}, "dependabot_details": [detail]},
            "svc-b": {"dependabot": {}, "dependabot_details": [detail]},
        }
        report = build_security_burndown(data)
        assert report.distinct_advisories == 1
        assert report.entries[0].affected_repo_count == 2

    def test_critical_and_high_same_advisory_reports_critical(self) -> None:
        """If the same advisory appears as both critical and high, report critical."""
        base = {
            "package": "vue",
            "ecosystem": "npm",
            "scope": "runtime",
            "ghsa_id": "GHSA-mixed",
            "first_patched_version": "3.0.0",
            "manifest_path": "package.json",
        }
        data = {
            "repo-x": {"dependabot": {}, "dependabot_details": [{**base, "severity": "critical"}]},
            "repo-y": {"dependabot": {}, "dependabot_details": [{**base, "severity": "high"}]},
        }
        report = build_security_burndown(data)
        assert report.distinct_advisories == 1
        assert report.entries[0].severity == "critical"


# ---------------------------------------------------------------------------
# Part 2 — ranking
# ---------------------------------------------------------------------------


class TestBurndownRanking:
    def _build_data(self, entries: list[dict]) -> dict:
        """Build ghas_data from a flat list of (repo, detail) specs."""
        data: dict = {}
        for spec in entries:
            repo = spec["repo"]
            if repo not in data:
                data[repo] = {"dependabot": {}, "dependabot_details": []}
            data[repo]["dependabot_details"].append(
                {
                    "package": spec["package"],
                    "ecosystem": "npm",
                    "scope": "runtime",
                    "severity": spec["severity"],
                    "ghsa_id": spec["ghsa_id"],
                    "first_patched_version": "1.0",
                    "manifest_path": "package.json",
                }
            )
        return data

    def test_critical_before_high(self) -> None:
        data = self._build_data(
            [
                {"repo": "r1", "package": "a-pkg", "severity": "high", "ghsa_id": "GHSA-high"},
                {"repo": "r2", "package": "b-pkg", "severity": "critical", "ghsa_id": "GHSA-crit"},
            ]
        )
        report = build_security_burndown(data)
        assert report.entries[0].severity == "critical"
        assert report.entries[1].severity == "high"

    def test_higher_repo_count_ranks_first_within_severity(self) -> None:
        """Among same severity, more-repos entry comes first."""
        data = self._build_data(
            [
                {"repo": "r1", "package": "pkg-a", "severity": "high", "ghsa_id": "GHSA-wide"},
                {"repo": "r2", "package": "pkg-a", "severity": "high", "ghsa_id": "GHSA-wide"},
                {"repo": "r3", "package": "pkg-a", "severity": "high", "ghsa_id": "GHSA-wide"},
                {"repo": "r4", "package": "pkg-b", "severity": "high", "ghsa_id": "GHSA-narrow"},
            ]
        )
        report = build_security_burndown(data)
        assert report.entries[0].ghsa_id == "GHSA-wide"
        assert report.entries[0].affected_repo_count == 3
        assert report.entries[1].ghsa_id == "GHSA-narrow"

    def test_package_name_asc_tiebreak(self) -> None:
        """When severity and repo-count tie, sort by package name ascending."""
        data = self._build_data(
            [
                {"repo": "r1", "package": "zebra", "severity": "high", "ghsa_id": "GHSA-z"},
                {"repo": "r2", "package": "alpha", "severity": "high", "ghsa_id": "GHSA-a"},
            ]
        )
        report = build_security_burndown(data)
        assert report.entries[0].package == "alpha"
        assert report.entries[1].package == "zebra"


# ---------------------------------------------------------------------------
# Part 2 — totals
# ---------------------------------------------------------------------------


class TestBurndownTotals:
    def test_totals_correct(self) -> None:
        """distinct_advisories, total_repo_instances, repos_touched all correct."""
        detail_a = {
            "package": "a",
            "ecosystem": "npm",
            "scope": "runtime",
            "severity": "critical",
            "ghsa_id": "GHSA-aaa",
            "first_patched_version": "1.0",
            "manifest_path": "package.json",
        }
        detail_b = {
            "package": "b",
            "ecosystem": "npm",
            "scope": "runtime",
            "severity": "high",
            "ghsa_id": "GHSA-bbb",
            "first_patched_version": "2.0",
            "manifest_path": "package.json",
        }
        data = {
            "repo-1": {"dependabot": {}, "dependabot_details": [detail_a, detail_b]},
            "repo-2": {"dependabot": {}, "dependabot_details": [detail_a]},
        }
        report = build_security_burndown(data)
        # advisory GHSA-aaa spans repo-1 + repo-2 = 2 instances
        # advisory GHSA-bbb spans repo-1 only = 1 instance
        assert report.distinct_advisories == 2
        assert report.total_repo_instances == 3
        assert report.repos_touched == 2


# ---------------------------------------------------------------------------
# Part 3 — render_burndown_markdown
# ---------------------------------------------------------------------------


class TestRenderBurndownMarkdown:
    def test_empty_report_shows_clear_message(self) -> None:
        report = BurndownReport(
            entries=(), distinct_advisories=0, total_repo_instances=0, repos_touched=0
        )
        md = render_burndown_markdown(report)
        assert "# Security Burndown" in md
        assert "clear" in md.lower()
        assert "|" not in md  # no table

    def test_populated_report_has_table(self) -> None:
        entry = BurndownEntry(
            package="lodash",
            ecosystem="npm",
            severity="critical",
            ghsa_id="GHSA-jf85-cpjp-wc8",
            first_patched_version="4.17.21",
            affected_repos=("repo-a", "repo-b"),
            affected_repo_count=2,
        )
        report = BurndownReport(
            entries=(entry,),
            distinct_advisories=1,
            total_repo_instances=2,
            repos_touched=2,
        )
        md = render_burndown_markdown(report)
        assert "# Security Burndown" in md
        assert "GHSA-jf85-cpjp-wc8" in md
        assert "CRITICAL" in md
        assert "4.17.21" in md
        assert "repo-a" in md
        assert "repo-b" in md

    def test_more_than_four_repos_uses_plus_notation(self) -> None:
        entry = BurndownEntry(
            package="pkg",
            ecosystem="npm",
            severity="high",
            ghsa_id="GHSA-wide",
            first_patched_version="2.0",
            affected_repos=("r1", "r2", "r3", "r4", "r5"),
            affected_repo_count=5,
        )
        report = BurndownReport(
            entries=(entry,),
            distinct_advisories=1,
            total_repo_instances=5,
            repos_touched=5,
        )
        md = render_burndown_markdown(report)
        assert "+1 more" in md

    def test_exactly_four_repos_no_truncation(self) -> None:
        entry = BurndownEntry(
            package="pkg",
            ecosystem="npm",
            severity="high",
            ghsa_id="GHSA-four",
            first_patched_version="1.0",
            affected_repos=("r1", "r2", "r3", "r4"),
            affected_repo_count=4,
        )
        report = BurndownReport(
            entries=(entry,),
            distinct_advisories=1,
            total_repo_instances=4,
            repos_touched=4,
        )
        md = render_burndown_markdown(report)
        assert "more" not in md
        assert "r1, r2, r3, r4" in md

    def test_no_ghsa_id_uses_ecosystem_package_label(self) -> None:
        entry = BurndownEntry(
            package="requests",
            ecosystem="pip",
            severity="high",
            ghsa_id=None,
            first_patched_version="2.28.0",
            affected_repos=("svc",),
            affected_repo_count=1,
        )
        report = BurndownReport(
            entries=(entry,),
            distinct_advisories=1,
            total_repo_instances=1,
            repos_touched=1,
        )
        md = render_burndown_markdown(report)
        assert "pip/requests" in md

    def test_summary_line_counts(self) -> None:
        entry = BurndownEntry(
            package="pkg",
            ecosystem="npm",
            severity="critical",
            ghsa_id="GHSA-x",
            first_patched_version="1.0",
            affected_repos=("a",),
            affected_repo_count=1,
        )
        report = BurndownReport(
            entries=(entry,),
            distinct_advisories=1,
            total_repo_instances=1,
            repos_touched=1,
        )
        md = render_burndown_markdown(report)
        assert "1 fixable runtime" in md
        assert "1 repo" in md


# ---------------------------------------------------------------------------
# Integration: build_security_burndown + render round-trip
# ---------------------------------------------------------------------------


class TestBurndownRoundTrip:
    def test_full_round_trip(self) -> None:
        """Build + render on a mixed dataset produces valid markdown."""
        ghas_data = {
            "IncidentWorkbench": {
                "dependabot": {"critical": 2, "high": 1, "medium": 0, "low": 0, "available": True},
                "dependabot_details": [
                    {
                        "package": "axios",
                        "ecosystem": "npm",
                        "scope": "runtime",
                        "severity": "critical",
                        "ghsa_id": "GHSA-crit-axios",
                        "first_patched_version": "1.6.0",
                        "manifest_path": "package.json",
                    },
                    {
                        "package": "axios",
                        "ecosystem": "npm",
                        "scope": "development",
                        "severity": "critical",
                        "ghsa_id": "GHSA-crit-axios",
                        "first_patched_version": "1.6.0",
                        "manifest_path": "package.json",
                    },
                ],
            },
            "IncidentWorkbench-statuspage": {
                "dependabot": {"critical": 1, "high": 0, "medium": 0, "low": 0, "available": True},
                "dependabot_details": [
                    {
                        "package": "axios",
                        "ecosystem": "npm",
                        "scope": "runtime",
                        "severity": "critical",
                        "ghsa_id": "GHSA-crit-axios",
                        "first_patched_version": "1.6.0",
                        "manifest_path": "package.json",
                    },
                ],
            },
            "my-api": {
                "dependabot": {"critical": 0, "high": 1, "medium": 0, "low": 0, "available": True},
                "dependabot_details": [
                    {
                        "package": "requests",
                        "ecosystem": "pip",
                        "scope": "runtime",
                        "severity": "high",
                        "ghsa_id": None,
                        "first_patched_version": "2.28.0",
                        "manifest_path": "requirements.txt",
                    },
                    {
                        "package": "requests",
                        "ecosystem": "pip",
                        "scope": "runtime",
                        "severity": "medium",
                        "ghsa_id": "GHSA-med-skip",
                        "first_patched_version": "2.28.0",
                        "manifest_path": "requirements.txt",
                    },
                ],
            },
        }
        report = build_security_burndown(ghas_data)

        # axios/GHSA-crit-axios spans IncidentWorkbench (runtime only) + statuspage = 2 repos
        # dev-scope alert is excluded
        assert report.distinct_advisories == 2
        assert report.repos_touched == 3  # all 3 repos touched by at least one entry

        # First entry: critical (axios), 2 repos
        assert report.entries[0].severity == "critical"
        assert report.entries[0].affected_repo_count == 2

        # Second entry: high (requests), 1 repo
        assert report.entries[1].severity == "high"

        md = render_burndown_markdown(report)
        assert "# Security Burndown" in md
        assert "GHSA-crit-axios" in md
        assert "CRITICAL" in md
        assert "HIGH" in md
        # medium was filtered out — pip/requests still appears but as the no-ghsa entry
        assert "pip/requests" in md


class TestRunSecurityBurndownMode:
    """CLI dispatch (_run_security_burndown_mode) — markdown + JSON sidecar."""

    def _write_ghas(self, output_dir, username: str) -> None:
        today = datetime.date.today().isoformat()
        ghas = {
            "RepoA": {
                "dependabot_details": [
                    {
                        "package": "lodash",
                        "ecosystem": "npm",
                        "scope": "runtime",
                        "severity": "critical",
                        "ghsa_id": "GHSA-aaaa-0001",
                        "first_patched_version": "4.17.21",
                    }
                ]
            },
            "RepoB": {
                "dependabot_details": [
                    {
                        "package": "lodash",
                        "ecosystem": "npm",
                        "scope": "runtime",
                        "severity": "critical",
                        "ghsa_id": "GHSA-aaaa-0001",
                        "first_patched_version": "4.17.21",
                    }
                ]
            },
        }
        (output_dir / f"ghas-alerts-{username}-{today}.json").write_text(
            json.dumps(ghas), encoding="utf-8"
        )

    def test_writes_markdown_and_json_sidecar(self, tmp_path, capsys) -> None:
        self._write_ghas(tmp_path, "octocat")
        args = SimpleNamespace(output_dir=str(tmp_path), username="octocat")

        _run_security_burndown_mode(args)

        today = datetime.date.today().isoformat()
        md_path = tmp_path / f"security-burndown-octocat-{today}.md"
        json_path = tmp_path / f"security-burndown-octocat-{today}.json"
        assert md_path.exists(), "markdown artifact should be written"
        assert json_path.exists(), "JSON sidecar should be written"

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        # one advisory (GHSA-aaaa-0001) spanning two repos
        assert payload["distinct_advisories"] == 1
        assert payload["repos_touched"] == 2
        assert payload["total_repo_instances"] == 2
        entry = payload["entries"][0]
        assert entry["package"] == "lodash"
        assert entry["severity"] == "critical"
        assert entry["affected_repo_count"] == 2
        assert sorted(entry["affected_repos"]) == ["RepoA", "RepoB"]

    def test_no_ghas_file_exits_nonzero(self, tmp_path) -> None:
        args = SimpleNamespace(output_dir=str(tmp_path), username="nobody")
        with pytest.raises(SystemExit) as exc:
            _run_security_burndown_mode(args)
        assert exc.value.code == 1

    def test_counts_only_ghas_exits_without_writing(self, tmp_path) -> None:
        """A counts-only ghas file (no dependabot_details) exits 0, writes nothing."""
        today = datetime.date.today().isoformat()
        ghas = {"RepoA": {"dependabot": {"critical": 1, "available": True}}}
        (tmp_path / f"ghas-alerts-octocat-{today}.json").write_text(
            json.dumps(ghas), encoding="utf-8"
        )
        args = SimpleNamespace(output_dir=str(tmp_path), username="octocat")
        with pytest.raises(SystemExit) as exc:
            _run_security_burndown_mode(args)
        assert exc.value.code == 0
        assert not list(tmp_path.glob("security-burndown-*"))
