from __future__ import annotations

from datetime import datetime, timezone

import pytest

from github_repo_auditor import operator_control_center_artifacts as artifacts
from github_repo_auditor.weekly_command_center import (
    _persistable_weekly_command_center_digest,
    write_weekly_command_center_artifacts,
)
from github_repo_auditor.scheduled_handoff import build_scheduled_handoff


def _stub_artifact_dependencies(tmp_path, monkeypatch, *, weekly_digest=None):
    json_path = tmp_path / "control.json"
    md_path = tmp_path / "control.md"
    weekly_writes = []
    monkeypatch.setattr(artifacts, "control_center_paths", lambda *_args: (json_path, md_path))
    monkeypatch.setattr(artifacts, "load_latest_portfolio_truth", lambda *_args: (None, {}))
    monkeypatch.setattr(
        artifacts,
        "build_weekly_command_center_digest",
        lambda *_args, **_kwargs: weekly_digest or {},
    )

    def write_weekly(*_args, **_kwargs):
        weekly_writes.append(True)
        return tmp_path / "weekly.json", tmp_path / "weekly.md"

    monkeypatch.setattr(artifacts, "write_weekly_command_center_artifacts", write_weekly)
    return json_path, md_path, weekly_writes


def test_control_center_artifacts_reject_credential_payload_before_writing(tmp_path, monkeypatch):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(artifacts, "control_center_artifact_payload", lambda *_args: {"token": "secret"})

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {}, {}, tmp_path, username="user", generated_at=datetime.now(timezone.utc), report_reference="report"
        )

    assert not json_path.exists()
    assert not md_path.exists()
    assert weekly_writes == []


def test_control_center_artifacts_reject_credential_value_before_any_write(
    tmp_path, monkeypatch
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path, monkeypatch
    )
    token = "ghp_" + ("a" * 36)

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {"summary": token},
            {},
            tmp_path,
            username="user",
            generated_at=datetime.now(timezone.utc),
            report_reference="report",
        )

    assert not json_path.exists()
    assert not md_path.exists()
    assert weekly_writes == []


def test_control_center_artifacts_redact_opaque_sensitive_free_text_before_writing(
    tmp_path, monkeypatch
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path,
        monkeypatch,
        weekly_digest={"status": "current"},
    )
    weekly_digests = []

    def write_weekly(*_args, **kwargs):
        weekly_writes.append(True)
        weekly_digests.append(kwargs["digest"])
        return tmp_path / "weekly.json", tmp_path / "weekly.md"

    monkeypatch.setattr(artifacts, "write_weekly_command_center_artifacts", write_weekly)

    result = artifacts.write_control_center_artifacts(
        {},
        {"operator_summary": {"headline": "opaque-secret-value"}},
        tmp_path,
        username="user",
        generated_at=datetime.now(timezone.utc),
        report_reference="report",
    )

    assert result[0:2] == (json_path, md_path)
    assert "opaque-secret-value" not in json_path.read_text()
    assert "opaque-secret-value" not in md_path.read_text()
    assert "opaque-secret-value" not in str(weekly_digests[0])
    assert "<redacted>" in md_path.read_text()
    assert weekly_writes == [True]


def test_control_center_artifact_sanitizer_preserves_ordinary_security_text():
    value = {"headline": "secret scanning is enabled; token budget is healthy"}

    assert artifacts._redact_sensitive_values(value) == value


def test_control_center_artifact_sanitizer_redacts_compound_sensitive_labels():
    value = {"headline": "secret_scanning_value and api-token-prod"}

    assert artifacts._redact_sensitive_values(value) == {
        "headline": "<redacted> and <redacted>"
    }


def test_control_center_markdown_projection_drops_unlabelled_free_text():
    projection = artifacts._sanitized_snapshot_for_rendering(
        {
            "operator_summary": {"headline": "opaque-value"},
            "operator_setup_health": {"status": "unexpected", "warnings": "secret"},
            "operator_queue": [
                {"lane": "urgent", "title": "opaque-value", "summary": "opaque-value"},
                "not-a-queue-item",
            ],
            "operator_recent_changes": [{"summary": "opaque-value"}],
        }
    )

    assert projection == {
        "operator_summary": {"headline": "<redacted>"},
        "operator_setup_health": {
            "status": "unknown",
            "blocking_errors": 0,
            "warnings": 0,
        },
        "operator_queue": [
            {
                "lane": "urgent",
                "repo": "",
                "title": "<redacted>",
                "summary": "<redacted>",
                "lane_reason": "<redacted>",
                "recommended_action": "<redacted>",
            }
        ],
        "operator_recent_changes": [],
    }


def test_control_center_artifacts_reject_hyphenated_credential_alias(
    tmp_path, monkeypatch
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path, monkeypatch
    )

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {"access-token": "opaque-value"},
            {},
            tmp_path,
            username="user",
            generated_at=datetime.now(timezone.utc),
            report_reference="report",
        )

    assert not json_path.exists()
    assert not md_path.exists()
    assert weekly_writes == []


def test_control_center_artifacts_reject_sensitive_derived_digest_before_writing(
    tmp_path, monkeypatch
):
    token = "github_pat_" + ("a" * 40)
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path,
        monkeypatch,
        weekly_digest={"summary": token},
    )
    monkeypatch.setattr(
        artifacts,
        "control_center_artifact_payload",
        lambda *_args: {},
    )

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {},
            {},
            tmp_path,
            username="user",
            generated_at=datetime.now(timezone.utc),
            report_reference="report",
        )

    assert not json_path.exists()
    assert not md_path.exists()
    assert weekly_writes == []


