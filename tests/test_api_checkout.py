from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.api_checkout import materialize_api_checkout, materialize_api_workspace
from src.models import RepoMetadata


def _meta(name: str = "demo", full_name: str = "octocat/demo") -> RepoMetadata:
    dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return RepoMetadata(
        name=name,
        full_name=full_name,
        description="d",
        language="Python",
        languages={"Python": 100},
        private=False,
        fork=False,
        archived=False,
        created_at=dt,
        updated_at=dt,
        pushed_at=dt,
        default_branch="main",
        stars=1,
        forks=0,
        open_issues=0,
        size_kb=10,
        html_url="https://example/x",
        clone_url="https://example/x.git",
        topics=[],
    )


class _FakeClient:
    """Duck-typed stand-in for GitHubClient — no HTTP."""

    def __init__(self, tree: dict, contents: dict[str, str] | None = None) -> None:
        self._tree = tree
        self._contents = contents or {}
        self.content_requests: list[str] = []

    def get_repo_tree(self, owner: str, repo: str, ref: str) -> dict:
        return self._tree

    def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
        max_bytes: int = 1_000_000,
    ) -> str | None:
        self.content_requests.append(path)
        return self._contents.get(path)


def test_materialize_creates_skeleton_dirs_and_files(tmp_path):
    tree = {
        "available": True,
        "truncated": False,
        "files": ["README.md", "src/main.py", "tests/test_main.py"],
        "dirs": ["src", "tests"],
    }
    client = _FakeClient(tree, contents={"README.md": "# Demo\nHello\n"})
    dest = tmp_path / "demo"

    result = materialize_api_checkout(_meta(), client, dest)

    assert result == dest
    assert (dest / "src").is_dir()
    assert (dest / "tests").is_dir()
    assert (dest / "src" / "main.py").is_file()
    assert (dest / "tests" / "test_main.py").is_file()


def test_curated_content_files_are_written_with_real_content(tmp_path):
    tree = {
        "available": True,
        "truncated": False,
        "files": ["README.md", "pyproject.toml", "src/main.py"],
        "dirs": ["src"],
    }
    client = _FakeClient(
        tree,
        contents={
            "README.md": "# Title\n\nLong readme body.\n",
            "pyproject.toml": "[project]\nname='demo'\n",
        },
    )
    dest = tmp_path / "demo"

    materialize_api_checkout(_meta(), client, dest)

    assert (dest / "README.md").read_text() == "# Title\n\nLong readme body.\n"
    assert "name='demo'" in (dest / "pyproject.toml").read_text()
    # Source files are presence-only (empty) — never content-fetched.
    assert (dest / "src" / "main.py").read_text() == ""
    assert "src/main.py" not in client.content_requests


def test_unavailable_tree_yields_empty_dir(tmp_path):
    client = _FakeClient(
        {"available": False, "files": [], "dirs": [], "truncated": False}
    )
    dest = tmp_path / "empty"

    result = materialize_api_checkout(_meta(), client, dest)

    assert result == dest
    assert dest.is_dir()
    assert list(dest.iterdir()) == []


def test_path_traversal_entries_are_rejected(tmp_path):
    tree = {
        "available": True,
        "truncated": False,
        "files": ["../escape.txt", "/abs/evil.txt", "ok.py"],
        "dirs": ["../evildir"],
    }
    client = _FakeClient(tree)
    dest = tmp_path / "demo"

    materialize_api_checkout(_meta(), client, dest)

    # Nothing escaped the destination directory.
    assert not (tmp_path / "escape.txt").exists()
    assert not Path("/abs/evil.txt").exists()
    assert not (tmp_path / "evildir").exists()
    # The safe file still materialized.
    assert (dest / "ok.py").is_file()


def test_max_files_cap_is_respected(tmp_path):
    files = [f"f{i}.py" for i in range(50)]
    tree = {"available": True, "truncated": False, "files": files, "dirs": []}
    client = _FakeClient(tree)
    dest = tmp_path / "demo"

    materialize_api_checkout(_meta(), client, dest, max_files=10)

    created = list(dest.rglob("*.py"))
    assert len(created) == 10


def test_content_fetch_budget_is_bounded(tmp_path):
    # Many README-like content files, but only a bounded number get fetched.
    files = [f"pkg{i}/README.md" for i in range(30)]
    dirs = [f"pkg{i}" for i in range(30)]
    tree = {"available": True, "truncated": False, "files": files, "dirs": dirs}
    contents = {f: "# readme\n" for f in files}
    client = _FakeClient(tree, contents=contents)
    dest = tmp_path / "demo"

    materialize_api_checkout(_meta(), client, dest, max_content_files=5)

    assert len(client.content_requests) == 5


def test_workspace_yields_paths_and_cleans_up():
    tree = {"available": True, "truncated": False, "files": ["README.md"], "dirs": []}
    client = _FakeClient(tree, contents={"README.md": "# hi\n"})
    repos = [_meta(name="a", full_name="o/a"), _meta(name="b", full_name="o/b")]

    captured: dict[str, Path] = {}
    with materialize_api_workspace(repos, client) as workspace:
        assert set(workspace.keys()) == {"a", "b"}
        for name, path in workspace.items():
            assert path.is_dir()
            captured[name] = path
        assert (workspace["a"] / "README.md").read_text() == "# hi\n"

    # Temp dirs are removed when the context exits.
    for path in captured.values():
        assert not path.exists()


def test_null_byte_paths_are_rejected(tmp_path):
    tree = {
        "available": True,
        "truncated": False,
        "files": ["ok.py", "evil\x00.py"],
        "dirs": [],
    }
    client = _FakeClient(tree)
    dest = tmp_path / "demo"

    materialize_api_checkout(_meta(), client, dest)

    assert (dest / "ok.py").is_file()
    # The null-byte entry is rejected at the guard, not written.
    assert len(list(dest.rglob("*.py"))) == 1
