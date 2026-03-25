from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models import AnalyzerResult, RepoAudit, RepoMetadata


@pytest.fixture
def sample_metadata() -> RepoMetadata:
    """A realistic RepoMetadata for testing."""
    return RepoMetadata(
        name="test-repo",
        full_name="user/test-repo",
        description="A test repository",
        language="Python",
        languages={"Python": 5000, "Shell": 200},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=5,
        forks=1,
        open_issues=2,
        size_kb=1024,
        html_url="https://github.com/user/test-repo",
        clone_url="https://github.com/user/test-repo.git",
        topics=["python", "cli"],
    )


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for analyzer testing."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # README
    (repo / "README.md").write_text(
        "# Test Repo\n\nA great project for testing.\n\n"
        "## Installation\n\n```bash\npip install test-repo\n```\n\n"
        "## Usage\n\n```python\nimport test_repo\n```\n"
    )

    # .gitignore
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n.env\n")

    # Source
    src = repo / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text(
        "def main() -> None:\n"
        "    print('hello')\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    # Tests
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text(
        "def test_main():\n    assert True\n"
    )
    (tests / "test_utils.py").write_text(
        "def test_utils():\n    assert True\n"
    )

    # Config
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "test-repo"\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )
    (repo / "requirements.txt").write_text("requests>=2.31.0\npytest>=7.0\n")

    # LICENSE
    (repo / "LICENSE").write_text("MIT License\n")

    return repo


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """A repo with nothing but a README."""
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Empty\n")
    return repo


@pytest.fixture
def swift_repo(tmp_path: Path) -> Path:
    """An iOS/Swift repo with Xcode project structure."""
    repo = tmp_path / "swift-repo"
    repo.mkdir()

    (repo / ".gitignore").write_text("*.xcuserdata\nDerivedData/\n")

    # Xcode project
    xcproj = repo / "SwiftApp.xcodeproj"
    xcproj.mkdir()
    (xcproj / "project.pbxproj").write_text("// xcode project\n")

    # Swift sources
    sources = repo / "SwiftApp"
    sources.mkdir()
    (sources / "App.swift").write_text(
        "import SwiftUI\n\n"
        "@main\n"
        "struct SwiftApp: App {\n"
        "    var body: some Scene {\n"
        "        WindowGroup { ContentView() }\n"
        "    }\n"
        "}\n"
    )
    (sources / "ContentView.swift").write_text(
        "import SwiftUI\n\nstruct ContentView: View {\n"
        "    var body: some View { Text(\"Hello\") }\n}\n"
    )

    # Tests
    tests = repo / "SwiftAppTests"
    tests.mkdir()
    (tests / "SwiftAppTests.swift").write_text(
        "import XCTest\n@testable import SwiftApp\n\n"
        "final class SwiftAppTests: XCTestCase {\n"
        "    func testExample() { XCTAssertTrue(true) }\n}\n"
    )

    return repo
