"""Distribution policy checks for the public package surface."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_pyproject_has_public_package_metadata() -> None:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]

    assert project["name"] == "github-repo-auditor"
    assert project.get("authors"), "PyPI metadata should include an author entry."
    assert project.get("classifiers"), "PyPI metadata should include classifiers."
    assert project.get("keywords"), "PyPI metadata should include package keywords."
    assert "Documentation" in project.get("urls", {})
    assert "Changelog" in project.get("urls", {})


def test_release_script_requires_explicit_pypi_publish_flag() -> None:
    release_script = (ROOT / "scripts" / "release.sh").read_text()

    assert "PUBLISH_PYPI=false" in release_script
    assert "--publish-pypi" in release_script
    assert 'if [ "$PUBLISH_PYPI" != "true" ]' in release_script
    assert "PyPI publish not requested" in release_script


def test_distribution_docs_name_supported_public_channel() -> None:
    distribution_doc = (ROOT / "docs" / "distribution.md").read_text()
    readme = (ROOT / "README.md").read_text()
    release_gates = (ROOT / "docs" / "release-gates.md").read_text()
    workflows_readme = (ROOT / ".github" / "workflows" / "README.md").read_text()

    assert "distributed through PyPI and GitHub Releases" in distribution_doc
    assert "PyPI publishing is active" in distribution_doc
    assert "uv tool install github-repo-auditor" in readme
    assert "pipx install github-repo-auditor" in readme
    assert "github.com/saagpatel/GithubRepoAuditor/actions/workflows/ci.yml/badge.svg" in readme
    assert "img.shields.io/pypi/v/github-repo-auditor.svg" in readme
    assert "docs/distribution.md" in readme
    assert "PyPI publishing is active through the manual" in release_gates
    assert "not part of the current public install story" not in release_gates
    assert "remaining PyPI activation checklist" not in release_gates
    assert "scripts/release.sh --publish-pypi" in release_gates
    assert "pypi.yml" in workflows_readme
    assert "id-token: write" in workflows_readme


def test_pypi_workflow_is_manual_trusted_publishing_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pypi.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "environment: pypi" in workflow
    assert "id-token: write" in workflow
    # SHA-pinned to the v1 trusted-publishing release line
    assert "pypa/gh-action-pypi-publish@" in workflow
    assert "# v1" in workflow
    assert "actions/upload-artifact" in workflow
    assert "actions/download-artifact" in workflow


def test_public_repo_has_code_scanning_workflow_documented() -> None:
    workflow = (ROOT / ".github" / "workflows" / "codeql.yml").read_text()
    workflows_readme = (ROOT / ".github" / "workflows" / "README.md").read_text()
    security_model = (ROOT / "docs" / "security-model.md").read_text()

    # CodeQL actions SHA-pinned to the v4 line
    assert "github/codeql-action/init@" in workflow
    assert "github/codeql-action/analyze@" in workflow
    assert "# v4" in workflow
    assert "security-events: write" in workflow
    assert "pull_request:" in workflow
    assert "schedule:" in workflow
    assert 'language: ["python"]' in workflow
    assert "security-extended,security-and-quality" in workflow
    assert "`codeql.yml` — Code Scanning" in workflows_readme
    assert ".github/workflows/codeql.yml" in security_model
    assert "Dependabot alerting is enabled" in security_model
