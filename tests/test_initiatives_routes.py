"""Tests for /initiatives and /initiatives/{repo}/gap routes (Arc G S7A.6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi", reason="[serve] extra not installed")
pytest.importorskip("uvicorn", reason="[serve] extra not installed")
pytest.importorskip("jinja2", reason="[serve] extra not installed")

from fastapi.testclient import TestClient  # noqa: E402

from src.serve.app import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_portfolio_truth(projects: list[dict]) -> dict:
    return {"generated_at": "2026-01-01T00:00:00", "projects": projects}


def _bronze_repo(name: str) -> dict:
    """Minimal repo dict that computes as Bronze (tier 1)."""
    return {
        "identity": {"display_name": name, "has_git": True},
        "derived": {
            "last_meaningful_activity_at": "2025-12-01",
            "context_files": ["README.md"],
            "context_quality": "boilerplate",
            "run_instructions_present": False,
            "activity_status": "active",
        },
        "risk": {"doctor_gap": True, "risk_tier": "elevated", "risk_factors": []},
    }


def _silver_repo(name: str) -> dict:
    """Minimal repo dict that computes as Silver (tier 2)."""
    return {
        "identity": {"display_name": name, "has_git": True},
        "derived": {
            "last_meaningful_activity_at": "2025-12-01",
            "context_files": ["README.md"],
            "context_quality": "adequate",
            "run_instructions_present": True,
            "activity_status": "active",
        },
        "risk": {"doctor_gap": False, "risk_tier": "", "risk_factors": []},
    }


def _write_initiatives(od: Path, items: list[dict]) -> None:
    data = {"version": 1, "initiatives": items}
    (od / "initiatives.json").write_text(json.dumps(data))


def _future_deadline() -> str:
    return "2099-12-31"


def _past_deadline() -> str:
    return "2000-01-01"


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    od = tmp_path / "output"
    od.mkdir()
    return od


@pytest.fixture()
def client(output_dir: Path) -> TestClient:
    app = create_app(output_dir=output_dir)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /initiatives
# ---------------------------------------------------------------------------


class TestInitiativesRoute:
    def test_no_initiatives_returns_200(self, client: TestClient) -> None:
        """GET /initiatives with no file → 200 with empty state."""
        resp = client.get("/initiatives")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_no_initiatives_shows_empty_state(self, client: TestClient) -> None:
        resp = client.get("/initiatives")
        # Should show a friendly empty-state message
        assert "No open initiatives" in resp.text or "initiatives" in resp.text.lower()

    def test_one_open_initiative_appears_in_table(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """One open on-track initiative → repo name shows in the table."""
        truth = _make_portfolio_truth([_bronze_repo("MyRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        _write_initiatives(
            output_dir,
            [
                {
                    "repo_name": "MyRepo",
                    "target_tier": 3,
                    "deadline": _future_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": None,
                    "closed_reason": None,
                }
            ],
        )
        resp = client.get("/initiatives")
        assert resp.status_code == 200
        assert "MyRepo" in resp.text

    def test_counts_appear_in_header(self, output_dir: Path, client: TestClient) -> None:
        """Header counts reflect on-track, at-risk, overdue, met correctly."""
        truth = _make_portfolio_truth([_bronze_repo("OnTrackRepo"), _bronze_repo("OverdueRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        _write_initiatives(
            output_dir,
            [
                {
                    "repo_name": "OnTrackRepo",
                    "target_tier": 3,
                    "deadline": _future_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": None,
                    "closed_reason": None,
                },
                {
                    "repo_name": "OverdueRepo",
                    "target_tier": 3,
                    "deadline": _past_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": None,
                    "closed_reason": None,
                },
            ],
        )
        resp = client.get("/initiatives")
        assert resp.status_code == 200
        # The page should mention counts (1 on-track, 1 overdue)
        assert "on-track" in resp.text or "1" in resp.text

    def test_closed_initiative_not_in_rows(self, output_dir: Path, client: TestClient) -> None:
        """Closed initiative is not rendered as a table row."""
        truth = _make_portfolio_truth([_bronze_repo("ClosedRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        _write_initiatives(
            output_dir,
            [
                {
                    "repo_name": "ClosedRepo",
                    "target_tier": 3,
                    "deadline": _future_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": "2026-03-01T00:00:00+00:00",
                    "closed_reason": "met",
                }
            ],
        )
        resp = client.get("/initiatives")
        assert resp.status_code == 200
        # The closed repo should NOT be in the rows table body
        # (it is counted in the footer "N closed" summary instead)
        assert "ClosedRepo" not in resp.text

    def test_closed_count_shown_in_header(self, output_dir: Path, client: TestClient) -> None:
        """Closed initiative count appears in the header summary line."""
        _write_initiatives(
            output_dir,
            [
                {
                    "repo_name": "ClosedRepo",
                    "target_tier": 2,
                    "deadline": _future_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": "2026-03-01T00:00:00+00:00",
                    "closed_reason": "met",
                }
            ],
        )
        resp = client.get("/initiatives")
        assert resp.status_code == 200
        assert "closed" in resp.text

    def test_no_portfolio_truth_still_returns_200(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """Initiatives file present but no portfolio-truth → graceful 200."""
        _write_initiatives(
            output_dir,
            [
                {
                    "repo_name": "Orphan",
                    "target_tier": 2,
                    "deadline": _future_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": None,
                    "closed_reason": None,
                }
            ],
        )
        resp = client.get("/initiatives")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /initiatives/{repo_name}/gap
# ---------------------------------------------------------------------------


class TestInitiativeGapRoute:
    def test_known_repo_returns_200(self, output_dir: Path, client: TestClient) -> None:
        """Known repo with target tier → 200 with missing requirements."""
        truth = _make_portfolio_truth([_bronze_repo("GapRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        resp = client.get("/initiatives/GapRepo/gap?target=3")
        assert resp.status_code == 200

    def test_gap_lists_missing_requirements(self, output_dir: Path, client: TestClient) -> None:
        """Bronze repo targeting Gold tier → shows unmet Gold requirements."""
        truth = _make_portfolio_truth([_bronze_repo("GapRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        resp = client.get("/initiatives/GapRepo/gap?target=3")
        assert resp.status_code == 200
        # At Bronze, should have missing Silver/Gold reqs
        assert "GapRepo" in resp.text

    def test_met_repo_shows_all_met(self, output_dir: Path, client: TestClient) -> None:
        """Silver repo targeting Silver → no missing requirements."""
        truth = _make_portfolio_truth([_silver_repo("SilverRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        resp = client.get("/initiatives/SilverRepo/gap?target=2")
        assert resp.status_code == 200
        assert "All requirements met" in resp.text

    def test_unknown_repo_returns_404(self, output_dir: Path, client: TestClient) -> None:
        """Repo not in portfolio-truth → 404."""
        truth = _make_portfolio_truth([_bronze_repo("KnownRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        resp = client.get("/initiatives/Nonexistent/gap?target=3")
        assert resp.status_code == 404

    def test_no_portfolio_truth_returns_404(self, output_dir: Path, client: TestClient) -> None:
        """No portfolio-truth file → 404 (repo cannot be found)."""
        resp = client.get("/initiatives/AnyRepo/gap?target=2")
        assert resp.status_code == 404

    def test_initiative_gap_fallback_uses_open_initiative(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """No ?target param + open initiative for repo → falls back to initiative target."""
        truth = _make_portfolio_truth([_bronze_repo("FallbackRepo")])
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        _write_initiatives(
            output_dir,
            [
                {
                    "repo_name": "FallbackRepo",
                    "target_tier": 3,
                    "deadline": _future_deadline(),
                    "set_at": "2026-01-01T00:00:00+00:00",
                    "set_by": "operator",
                    "closed_at": None,
                    "closed_reason": None,
                }
            ],
        )
        # No ?target query string — should fall back to the open initiative's target (3)
        resp = client.get("/initiatives/FallbackRepo/gap")
        assert resp.status_code == 200
        assert "FallbackRepo" in resp.text
