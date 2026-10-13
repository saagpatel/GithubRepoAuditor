"""Keep the package description aligned with the built-in analyzer registry."""

from pathlib import Path
import tomllib

from github_repo_auditor.analyzers import ALL_ANALYZERS


def test_package_description_matches_analyzer_count():
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    )
    assert (
        f"with {len(ALL_ANALYZERS)} analysis dimensions"
        in project["project"]["description"]
    )
