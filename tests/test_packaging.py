from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from github_repo_auditor.config import inspect_config

ROOT = Path(__file__).resolve().parents[1]

_FAMILY_VERDICT_BLOCK = re.compile(rb"(?ms)^families:[ \t]*\r?\n.*?(?=^\S|\Z)")
_FAMILY_VERDICT_KEY = re.compile(rb"(?m)^[ \t]+(?:fate|rationale):")


def _private_reckoning_signatures(contents: bytes) -> list[str]:
    signatures: list[str] = []
    if b"reckoning-verdicts/1" in contents:
        signatures.append("reckoning-verdicts/1")
    if any(
        _FAMILY_VERDICT_KEY.search(block.group())
        for block in _FAMILY_VERDICT_BLOCK.finditer(contents)
    ):
        signatures.append("families verdict fields")
    return signatures


def test_built_distributions_exclude_private_reckoning_data(tmp_path):
    private = tmp_path / "reckoning-verdicts.yaml"
    private.write_text("schema: reckoning-verdicts/1\nfamilies: {}\n")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(tmp_path / "dist")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GHRA_RECKONING_OVERLAY": str(private),
            "TMPDIR": str(tmp_path),
            "PIP_CACHE_DIR": str(tmp_path / "pip-cache"),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (wheel,) = (tmp_path / "dist").glob("*.whl")
    (sdist,) = (tmp_path / "dist").glob("*.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        wheel_files = [
            (item.filename, archive.read(item))
            for item in archive.infolist()
            if not item.is_dir()
        ]
    with tarfile.open(sdist) as archive:
        sdist_files = [
            (member.name, extracted.read())
            for member in archive.getmembers()
            if member.isfile()
            and (extracted := archive.extractfile(member)) is not None
        ]

    for files in (wheel_files, sdist_files):
        names = [name for name, _ in files]
        assert any(
            name.endswith("github_repo_auditor/reckoning_overlay.py") for name in names
        )
        assert not any(
            ("reckoning" in name.lower() or "verdicts" in name.lower())
            and Path(name).name
            not in {
                "reckoning_overlay.py",
                "test_reckoning_overlay.py",
                "test_cli_reckoning.py",
            }
            for name in names
        )
        for name, contents in files:
            if not name.endswith(".py"):
                assert _private_reckoning_signatures(contents) == [], name


@pytest.mark.parametrize(
    "contents, expected",
    [
        (b"schema: reckoning-verdicts/1\n", ["reckoning-verdicts/1"]),
        (
            b"Documentation mentions reckoning-verdicts/1 inline.\n",
            ["reckoning-verdicts/1"],
        ),
        (
            b"families:\n  Example:\n    fate: archive\n",
            ["families verdict fields"],
        ),
        (
            b"families:\n  Example:\n    rationale: unsupported\n",
            ["families verdict fields"],
        ),
        (b"families:\n  Example:\n    fate: keep", ["families verdict fields"]),
        (b"families:\n  Example:\n    owner: team\nother: value\n", []),
    ],
)
def test_private_reckoning_signature_scanner(contents: bytes, expected: list[str]):
    assert _private_reckoning_signatures(contents) == expected


def _project_dependency_names() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    return {item.split(">=", 1)[0].split("[", 1)[0] for item in deps}


def _requirements_names() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    cleaned = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return {item.split(">=", 1)[0].split("[", 1)[0] for item in cleaned}


def test_pyproject_exposes_audit_console_script():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["audit"] == "github_repo_auditor.cli:main"


def test_import_package_uses_conventional_src_layout():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert data["tool"]["setuptools"]["packages"]["find"] == {
        "where": ["src"],
        "include": ["github_repo_auditor*"],
    }
    assert not (ROOT / "src" / "__init__.py").exists()
    assert (ROOT / "src" / "github_repo_auditor" / "__init__.py").is_file()
    assert data["tool"]["setuptools"]["package-data"]["github_repo_auditor"]
    assert (
        "assets/excel/*.xlsx"
        in data["tool"]["setuptools"]["package-data"]["github_repo_auditor"]
    )


def test_cli_module_executes_help():
    result = subprocess.run(
        [sys.executable, "-m", "github_repo_auditor.cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "usage: github-repo-auditor" in result.stdout
    assert "--control-center" in result.stdout


def test_requirements_cover_runtime_and_config_dependencies():
    requirement_names = _requirements_names()
    assert _project_dependency_names().issubset(requirement_names)
    assert "pyyaml" in requirement_names


def test_makefile_includes_operator_entrypoints():
    makefile = (ROOT / "Makefile").read_text()
    for target in (
        "install:",
        "install-dev:",
        "doctor:",
        "audit:",
        "control-center:",
        "workbook-gate:",
        "workbook-signoff:",
        "test:",
    ):
        assert target in makefile
    assert "SOURCE_ENV := PYTHONPATH=src" in makefile
    assert "CLI := $(SOURCE_ENV) uv run python -m github_repo_auditor.cli" in makefile
    assert "$(CLI) $(USERNAME) --doctor $(ARGS)" in makefile
    assert "$(CLI) $(USERNAME) --excel-mode standard $(ARGS)" in makefile
    assert "$(CLI) $(USERNAME) --control-center $(ARGS)" in makefile
    assert "$(PYTHON) -m github_repo_auditor.workbook_gate $(ARGS)" in makefile
    assert (
        "$(PYTHON) -m github_repo_auditor.workbook_gate --record-signoff $(ARGS)"
        in makefile
    )
    assert "$(CLI) --help" in makefile


def test_example_audit_config_is_parseable():
    pytest.importorskip("yaml")
    inspection = inspect_config(
        ROOT / "config" / "examples" / "audit-config.example.yaml"
    )
    assert inspection.exists is True
    assert inspection.errors == []
    assert inspection.data["excel_mode"] == "standard"
    assert inspection.data["preflight_mode"] == "auto"
    assert inspection.data["watch_strategy"] == "adaptive"


def test_example_notion_config_is_parseable():
    data = json.loads(
        (ROOT / "config" / "examples" / "notion-config.example.json").read_text()
    )
    assert "events_database_id" in data
    assert "weekly_reviews_db_id" in data


def test_workflows_install_package_and_use_audit_console_script():
    workflow_path = ROOT / ".github" / "workflows" / "audit.yml"
    contents = workflow_path.read_text()
    assert 'pip install -e ".[config]"' in contents
    assert (
        'audit "$USERNAME" --incremental --html --badges --diff --excel-mode standard'
        in contents
    )
    assert 'audit "$USERNAME" --control-center' in contents
    assert "--issue-state" in contents
    assert "gh issue reopen" in contents
    assert "gh issue close" in contents
    assert "USERNAME=\"${{ github.event.inputs.username || 'saagpatel' }}\"" in contents
    assert "git add output/" not in contents
    assert "Audit Regression:" not in contents
