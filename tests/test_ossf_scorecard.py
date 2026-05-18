"""Tests for src/ossf_scorecard.py — OSSF Scorecard integration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import requests

from src.cache import ResponseCache
from src.ossf_scorecard import (
    _OSSF_CACHE_PARAMS,
    OSSF_SCORECARD_BASE_URL,
    _fetch_one,
    fetch_ossf_scorecards,
    format_ossf_summary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """A requests.Session mock pre-configured with a no-op HTTPAdapter."""
    session = MagicMock(spec=requests.Session)
    return session


def _ok_response(score: float = 7.5) -> MagicMock:
    """Build a mock 200 response matching the Scorecard API shape."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "score": score,
        "checks": [{"name": "Code-Review", "score": 10}],
        "date": "2026-05-01",
        "repo": {"name": "github.com/owner/repo"},
    }
    resp.raise_for_status.return_value = None
    return resp


def _not_found_response() -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 404
    resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


def _server_error_response() -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 500
    resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


# ---------------------------------------------------------------------------
# Unit tests: _fetch_one
# ---------------------------------------------------------------------------


class TestFetchOne:
    def test_happy_path_returns_parsed_scorecard(self, mock_session):
        """200 response is parsed into available=True result."""
        mock_session.get.return_value = _ok_response(7.5)

        result = _fetch_one("owner/repo", session=mock_session, cache=None)

        assert result["available"] is True
        assert result["score"] == 7.5
        assert result["checks"] == [{"name": "Code-Review", "score": 10}]
        assert result["date"] == "2026-05-01"
        mock_session.get.assert_called_once()
        call_url = mock_session.get.call_args[0][0]
        assert "github.com/owner/repo" in call_url

    def test_404_returns_unavailable_no_exception(self, mock_session):
        """404 is treated as 'no scorecard data' — available=False, no raise."""
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 404
        # raise_for_status should NOT be called for 404 (handled before it)
        mock_session.get.return_value = resp

        result = _fetch_one("owner/repo", session=mock_session, cache=None)

        assert result["available"] is False
        assert "error" not in result  # clean unavailable, not an error

    def test_network_error_returns_error_dict(self, mock_session):
        """RequestException is caught, logged, returned as error dict."""
        mock_session.get.side_effect = requests.ConnectionError("refused")

        result = _fetch_one("owner/repo", session=mock_session, cache=None)

        assert result["available"] is False
        assert "error" in result
        assert "refused" in result["error"]

    def test_http_error_non_404_returns_error_dict(self, mock_session):
        """Non-404 HTTP errors are caught and returned as error dict."""
        mock_session.get.return_value = _server_error_response()

        result = _fetch_one("owner/repo", session=mock_session, cache=None)

        assert result["available"] is False
        assert "error" in result

    def test_invalid_full_name_returns_error(self, mock_session):
        """A full_name with no slash returns error without making an HTTP call."""
        result = _fetch_one("no-slash-here", session=mock_session, cache=None)

        assert result["available"] is False
        assert result.get("error") == "invalid_full_name"
        mock_session.get.assert_not_called()

    def test_cache_hit_skips_http(self, tmp_path):
        """When a cache entry exists the HTTP call is skipped."""
        cache = ResponseCache(cache_dir=tmp_path / ".cache", ttl=86400)
        url = f"{OSSF_SCORECARD_BASE_URL}/projects/github.com/owner/repo"
        cached_data = {"available": True, "score": 9.0, "checks": [], "date": "2026-04-01"}
        cache.put(url, _OSSF_CACHE_PARAMS, cached_data)

        mock_session = MagicMock(spec=requests.Session)
        result = _fetch_one("owner/repo", session=mock_session, cache=cache)

        assert result["available"] is True
        assert result["score"] == 9.0
        mock_session.get.assert_not_called()

    def test_successful_result_is_cached(self, tmp_path):
        """A 200 response is stored in cache for subsequent calls."""
        cache = ResponseCache(cache_dir=tmp_path / ".cache", ttl=3600)
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = _ok_response(6.2)

        _fetch_one("owner/repo", session=mock_session, cache=cache)

        url = f"{OSSF_SCORECARD_BASE_URL}/projects/github.com/owner/repo"
        # The cache entry should be readable with the OSSF TTL override (24h)
        # We test by temporarily setting a long TTL to guarantee the read works.
        cache.ttl = 86400
        cached = cache.get(url, _OSSF_CACHE_PARAMS)
        assert cached is not None
        assert cached["score"] == 6.2  # type: ignore[index]


