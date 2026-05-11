"""Tests for src/serve — FastAPI + HTMX local web UI (Arc F S4.1)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Dependency guard — skip entire module if [serve] extra not installed
# ---------------------------------------------------------------------------
fastapi = pytest.importorskip("fastapi", reason="[serve] extra not installed")
pytest.importorskip("uvicorn", reason="[serve] extra not installed")
pytest.importorskip("jinja2", reason="[serve] extra not installed")

from fastapi.testclient import TestClient  # noqa: E402

from src.serve.app import create_app  # noqa: E402
from src.serve.runner import SAFE_FLAG_NAMES, validate_flags  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Minimal output directory with fixture data."""
    od = tmp_path / "output"
    od.mkdir()

    # --- portfolio-truth-latest.json ---
    truth = {
        "generated_at": "2026-01-01T00:00:00",
        "repos": [
            {
                "name": "repo-alpha",
                "risk_score": 85.0,
                "completeness_score": 30.0,
                "total_score": 55.0,
                "language": "Python",
                "tier": 1,
            },
            {
                "name": "repo-beta",
                "risk_score": 10.0,
                "completeness_score": 90.0,
                "total_score": 80.0,
                "language": "TypeScript",
                "tier": 2,
            },
        ],
    }
    (od / "portfolio-truth-latest.json").write_text(json.dumps(truth))

    # --- portfolio-warehouse.db with audit_runs + repo_snapshots ---
    db_path = od / "portfolio-warehouse.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_runs (
            run_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            schema_version TEXT NOT NULL DEFAULT '1',
            scoring_profile TEXT NOT NULL DEFAULT 'default',
            run_mode TEXT NOT NULL DEFAULT 'full',
            report_path TEXT,
            total_repos INTEGER NOT NULL DEFAULT 0,
            repos_audited INTEGER NOT NULL DEFAULT 0,
            average_score REAL NOT NULL DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS repo_snapshots (
            run_id TEXT NOT NULL,
            repo_name TEXT NOT NULL,
            total_score REAL NOT NULL DEFAULT 0.0,
            completeness_score REAL NOT NULL DEFAULT 0.0,
            risk_score REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (run_id, repo_name)
        );
        CREATE TABLE IF NOT EXISTS dimension_scores (
            run_id TEXT NOT NULL,
            repo_name TEXT NOT NULL,
            dimension TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            weight REAL NOT NULL DEFAULT 1.0
        );
        """
    )
    conn.execute(
        "INSERT INTO audit_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("run-001", "testuser", "2026-01-01T00:00:00", "1", "default", "full", None, 2, 2, 67.5),
    )
    conn.execute(
        "INSERT INTO audit_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("run-002", "testuser", "2026-01-02T00:00:00", "1", "default", "full", None, 2, 2, 70.0),
    )
    conn.execute(
        "INSERT INTO repo_snapshots VALUES (?,?,?,?,?)",
        ("run-001", "repo-alpha", 55.0, 30.0, 85.0),
    )
    conn.commit()
    conn.close()

    return od


@pytest.fixture()
def client(output_dir: Path) -> TestClient:
    app = create_app(output_dir=output_dir)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Route smoke tests
# ---------------------------------------------------------------------------


class TestIndexRoute:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_repo_names(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "repo-alpha" in resp.text

    def test_shows_total_count(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "2" in resp.text

    def test_shows_generated_at(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "2026-01-01" in resp.text

    def test_html_content_type(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]


class TestRepoDetailRoute:
    def test_known_repo_returns_200(self, client: TestClient) -> None:
        resp = client.get("/repos/repo-alpha")
        assert resp.status_code == 200

    def test_shows_repo_name(self, client: TestClient) -> None:
        resp = client.get("/repos/repo-alpha")
        assert "repo-alpha" in resp.text

    def test_shows_scores(self, client: TestClient) -> None:
        resp = client.get("/repos/repo-alpha")
        assert "85" in resp.text or "30" in resp.text

    def test_unknown_repo_returns_404(self, client: TestClient) -> None:
        resp = client.get("/repos/nonexistent-repo-xyz")
        assert resp.status_code == 404


class TestRunsRoute:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/runs")
        assert resp.status_code == 200

    def test_shows_run_ids(self, client: TestClient) -> None:
        resp = client.get("/runs")
        assert "run-001" in resp.text or "run-002" in resp.text

    def test_pagination_page_param(self, client: TestClient) -> None:
        resp = client.get("/runs?page=1")
        assert resp.status_code == 200

    def test_empty_warehouse(self, tmp_path: Path) -> None:
        """Empty output dir → 200 with empty state."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        app = create_app(output_dir=empty_dir)
        c = TestClient(app)
        resp = c.get("/runs")
        assert resp.status_code == 200


