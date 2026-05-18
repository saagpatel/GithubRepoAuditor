from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from src.cloner import clone_repo


class TestCloneRepoHardening:
    def test_clone_repo_uses_askpass_without_putting_token_in_git_command(self, monkeypatch, tmp_path):
        recorded: dict[str, object] = {}

        def fake_run(cmd, **kwargs):
            recorded["cmd"] = cmd
            recorded["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)

        dest = clone_repo(
            "https://github.com/user/repo.git",
            "repo",
            token="super-secret-token",
            clone_dir=tmp_path,
        )

        joined_cmd = " ".join(recorded["cmd"])
        env = recorded["env"]

        assert dest == tmp_path / "repo"
        assert "super-secret-token" not in joined_cmd
        assert env is not None
        assert env["GITHUB_AUDITOR_CLONE_TOKEN"] == "super-secret-token"
        assert Path(env["GIT_ASKPASS"]).exists() is False

    def test_clone_repo_logs_failure_without_leaking_token(self, monkeypatch, tmp_path, caplog):
        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=128,
                cmd=cmd,
                stderr="fatal: could not read from https://super-secret-token@github.com/",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        with caplog.at_level(logging.WARNING):
            with pytest.raises(subprocess.CalledProcessError):
                clone_repo(
                    "https://github.com/user/repo.git",
                    "repo",
                    token="super-secret-token",
                    clone_dir=tmp_path,
                )

        assert "super-secret-token" not in caplog.text
