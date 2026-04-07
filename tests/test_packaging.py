from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from src.config import inspect_config


ROOT = Path(__file__).resolve().parents[1]


def _project_dependency_names() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    return {item.split(">=", 1)[0].split("[", 1)[0] for item in deps}


def _requirements_names() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    cleaned = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    return {item.split(">=", 1)[0].split("[", 1)[0] for item in cleaned}


def test_pyproject_exposes_audit_console_script():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["audit"] == "src.cli:main"


def test_requirements_cover_runtime_and_config_dependencies():
    requirement_names = _requirements_names()
    assert _project_dependency_names().issubset(requirement_names)
    assert "pyyaml" in requirement_names


def test_makefile_includes_operator_entrypoints():
    makefile = (ROOT / "Makefile").read_text()
    for target in ("install:", "install-dev:", "doctor:", "audit:", "control-center:", "workbook-gate:", "workbook-signoff:", "test:"):
        assert target in makefile
    assert "audit $(USERNAME) --doctor $(ARGS)" in makefile
    assert "audit $(USERNAME) --excel-mode standard $(ARGS)" in makefile
    assert "audit $(USERNAME) --control-center $(ARGS)" in makefile
    assert "$(PYTHON) -m src.workbook_gate $(ARGS)" in makefile
    assert "$(PYTHON) -m src.workbook_gate --record-signoff $(ARGS)" in makefile


def test_example_audit_config_is_parseable():
    pytest.importorskip("yaml")
    inspection = inspect_config(ROOT / "config" / "examples" / "audit-config.example.yaml")
    assert inspection.exists is True
    assert inspection.errors == []
    assert inspection.data["excel_mode"] == "standard"
    assert inspection.data["preflight_mode"] == "auto"
    assert inspection.data["watch_strategy"] == "adaptive"


def test_example_notion_config_is_parseable():
    data = json.loads((ROOT / "config" / "examples" / "notion-config.example.json").read_text())
    assert "events_database_id" in data
    assert "weekly_reviews_db_id" in data


def test_workflows_install_package_and_use_audit_console_script():
    workflow_path = ROOT / ".github" / "workflows" / "audit.yml"
    contents = workflow_path.read_text()
    assert 'pip install -e ".[config]"' in contents
    assert "audit \"$USERNAME\" --incremental --html --badges --diff --excel-mode standard" in contents
    assert "audit \"$USERNAME\" --control-center" in contents
    assert "--issue-state" in contents
    assert "gh issue reopen" in contents
    assert "gh issue close" in contents
    assert 'USERNAME="${{ github.event.inputs.username || \'saagpatel\' }}"' in contents
    assert "git add output/" not in contents
    assert "Audit Regression:" not in contents