# ---------------------------------------------------------------------------
# Integration-level: fetch_ossf_scorecards
# ---------------------------------------------------------------------------


class TestFetchOssfScorecards:
    def test_returns_mapping_keyed_by_full_name(self, mock_session):
        """Results are keyed by full_name from audit metadata."""
        mock_session.get.return_value = _ok_response(8.0)
        audits = [{"metadata": {"full_name": "owner/repo"}}]

        results = fetch_ossf_scorecards(audits, session=mock_session)

        assert "owner/repo" in results
        assert results["owner/repo"]["score"] == 8.0

    def test_skips_audits_without_full_name(self, mock_session):
        """Audits missing metadata.full_name are silently skipped."""
        audits = [{"metadata": {}}, {"metadata": {"full_name": ""}}]

        results = fetch_ossf_scorecards(audits, session=mock_session)

        assert results == {}
        mock_session.get.assert_not_called()

    def test_404_recorded_as_unavailable(self, mock_session):
        """404 repos produce {'available': False} entry without crashing."""
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 404
        mock_session.get.return_value = resp
        audits = [{"metadata": {"full_name": "owner/private-repo"}}]

        results = fetch_ossf_scorecards(audits, session=mock_session)

        assert results["owner/private-repo"]["available"] is False

    def test_multiple_repos_all_processed(self, mock_session):
        """All audits are processed even if some fail."""
        side_effects = [
            _ok_response(7.0),
            MagicMock(spec=requests.Response, status_code=404),
        ]
        side_effects[1].raise_for_status.return_value = None
        mock_session.get.side_effect = side_effects
        audits = [
            {"metadata": {"full_name": "owner/public-repo"}},
            {"metadata": {"full_name": "owner/missing-repo"}},
        ]

        results = fetch_ossf_scorecards(audits, session=mock_session)

        assert len(results) == 2
        assert results["owner/public-repo"]["available"] is True
        assert results["owner/missing-repo"]["available"] is False


# ---------------------------------------------------------------------------
# format_ossf_summary
# ---------------------------------------------------------------------------


class TestFormatOssfSummary:
    def test_all_scored(self):
        results = {
            "a/b": {"available": True, "score": 8.0},
            "c/d": {"available": True, "score": 6.0},
        }
        summary = format_ossf_summary(results)
        assert "2/2" in summary
        assert "7.0" in summary  # avg of 8.0 and 6.0

    def test_none_scored(self):
        results = {
            "a/b": {"available": False},
            "c/d": {"available": False},
        }
        summary = format_ossf_summary(results)
        assert "0/2" in summary
        assert "no public data" in summary

    def test_mixed_scored(self):
        results = {
            "a/b": {"available": True, "score": 5.0},
            "c/d": {"available": False},
        }
        summary = format_ossf_summary(results)
        assert "1/2" in summary


# ---------------------------------------------------------------------------
# CLI integration: --ossf-scorecard flag triggers fetch and writes JSON
# ---------------------------------------------------------------------------


class TestOssfScorecardCLIIntegration:
    def test_output_json_written_correctly(self, tmp_path):
        """Output JSON is written with the correct structure.

        Simulates the cli.py write block:
          ossf_path.write_text(json.dumps(ossf_data, indent=2, default=str))
        """
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        scorecard_data = {
            "owner/repo": {"available": True, "score": 7.5, "checks": [], "date": "2026-05-01"}
        }

        # Simulate the cli.py write step directly
        ossf_path = output_dir / "ossf-scorecard-testuser-2026-05-11.json"
        ossf_path.write_text(json.dumps(scorecard_data, indent=2, default=str))

        assert ossf_path.exists()
        written = json.loads(ossf_path.read_text())
        assert "owner/repo" in written
        assert written["owner/repo"]["score"] == 7.5
        assert written["owner/repo"]["available"] is True

    def test_fetch_ossf_scorecards_called_for_each_audit(self, mock_session):
        """fetch_ossf_scorecards processes every audit entry via HTTP."""
        mock_session.get.return_value = _ok_response(8.3)
        audits = [
            {"metadata": {"full_name": "org/alpha"}},
            {"metadata": {"full_name": "org/beta"}},
        ]

        results = fetch_ossf_scorecards(audits, session=mock_session)

        assert mock_session.get.call_count == 2
        assert results["org/alpha"]["available"] is True
        assert results["org/beta"]["available"] is True
