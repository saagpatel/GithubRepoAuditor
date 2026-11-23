from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from github_repo_auditor import portfolio_repository_state, portfolio_truth_sources
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from github_repo_auditor.portfolio_truth_types import PortfolioTruthProject


def _make_repository(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "README.md").write_text("# Synthetic repository\n")
    subprocess.run(["git", "init", "-q", str(path)], check=True)


@pytest.mark.parametrize(
    "probe_error",
    [
        PermissionError("final repository-kind probe denied"),
        subprocess.CalledProcessError(
            128, ["git"], stderr="fatal: permission denied /private/path"
        ),
    ],
)
def test_final_repository_kind_probe_error_preserves_git_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe_error: Exception
) -> None:
    workspace = tmp_path / "workspace"
    repository = workspace / "Repo"
    _make_repository(repository)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "remote",
            "add",
            "origin",
            "https://github.com/fixture/Repo.git",
        ],
        check=True,
    )
    original_git = portfolio_repository_state._git

    def deny_final_kind_probe(path: Path, *args: str) -> str:
        if args == ("rev-parse", "--is-bare-repository"):
            raise probe_error
        return original_git(path, *args)

    monkeypatch.setattr(portfolio_repository_state, "_git", deny_final_kind_probe)
    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "missing.yaml",
        include_notion=False,
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )

    project = result.snapshot.projects[0]
    assert project.identity.has_git is True
    assert project.identity.repo_full_name == "fixture/Repo"
    assert project.repository_state["state"] == "unknown"
    assert "private/path" not in project.repository_state["reason"]


def test_catalogued_local_lifecycle_stays_unknown_when_git_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    repository = workspace / "Repo"
    _make_repository(repository)
    original_git_read = portfolio_truth_sources._git_read

    def deny_marker_probe(path: Path, *args: str) -> str:
        if args[:2] == ("rev-parse", "--resolve-git-dir"):
            raise PermissionError("initial repository probe denied")
        return original_git_read(path, *args)

    monkeypatch.setattr(portfolio_truth_sources, "_git_read", deny_marker_probe)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("repos:\n  Repo:\n    lifecycle_state: active\n")
    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog,
        include_notion=False,
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )

    project = result.snapshot.projects[0]
    assert project.identity.has_git is True
    assert project.repository_state["state"] == "unknown"
    assert project.derived.archived is None
    assert "github.archived" not in project.provenance


@pytest.mark.parametrize("failure", ["permission", "timeout", "nonzero"])
def test_catalogued_lifecycle_stays_unknown_when_remote_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    workspace = tmp_path / "workspace"
    repository = workspace / "Repo"
    _make_repository(repository)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("repos:\n  Repo:\n    lifecycle_state: active\n")

    def row() -> PortfolioTruthProject:
        (project,) = build_portfolio_truth_snapshot(
            workspace_root=workspace,
            catalog_path=catalog,
            include_notion=False,
            now=datetime(2026, 11, 23, tzinfo=timezone.utc),
        ).snapshot.projects
        return project

    assert row().derived.archived is False
    original_run = subprocess.run

    def fail_remote_read(command, *args, **kwargs):
        if command[-2:] == ["remote", "-v"]:
            if failure == "permission":
                raise PermissionError("remote read denied")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, timeout=5)
            return subprocess.CompletedProcess(command, 128, "", "remote read failed")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(portfolio_truth_sources.subprocess, "run", fail_remote_read)
    project = row()
    assert project.derived.archived is None
    assert "github.archived" not in project.provenance
