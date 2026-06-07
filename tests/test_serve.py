"""Tests for src/serve — FastAPI + HTMX local web UI (Arc F S4.1)."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
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
from src.serve.runner import SAFE_FLAG_NAMES, validate_flags, validate_username  # noqa: E402

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

    def test_known_repo_reads_production_warehouse_schema(self, tmp_path: Path) -> None:
        from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
        from src.warehouse import write_warehouse_snapshot

        od = tmp_path / "output"
        od.mkdir()
        generated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        (od / "portfolio-truth-latest.json").write_text(
            json.dumps(
                {
                    "generated_at": generated_at.isoformat(),
                    "repos": [
                        {
                            "name": "repo-alpha",
                            "risk_score": 85.0,
                            "completeness_score": 30.0,
                            "total_score": 55.0,
                            "language": "Python",
                            "tier": 1,
                        }
                    ],
                }
            )
        )
        audit = RepoAudit(
            metadata=RepoMetadata(
                name="repo-alpha",
                full_name="user/repo-alpha",
                description="Production-schema fixture",
                language="Python",
                languages={"Python": 1},
                private=False,
                fork=False,
                archived=False,
                created_at=generated_at,
                updated_at=generated_at,
                pushed_at=generated_at,
                default_branch="main",
                stars=0,
                forks=0,
                open_issues=0,
                size_kb=1,
                html_url="https://github.com/user/repo-alpha",
                clone_url="https://github.com/user/repo-alpha.git",
            ),
            analyzer_results=[
                AnalyzerResult(
                    dimension="testing",
                    score=0.8,
                    max_score=1.0,
                    findings=["Tests are present"],
                )
            ],
            overall_score=0.55,
            completeness_tier="functional",
        )
        report = AuditReport(
            username="user",
            generated_at=generated_at,
            total_repos=1,
            repos_audited=1,
            tier_distribution={"functional": 1},
            average_score=0.55,
            language_distribution={"Python": 1},
            audits=[audit],
            errors=[],
        )
        write_warehouse_snapshot(report, od)

        resp = TestClient(create_app(output_dir=od)).get("/repos/repo-alpha")

        assert resp.status_code == 200
        assert "55.0" in resp.text
        assert "testing" in resp.text


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

    def test_post_rejects_shell_metacharacters_in_username(self, client: TestClient) -> None:
        resp = client.post(
            "/runs/new",
            data={"username": "octo; touch /tmp/audit-test", "flags": "--portfolio-truth"},
        )
        assert resp.status_code == 422

    def test_post_rejects_username_starting_with_dash(self, client: TestClient) -> None:
        resp = client.post(
            "/runs/new",
            data={"username": "-evil", "flags": "--portfolio-truth"},
        )
        assert resp.status_code == 422


def _seed_draft_readme_records(output_dir: Path) -> tuple[str, str]:
    """Insert two draft-readme approval records into the warehouse DB.

    Returns (record_id_1, record_id_2).
    """
    from src.warehouse import save_approval_record

    id1 = "dr-aabbccdd00000001"
    id2 = "dr-aabbccdd00000002"

    save_approval_record(
        output_dir,
        {
            "approval_id": id1,
            "fingerprint": "fp-001",
            "approval_subject_type": "draft-readme",
            "subject_key": "repo-with-readme",
            "source_run_id": "",
            "approved_at": "2026-01-10T00:00:00",
            "approved_by": "test",
            "approval_note": "+5 lines added, -2 lines removed vs current README.",
            "action_type": "draft-readme",
            "target_context": "repo-with-readme",
            "decision": "",
            "status": "ready-for-review",
            "repo_name": "repo-with-readme",
            "current_readme_sha": "abc123def456",
            "proposed_readme": "# repo-with-readme\n\nThis is the proposed README.",
            "diff_summary": "+5 lines added, -2 lines removed vs current README.",
            "llm_provider": "test",
            "llm_model": "test-model",
            "llm_cost_usd": 0.0,
            "generated_at": "2026-01-10T00:00:00",
            "context_repos": [],
        },
    )
    save_approval_record(
        output_dir,
        {
            "approval_id": id2,
            "fingerprint": "fp-002",
            "approval_subject_type": "draft-readme",
            "subject_key": "repo-no-readme",
            "source_run_id": "",
            "approved_at": "2026-01-11T00:00:00",
            "approved_by": "test",
            "approval_note": "Created new README from scratch.",
            "action_type": "draft-readme",
            "target_context": "repo-no-readme",
            "decision": "",
            "status": "ready-for-review",
            "repo_name": "repo-no-readme",
            "current_readme_sha": None,
            "proposed_readme": "# repo-no-readme\n\nBrand new README.",
            "diff_summary": "Created new README from scratch.",
            "llm_provider": "test",
            "llm_model": "test-model",
            "llm_cost_usd": 0.0,
            "generated_at": "2026-01-11T00:00:00",
            "context_repos": [],
        },
    )
    return id1, id2


class TestDraftReadmeApprovals:
    """Tests for draft-readme packet display and diff partial (Arc G S5.4)."""

    def test_approvals_lists_both_draft_readme_records(self, output_dir: Path) -> None:
        _seed_draft_readme_records(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/approvals")
        assert resp.status_code == 200
        assert "repo-with-readme" in resp.text
        assert "repo-no-readme" in resp.text

    def test_draft_diff_returns_200_with_proposed_readme(self, output_dir: Path) -> None:
        id1, _id2 = _seed_draft_readme_records(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{id1}/draft-diff")
        assert resp.status_code == 200
        assert "This is the proposed README." in resp.text

    def test_draft_diff_non_draft_readme_returns_404(self, output_dir: Path) -> None:
        """A record with a different approval_subject_type should return 404."""
        from src.warehouse import save_approval_record

        save_approval_record(
            output_dir,
            {
                "approval_id": "campaign-zz9999",
                "fingerprint": "fp-campaign",
                "approval_subject_type": "campaign",
                "subject_key": "repo-alpha",
                "source_run_id": "",
                "approved_at": "2026-01-05T00:00:00",
                "approved_by": "test",
                "approval_note": "",
            },
        )
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/approvals/campaign-zz9999/draft-diff")
        assert resp.status_code == 404

    def test_draft_diff_nonexistent_record_returns_404(self, output_dir: Path) -> None:
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/approvals/nonexistent-record-id/draft-diff")
        assert resp.status_code == 404

    def test_draft_diff_partial_has_no_html_or_body_tags(self, output_dir: Path) -> None:
        """The partial must be HTMX-injectable: no <html> or <body> wrapper."""
        id1, _id2 = _seed_draft_readme_records(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{id1}/draft-diff")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "<html" not in body
        assert "<body" not in body

    def test_approvals_shows_view_diff_button_for_draft_readme(self, output_dir: Path) -> None:
        id1, _id2 = _seed_draft_readme_records(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/approvals")
        assert resp.status_code == 200
        assert "View diff" in resp.text
        assert f"/approvals/{id1}/draft-diff" in resp.text


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


class TestValidateUsername:
    def test_valid_username_allowed(self) -> None:
        assert validate_username("octocat") == "octocat"

    def test_valid_org_with_hyphen_allowed(self) -> None:
        assert validate_username("octo-org") == "octo-org"

    def test_surrounding_whitespace_stripped(self) -> None:
        assert validate_username(" octocat ") == "octocat"

    def test_shell_metacharacter_rejected(self) -> None:
        with pytest.raises(ValueError, match="valid GitHub owner"):
            validate_username("octo;touch")

    def test_leading_hyphen_rejected(self) -> None:
        with pytest.raises(ValueError, match="valid GitHub owner"):
            validate_username("-octo")

    def test_trailing_hyphen_rejected(self) -> None:
        with pytest.raises(ValueError, match="valid GitHub owner"):
            validate_username("octo-")

    def test_consecutive_hyphens_rejected(self) -> None:
        with pytest.raises(ValueError, match="consecutive hyphens"):
            validate_username("octo--org")


class TestHtmxFragmentEscaping:
    def test_campaign_action_values_are_escaped(self) -> None:
        from src.serve.routes import _render_action_row

        html = _render_action_row(
            'packet"><script>alert(1)</script>',
            0,
            {
                "repo_name": "<img src=x onerror=alert(1)>",
                "action_type": "<b>write</b>",
                "target": "<script>alert(1)</script>",
                "rationale": "needs <strong>escaping</strong>",
            },
        )

        assert "<script>" not in html
        assert "<img" not in html
        assert "&lt;script&gt;" in html
        assert "&lt;strong&gt;escaping&lt;/strong&gt;" in html

    def test_section_card_values_are_escaped(self) -> None:
        from src.serve.routes import _render_section_card

        html = _render_section_card(
            'section"><script>alert(1)</script>',
            {
                "section_heading": "<h1>bad</h1>",
                "section_body": "<script>alert(1)</script>",
                "rejected_reason": "<img src=x onerror=alert(1)>",
                "state": "rejected",
            },
        )

        assert "<script>" not in html
        assert "<img" not in html
        assert "&lt;h1&gt;bad&lt;/h1&gt;" in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_campaign_action_error_hides_exception_details(self, client: TestClient) -> None:
        with patch(
            "src.plan_campaign.approve_action",
            side_effect=ValueError("internal stack trace /tmp/private.py:99"),
        ):
            resp = client.post("/approvals/packet-1/actions/0/approve")

        assert resp.status_code == 404
        assert "Not found." in resp.text
        assert "internal stack trace" not in resp.text
        assert "/tmp/private.py" not in resp.text

    def test_section_error_hides_exception_details(self, client: TestClient) -> None:
        with patch(
            "src.draft_readmes.approve_section",
            side_effect=ValueError("internal stack trace /tmp/private.py:99"),
        ):
            resp = client.post("/approvals/sections/section-1/approve")

        assert resp.status_code == 404
        assert "Not found." in resp.text
        assert "internal stack trace" not in resp.text
        assert "/tmp/private.py" not in resp.text


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


# ---------------------------------------------------------------------------
# Campaign-plan packet display (Arc G S6.3)
# ---------------------------------------------------------------------------


def _seed_campaign_plan_record(output_dir: Path) -> str:
    """Insert one campaign-plan approval record into the warehouse DB.

    Returns the record_id.
    """
    from src.warehouse import save_approval_record

    record_id = "cp-aabbccdd00000001"
    save_approval_record(
        output_dir,
        {
            "approval_id": record_id,
            "fingerprint": "fp-cp-001",
            "approval_subject_type": "campaign-plan",
            "subject_key": "campaign-plan-fixture",
            "source_run_id": "",
            "approved_at": "2026-05-11T00:00:00",
            "approved_by": "test",
            "approval_note": "2 actions for goal: add CI to all repos",
            "action_type": "campaign-plan",
            "target_context": "add CI to all repos",
            "goal": "add CI to all repos",
            "candidate_count": 10,
            "qualified_count": 2,
            "llm_provider": "test",
            "llm_model": "test-model",
            "llm_cost_usd": 0.0042,
            "generated_at": "2026-05-11T00:00:00",
            "actions": [
                {
                    "repo_name": "my-repo",
                    "action_type": "add_ci",
                    "target": ".github/workflows/ci.yml",
                    "rationale": "No CI pipeline found.",
                    "expected_impact": "Automated tests on PR.",
                },
                {
                    "repo_name": "another-repo",
                    "action_type": "pending_human_action",
                    "target": "",
                    "rationale": "Complex monorepo — needs manual review.",
                    "expected_impact": None,
                },
            ],
        },
    )
    return record_id


class TestCampaignPlanApprovals:
    """Tests for campaign-plan packet display in /approvals (Arc G S6.3)."""

    def test_approvals_lists_campaign_plan_record(self, output_dir: Path) -> None:
        """GET /approvals with a campaign-plan record → 200, record visible."""
        record_id = _seed_campaign_plan_record(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/approvals")
        assert resp.status_code == 200
        assert record_id[:12] in resp.text or "campaign-plan" in resp.text

    def test_campaign_plan_partial_returns_200_with_goal(self, output_dir: Path) -> None:
        """GET /approvals/{id}/campaign-plan → 200, contains goal text and action row."""
        record_id = _seed_campaign_plan_record(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{record_id}/campaign-plan")
        assert resp.status_code == 200
        assert "add CI to all repos" in resp.text
        assert "my-repo" in resp.text

    def test_campaign_plan_non_campaign_plan_returns_404(self, output_dir: Path) -> None:
        """A draft-readme record requested via /campaign-plan → 404."""
        _id1, _id2 = _seed_draft_readme_records(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{_id1}/campaign-plan")
        assert resp.status_code == 404

    def test_campaign_plan_nonexistent_record_returns_404(self, output_dir: Path) -> None:
        """GET /approvals/nonexistent/campaign-plan → 404."""
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/approvals/nonexistent-campaign-id/campaign-plan")
        assert resp.status_code == 404

    def test_campaign_plan_partial_has_no_html_or_body_tags(self, output_dir: Path) -> None:
        """The partial must be HTMX-injectable: no <html> or <body> wrapper."""
        record_id = _seed_campaign_plan_record(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{record_id}/campaign-plan")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "<html" not in body
        assert "<body" not in body

    def test_campaign_plan_pending_rows_have_de_emphasis_class(self, output_dir: Path) -> None:
        """Pending-human-action rows render with the de-emphasis CSS class."""
        record_id = _seed_campaign_plan_record(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{record_id}/campaign-plan")
        assert resp.status_code == 200
        assert "campaign-plan__row--pending" in resp.text

    def test_campaign_plan_partial_shows_llm_cost_4dp(self, output_dir: Path) -> None:
        """Partial includes the LLM cost formatted to 4 decimal places."""
        record_id = _seed_campaign_plan_record(output_dir)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get(f"/approvals/{record_id}/campaign-plan")
        assert resp.status_code == 200
        assert "$0.0042" in resp.text
