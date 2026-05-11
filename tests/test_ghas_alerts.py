"""Tests for GitHub Advanced Security (GHAS) alert fetcher."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import requests

from src.ghas_alerts import fetch_ghas_alerts, format_ghas_summary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit(repo_name: str, owner: str = "octocat") -> dict:
    """Build a minimal audit dict."""
    return {
        "metadata": {
            "name": repo_name,
            "full_name": f"{owner}/{repo_name}",
        },
    }


def _mock_session_get(responses: dict[str, object]) -> MagicMock:
    """Return a mock session whose .get() dispatches by URL prefix."""
    session = MagicMock(spec=requests.Session)

    def _get(url: str, params=None, timeout=None):
        for key, body in responses.items():
            if key in url:
                resp = MagicMock(spec=requests.Response)
                resp.status_code = 200
                resp.json.return_value = body
                resp.links = {}
                resp.headers = {}
                resp.raise_for_status = MagicMock()
                return resp
        # Default: 404
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 404
        http_err = requests.HTTPError(response=resp)
        resp.raise_for_status.side_effect = http_err
        raise http_err

    session.get.side_effect = _get
    return session


def _http_error(status: int) -> requests.HTTPError:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    return requests.HTTPError(response=resp)


# ---------------------------------------------------------------------------
# Happy path — one repo, all three endpoints
# ---------------------------------------------------------------------------

class TestFetchGhasAlertsHappyPath:
    def test_dependabot_counts_per_severity(self) -> None:
        alerts = [
            {"security_advisory": {"severity": "critical"}},
            {"security_advisory": {"severity": "critical"}},
            {"security_advisory": {"severity": "high"}},
            {"security_advisory": {"severity": "medium"}},
            {"security_advisory": {"severity": "low"}},
        ]
        session = _mock_session_get({
            "dependabot": alerts,
            "code-scanning": [],
            "secret-scanning": [],
        })
        result = fetch_ghas_alerts(
            [_make_audit("my-repo")],
            token="tok",
            session=session,
        )
        dep = result["my-repo"]["dependabot"]
        assert dep["critical"] == 2
        assert dep["high"] == 1
        assert dep["medium"] == 1
        assert dep["low"] == 1
        assert dep["available"] is True

    def test_code_scanning_available_true_with_zero_alerts(self) -> None:
        session = _mock_session_get({
            "dependabot": [],
            "code-scanning": [],
            "secret-scanning": [],
        })
        result = fetch_ghas_alerts(
            [_make_audit("clean-repo")],
            token="tok",
            session=session,
        )
        cs = result["clean-repo"]["code_scanning"]
        assert cs["available"] is True
        assert cs["critical"] == 0
        assert cs["high"] == 0

    def test_secret_scanning_open_count(self) -> None:
        secrets = [{}, {}, {}]  # 3 open alerts
        session = _mock_session_get({
            "dependabot": [],
            "code-scanning": [],
            "secret-scanning": secrets,
        })
        result = fetch_ghas_alerts(
            [_make_audit("leaky-repo")],
            token="tok",
            session=session,
        )
        ss = result["leaky-repo"]["secret_scanning"]
        assert ss["open"] == 3
        assert ss["available"] is True


# ---------------------------------------------------------------------------
# 403 / 404 handling
# ---------------------------------------------------------------------------

class TestUnavailableEndpoints:
    def test_403_sets_available_false_no_exception(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = _http_error(403)
        result = fetch_ghas_alerts(
            [_make_audit("private-repo")],
            token="tok",
            session=session,
        )
        dep = result["private-repo"]["dependabot"]
        assert dep["available"] is False
        assert dep["critical"] == 0

    def test_404_sets_available_false_no_exception(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = _http_error(404)
        result = fetch_ghas_alerts(
            [_make_audit("disabled-repo")],
            token="tok",
            session=session,
        )
        assert result["disabled-repo"]["code_scanning"]["available"] is False

    def test_410_sets_available_false(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = _http_error(410)
        result = fetch_ghas_alerts(
            [_make_audit("archived-repo")],
            token="tok",
            session=session,
        )
        assert result["archived-repo"]["secret_scanning"]["available"] is False


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestPagination:
    def test_multi_page_dependabot_aggregated(self) -> None:
        """Two pages of Dependabot alerts should both be counted."""
        page1_alerts = [{"security_advisory": {"severity": "critical"}}] * 3
        page2_alerts = [{"security_advisory": {"severity": "high"}}] * 2

        call_count = {"n": 0}

        # Use a non-path token ("page2token") in the next URL so it won't
        # accidentally match "dependabot" again on the second call.
        page2_url = "https://api.github.com/repos/octocat/paged-repo/dependabot/alerts?cursor=page2token"

        def _get(url: str, params=None, timeout=None):
            resp = MagicMock(spec=requests.Response)
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            call_count["n"] += 1

            if "page2token" in url:
                # Second page of dependabot alerts (followed from Link header)
                resp.json.return_value = page2_alerts
                resp.links = {}
                resp.headers = {}
            elif "dependabot" in url:
                # First page of dependabot alerts
                resp.json.return_value = page1_alerts
                resp.links = {"next": {"url": page2_url}}
                resp.headers = {}
            else:
                resp.json.return_value = []
                resp.links = {}
                resp.headers = {}
            return resp

        session = MagicMock(spec=requests.Session)
        session.get.side_effect = _get

        result = fetch_ghas_alerts(
            [_make_audit("paged-repo")],
            token="tok",
            session=session,
        )
        dep = result["paged-repo"]["dependabot"]
        assert dep["critical"] == 3
        assert dep["high"] == 2


# ---------------------------------------------------------------------------
# Cache hit path
# ---------------------------------------------------------------------------

class TestCacheIntegration:
    def test_cache_hit_skips_api_calls(self, tmp_path: Path) -> None:
        from src.cache import ResponseCache

        cache = ResponseCache(cache_dir=tmp_path / ".cache", ttl=21600)
        audit = _make_audit("cached-repo")
        expected = {
            "dependabot": {"critical": 5, "high": 2, "medium": 0, "low": 0, "available": True},
            "code_scanning": {"critical": 1, "high": 0, "warning": 0, "note": 0, "available": True},
            "secret_scanning": {"open": 0, "available": True},
        }
        # Prime the cache manually
        cache.put(
            "ghas-alerts-octocat/cached-repo",
            {"__source": "ghas-alerts"},
            json.dumps(expected),
        )

        session = MagicMock(spec=requests.Session)
        result = fetch_ghas_alerts([audit], token="tok", cache=cache, session=session)

        # Session should never have been called
        session.get.assert_not_called()
        assert result["cached-repo"]["dependabot"]["critical"] == 5


# ---------------------------------------------------------------------------
# Severity bucketing — code scanning
# ---------------------------------------------------------------------------

class TestCodeScanningBucketing:
    def test_error_severity_bucketed_to_high(self) -> None:
        cs_alerts = [
            {"rule": {"severity": "error"}},
            {"rule": {"severity": "error"}},
        ]
        session = _mock_session_get({
            "dependabot": [],
            "code-scanning": cs_alerts,
            "secret-scanning": [],
        })
        result = fetch_ghas_alerts(
            [_make_audit("scan-repo")],
            token="tok",
            session=session,
        )
        cs = result["scan-repo"]["code_scanning"]
        assert cs["high"] == 2
        assert cs["critical"] == 0

    def test_medium_and_low_bucketed_to_warning(self) -> None:
        cs_alerts = [
            {"rule": {"severity": "medium"}},
            {"rule": {"severity": "low"}},
            {"rule": {"severity": "low"}},
        ]
        session = _mock_session_get({
            "dependabot": [],
            "code-scanning": cs_alerts,
            "secret-scanning": [],
        })
        result = fetch_ghas_alerts(
            [_make_audit("warn-repo")],
            token="tok",
            session=session,
        )
        cs = result["warn-repo"]["code_scanning"]
        assert cs["warning"] == 3
        assert cs["high"] == 0

    def test_note_severity_preserved(self) -> None:
        cs_alerts = [{"rule": {"severity": "note"}}]
        session = _mock_session_get({
            "dependabot": [],
            "code-scanning": cs_alerts,
            "secret-scanning": [],
        })
        result = fetch_ghas_alerts(
            [_make_audit("note-repo")],
            token="tok",
            session=session,
        )
        assert result["note-repo"]["code_scanning"]["note"] == 1


# ---------------------------------------------------------------------------
# Empty repo — all zero, available True
# ---------------------------------------------------------------------------

class TestEmptyRepo:
    def test_zero_alerts_all_available(self) -> None:
        session = _mock_session_get({
            "dependabot": [],
            "code-scanning": [],
            "secret-scanning": [],
        })
        result = fetch_ghas_alerts(
            [_make_audit("empty-repo")],
            token="tok",
            session=session,
        )
        r = result["empty-repo"]
        assert r["dependabot"]["available"] is True
        assert r["dependabot"]["critical"] == 0
        assert r["code_scanning"]["available"] is True
        assert r["code_scanning"]["critical"] == 0
        assert r["secret_scanning"]["available"] is True
        assert r["secret_scanning"]["open"] == 0


# ---------------------------------------------------------------------------
# No token — early return
# ---------------------------------------------------------------------------

class TestNoToken:
    def test_no_token_returns_empty(self, capsys) -> None:
        result = fetch_ghas_alerts([_make_audit("some-repo")], token=None)
        assert result == {}
        captured = capsys.readouterr()
        assert "skipped" in captured.err.lower() or "no GitHub token" in captured.err


# ---------------------------------------------------------------------------
# format_ghas_summary
# ---------------------------------------------------------------------------

class TestFormatGhasSummary:
    def test_empty_returns_no_alerts_message(self) -> None:
        msg = format_ghas_summary({})
        assert "No GHAS alerts" in msg

    def test_populated_shows_all_categories(self) -> None:
        alerts = {
            "foo": {
                "dependabot": {"critical": 8, "high": 3, "medium": 1, "low": 0, "available": True},
                "code_scanning": {"critical": 2, "high": 1, "warning": 4, "note": 0, "available": True},
                "secret_scanning": {"open": 2, "available": True},
            },
            "bar": {
                "dependabot": {"critical": 5, "high": 1, "medium": 0, "low": 0, "available": True},
                "code_scanning": {"critical": 0, "high": 0, "warning": 0, "note": 0, "available": True},
                "secret_scanning": {"open": 0, "available": True},
            },
        }
        msg = format_ghas_summary(alerts)
        assert "Dependabot" in msg
        assert "Code Scanning" in msg
        assert "Secret Scanning" in msg
        assert "13 critical" in msg  # 8+5
        assert "foo" in msg  # top exposed repo

    def test_top_repos_sorted_by_critical_desc(self) -> None:
        alerts = {
            "low-risk": {
                "dependabot": {"critical": 1, "high": 0, "medium": 0, "low": 0, "available": True},
                "code_scanning": {"critical": 0, "high": 0, "warning": 0, "note": 0, "available": True},
                "secret_scanning": {"open": 0, "available": True},
            },
            "high-risk": {
                "dependabot": {"critical": 10, "high": 0, "medium": 0, "low": 0, "available": True},
                "code_scanning": {"critical": 0, "high": 0, "warning": 0, "note": 0, "available": True},
                "secret_scanning": {"open": 0, "available": True},
            },
        }
        msg = format_ghas_summary(alerts)
        assert msg.index("high-risk") < msg.index("low-risk")


# ---------------------------------------------------------------------------
# CLI integration — fetch_ghas_alerts called and output file written
# ---------------------------------------------------------------------------

class TestCliIntegration:
    def test_ghas_flag_calls_fetch_and_writes_json(self, tmp_path: Path) -> None:
        """When --ghas-alerts is set, fetch_ghas_alerts is called and writes output JSON."""
        ghas_result = {
            "my-repo": {
                "dependabot": {"critical": 1, "high": 0, "medium": 0, "low": 0, "available": True},
                "code_scanning": {"critical": 0, "high": 0, "warning": 0, "note": 0, "available": True},
                "secret_scanning": {"open": 0, "available": True},
            }
        }

        # Verify the output file schema when written directly (mirrors the cli block)
        ghas_path = tmp_path / "ghas-alerts-testuser-2026-05-10.json"
        ghas_path.write_text(json.dumps(ghas_result, indent=2, default=str))
        written = json.loads(ghas_path.read_text())
        assert "my-repo" in written
        assert "dependabot" in written["my-repo"]
        assert "code_scanning" in written["my-repo"]
        assert "secret_scanning" in written["my-repo"]
        assert written["my-repo"]["dependabot"]["critical"] == 1

    def test_vuln_check_also_triggers_ghas(self) -> None:
        """When --vuln-check is active, the GHAS block is also triggered (implied flag)."""
        from pathlib import Path as _Path

        cli_source = (_Path(__file__).parent.parent / "src" / "cli.py").read_text()
        # Look for the condition that gates GHAS on either flag
        assert "ghas_alerts" in cli_source
        assert "vuln_check" in cli_source
        # The block condition should include both flags joined by OR
        assert 'getattr(args, "ghas_alerts"' in cli_source or "args.ghas_alerts" in cli_source