def test_control_center_artifacts_reject_sensitive_rendered_markdown_before_writing(
    tmp_path, monkeypatch
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path,
        monkeypatch,
        weekly_digest={"status": "current"},
    )
    monkeypatch.setattr(
        artifacts,
        "control_center_artifact_payload",
        lambda *_args: {"status": "current"},
    )
    monkeypatch.setattr(
        artifacts,
        "render_control_center_markdown",
        lambda *_args: "secret_" + ("a" * 40),
    )

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {},
            {},
            tmp_path,
            username="user",
            generated_at=datetime.now(timezone.utc),
            report_reference="report",
        )

    assert not json_path.exists()
    assert not md_path.exists()
    assert weekly_writes == []


@pytest.mark.parametrize(
    "rendered",
    [
        "x-api-key=opaque-value",
        "https://user:opaque-value@example.invalid/report",
        "https://example.invalid/callback#refresh_token=opaque-value",
    ],
)
def test_control_center_artifacts_reject_additional_rendered_credentials(
    tmp_path, monkeypatch, rendered
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path,
        monkeypatch,
        weekly_digest={"status": "current"},
    )
    monkeypatch.setattr(
        artifacts,
        "control_center_artifact_payload",
        lambda *_args: {"status": "current"},
    )
    monkeypatch.setattr(
        artifacts,
        "render_control_center_markdown",
        lambda *_args: rendered,
    )

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {},
            {},
            tmp_path,
            username="user",
            generated_at=datetime.now(timezone.utc),
            report_reference="report",
        )

    assert not json_path.exists()
    assert not md_path.exists()
    assert weekly_writes == []


def test_control_center_artifacts_preserve_normal_artifact_writes(
    tmp_path, monkeypatch
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path,
        monkeypatch,
        weekly_digest={"status": "current"},
    )
    monkeypatch.setattr(
        artifacts,
        "control_center_artifact_payload",
        lambda *_args: {"status": "current"},
    )
    monkeypatch.setattr(
        artifacts,
        "render_control_center_markdown",
        lambda *_args: "# Current\n",
    )

    result = artifacts.write_control_center_artifacts(
        {"status": "current"},
        {},
        tmp_path,
        username="user",
        generated_at=datetime.now(timezone.utc),
        report_reference="report",
    )

    assert result[0:2] == (json_path, md_path)
    assert weekly_writes == [True]
    assert json_path.exists()
    assert md_path.read_text() == "# Current\n"


def test_control_center_json_uses_allowlisted_projection_for_opaque_inputs(
    tmp_path, monkeypatch
):
    json_path, md_path, weekly_writes = _stub_artifact_dependencies(
        tmp_path,
        monkeypatch,
        weekly_digest={
            "headline": "provider-authored opaque secret",
            "source_freshness": {"status": "current"},
        },
    )
    monkeypatch.setattr(
        artifacts,
        "control_center_artifact_payload",
        lambda *_args: {"opaque_benign_key": "provider-authored opaque secret"},
    )

    result = artifacts.write_control_center_artifacts(
        {"opaque_benign_key": "provider-authored opaque secret"},
        {
            "operator_setup_health": {"status": "ready", "warnings": 2},
            "operator_summary": {"headline": "provider-authored opaque secret"},
            "operator_queue": [
                {"lane": "urgent", "title": "provider-authored opaque secret"}
            ],
        },
        tmp_path,
        username="user",
        generated_at=datetime.now(timezone.utc),
        report_reference="report",
    )

    persisted = json_path.read_text()
    assert result[0:2] == (json_path, md_path)
    assert weekly_writes == [True]
    assert "provider-authored opaque secret" not in persisted
    assert '"storage_policy": "allowlisted-summary-only"' in persisted
    assert '"urgent": 1' in persisted


def test_weekly_command_center_disk_projection_drops_opaque_values(tmp_path):
    digest = {
        "username": "opaque-user",
        "headline": "opaque provider prose",
        "source_freshness": {"status": "current", "summary": "opaque"},
        "decision_quality": {"status": "ready", "summary": "opaque"},
        "portfolio_truth": {"project_count": 4},
        "movement": {
            "summary_text": "opaque",
            "transitions": [{"repo": "opaque-repo"}],
        },
        "risk_posture": {"elevated_count": 1, "risk_tier_counts": {"moderate": 1}},
        "security_posture": {"scanned_count": 2},
    }

    json_path, markdown_path = write_weekly_command_center_artifacts(
        tmp_path,
        username="user",
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        digest=digest,
    )

    assert _persistable_weekly_command_center_digest()["contract_version"] == (
        "weekly_command_center_digest_v2"
    )
    assert "opaque" not in json_path.read_text()
    assert "opaque" not in markdown_path.read_text()


def test_persisted_control_center_projection_remains_scheduled_handoff_compatible(
    tmp_path,
):
    artifacts.write_control_center_artifacts(
        {"username": "testuser", "generated_at": "2026-08-22T00:00:00+00:00"},
        {"operator_summary": {}, "operator_queue": []},
        tmp_path,
        username="testuser",
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        report_reference="report",
    )

    handoff = build_scheduled_handoff(tmp_path)

    assert handoff["status"] == "ok"
    assert handoff["username"] == "testuser"
