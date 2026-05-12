"""Smoke tests for setuptools-scm tag-derived versioning (Arc G S8.1)."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import pytest

PYPROJECT_PATH = Path(__file__).parent.parent / "pyproject.toml"


def test_pyproject_no_static_version() -> None:
    """pyproject.toml must NOT carry a static version = line under [project].

    A static version would silently shadow setuptools-scm and re-introduce the
    regression this sprint is designed to prevent.
    """
    with open(PYPROJECT_PATH, "rb") as fh:
        data = tomllib.load(fh)

    project = data.get("project", {})
    assert "version" not in project, (
        "Static 'version' key found in [project]. "
        "Remove it and use dynamic = ['version'] with setuptools-scm."
    )
    assert "version" in project.get("dynamic", []), (
        "'version' must be listed in [project] dynamic = [...] for setuptools-scm."
    )


def test_pyproject_setuptools_scm_table() -> None:
    """pyproject.toml must have a [tool.setuptools_scm] table with fallback_version."""
    with open(PYPROJECT_PATH, "rb") as fh:
        data = tomllib.load(fh)

    scm = data.get("tool", {}).get("setuptools_scm", None)
    assert scm is not None, "Missing [tool.setuptools_scm] table in pyproject.toml."
    assert "fallback_version" in scm, (
        "[tool.setuptools_scm] must define fallback_version "
        "so builds outside a tagged git checkout don't fail."
    )
    assert scm["fallback_version"], "fallback_version must be a non-empty string."


def test_installed_package_version_resolvable() -> None:
    """If the package is installed (editable or otherwise), importlib.metadata must
    return a non-empty version string.  Skip gracefully when it's not installed so
    this test doesn't block CI environments that only run the suite without installing.
    """
    try:
        ver = importlib.metadata.version("github-repo-auditor")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip(
            "github-repo-auditor not installed in this environment — skipping runtime version check."
        )

    assert ver, "importlib.metadata.version() returned an empty string."
    assert isinstance(ver, str), f"Expected str, got {type(ver)}"