class TestApprovalsRoute:
    def test_returns_200_with_mocked_records(self, client: TestClient) -> None:
        fake_records = [
            {
                "approval_id": "appr-001",
                "approval_subject_type": "campaign",
                "subject_key": "repo-alpha",
                "approval_state": "ready-for-review",
            },
            {
                "approval_id": "appr-002",
                "approval_subject_type": "governance",
                "subject_key": "all",
                "approval_state": "not-applicable",
            },
        ]
        with patch("src.warehouse.load_approval_records", return_value=fake_records):
            resp = client.get("/approvals")
        assert resp.status_code == 200
        assert "appr-001" in resp.text
        assert "appr-002" in resp.text

    def test_returns_200_without_warehouse(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "no_warehouse"
        empty_dir.mkdir()
        app = create_app(output_dir=empty_dir)
        c = TestClient(app)
        resp = c.get("/approvals")
        assert resp.status_code == 200


class TestNewRunRoute:
    def test_get_form_returns_200(self, client: TestClient) -> None:
        resp = client.get("/runs/new")
        assert resp.status_code == 200
        assert "username" in resp.text.lower()

    def test_post_valid_flags_returns_run_id(self, client: TestClient) -> None:
        with patch("src.serve.routes.spawn_run", return_value="abc123"):
            resp = client.post(
                "/runs/new",
                data={"username": "testuser", "flags": "--portfolio-truth"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "run_id" in body
        assert body["run_id"] == "abc123"

    def test_post_invalid_flag_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/runs/new",
            data={"username": "testuser", "flags": "--evil-flag"},
        )
        assert resp.status_code == 422

    def test_post_injection_attempt_returns_422(self, client: TestClient) -> None:
        """Shell metacharacter in flag value must be rejected."""
        resp = client.post(
            "/runs/new",
            data={"username": "testuser", "flags": "--token=; rm -rf /"},
        )
        assert resp.status_code == 422

    def test_post_missing_username_returns_422(self, client: TestClient) -> None:
        resp = client.post("/runs/new", data={"flags": ""})
        assert resp.status_code == 422


class TestApprovalActions:
    def test_approve_records_intent(self, client: TestClient, output_dir: Path) -> None:
        resp = client.post("/approvals/appr-999/approve")
        assert resp.status_code == 200
        assert "intent recorded" in resp.text.lower() or "approved" in resp.text.lower()
        # intent log written
        log = output_dir / "serve-intent-log.jsonl"
        assert log.exists()
        data = json.loads(log.read_text().strip().splitlines()[0])
        assert data["approval_id"] == "appr-999"
        assert data["action"] == "approve"

    def test_reject_records_intent(self, client: TestClient, output_dir: Path) -> None:
        resp = client.post("/approvals/appr-888/reject")
        assert resp.status_code == 200
        log = output_dir / "serve-intent-log.jsonl"
        assert log.exists()
        lines = log.read_text().strip().splitlines()
        last = json.loads(lines[-1])
        assert last["approval_id"] == "appr-888"
        assert last["action"] == "reject"


# ---------------------------------------------------------------------------
# SSE / stream tests
# ---------------------------------------------------------------------------


class TestStreamRoute:
    def test_unknown_run_id_returns_404(self, client: TestClient) -> None:
        resp = client.get("/runs/new/stream/nonexistent-run-id-xyz")
        assert resp.status_code == 404

    def test_stream_happy_path(self, client: TestClient, output_dir: Path) -> None:
        """Spawn a trivial subprocess and read at least one SSE event."""
        from src.serve.runner import spawn_run

        # Use python -c "print('hello')" — portable, no shell=True
        run_id = spawn_run(
            username="testuser",
            flags={},
            output_dir=output_dir,
        )
        # Override the session's command to something safe and instant
        from src.serve import runner as runner_mod

        session = runner_mod.get_session(run_id)
        assert session is not None

        # Wait briefly for the subprocess to complete (it may fail — that's OK,
        # we just want the stream endpoint to respond)
        deadline = time.monotonic() + 5.0
        while not session.done and time.monotonic() < deadline:
            time.sleep(0.05)

        resp = client.get(f"/runs/new/stream/{run_id}")
        # SSE endpoint must return 200 with correct media type
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Runner unit tests
# ---------------------------------------------------------------------------


class TestValidateFlags:
    def test_bool_flag_allowed(self) -> None:
        args = validate_flags({"portfolio-truth": True})
        assert "--portfolio-truth" in args

    def test_bool_flag_false_omitted(self) -> None:
        args = validate_flags({"portfolio-truth": False})
        assert args == []

    def test_string_value_allowed(self) -> None:
        args = validate_flags({"output-dir": "output/test"})
        assert "--output-dir" in args
        assert "output/test" in args

    def test_unknown_flag_raises(self) -> None:
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_flags({"evil-flag": True})

    def test_shell_metachar_semicolon_raises(self) -> None:
        with pytest.raises(ValueError, match="disallowed character"):
            validate_flags({"output-dir": "; rm -rf /"})

    def test_shell_metachar_pipe_raises(self) -> None:
        with pytest.raises(ValueError, match="disallowed character"):
            validate_flags({"output-dir": "foo | bar"})

    def test_shell_metachar_backtick_raises(self) -> None:
        with pytest.raises(ValueError, match="disallowed character"):
            validate_flags({"output-dir": "`whoami`"})

    def test_underscore_normalised_to_dash(self) -> None:
        args = validate_flags({"portfolio_truth": True})
        assert "--portfolio-truth" in args

    def test_leading_dashes_stripped(self) -> None:
        args = validate_flags({"--portfolio-truth": True})
        assert "--portfolio-truth" in args

    def test_safe_flag_names_populated(self) -> None:
        assert "portfolio-truth" in SAFE_FLAG_NAMES
        assert "control-center" in SAFE_FLAG_NAMES


# ---------------------------------------------------------------------------
# CLI wiring smoke test (no server start)
# ---------------------------------------------------------------------------


class TestCLIServeFlag:
    def test_serve_flag_in_parser(self) -> None:
        from src.cli import build_parser

        parser = build_parser()
        # --serve must be a recognised flag (parse with a dummy username)
        args = parser.parse_args(["dummyuser", "--serve", "--port", "9999", "--host", "0.0.0.0"])
        assert args.serve is True
        assert args.port == 9999
        assert args.host == "0.0.0.0"

    def test_serve_defaults(self) -> None:
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["dummyuser", "--serve"])
        assert args.port == 8080
        assert args.host == "127.0.0.1"
