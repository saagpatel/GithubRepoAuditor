from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src import operator_control_center_artifacts as artifacts


def test_control_center_artifacts_reject_credential_payload_before_writing(tmp_path, monkeypatch):
    json_path = tmp_path / "control.json"
    md_path = tmp_path / "control.md"
    monkeypatch.setattr(artifacts, "control_center_paths", lambda *_args: (json_path, md_path))
    monkeypatch.setattr(artifacts, "load_latest_portfolio_truth", lambda *_args: (None, {}))
    monkeypatch.setattr(artifacts, "build_weekly_command_center_digest", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        artifacts,
        "write_weekly_command_center_artifacts",
        lambda *_args, **_kwargs: (tmp_path / "weekly.json", tmp_path / "weekly.md"),
    )
    monkeypatch.setattr(artifacts, "control_center_artifact_payload", lambda *_args: {"token": "secret"})

    with pytest.raises(ValueError, match="must not persist credential fields"):
        artifacts.write_control_center_artifacts(
            {}, {}, tmp_path, username="user", generated_at=datetime.now(timezone.utc), report_reference="report"
        )

    assert not json_path.exists()
    assert not md_path.exists()
