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

    assert "GitHub Releases remain the supported public" in distribution_doc
    assert "PyPI publishing is not active yet" in distribution_doc
    assert "docs/distribution.md" in readme
    assert "scripts/release.sh --publish-pypi" in release_gates
