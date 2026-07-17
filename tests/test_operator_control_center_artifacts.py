from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src import operator_control_center_artifacts as artifacts


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
