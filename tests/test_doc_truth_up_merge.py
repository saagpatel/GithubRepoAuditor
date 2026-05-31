"""Tests for the doc-truth-up FF-merge helper's safety gate.

``plan_merge`` is the decision that guards a 49-repo branch mutation, so it is
exercised against a real temporary git repo for each branch: the happy
fast-forward, a non-doc commit (must skip), a moved base (must skip), and a
missing branch (must skip). ``merge_one`` is then run end-to-end to confirm the
fast-forward lands and the reconciliation branch is safe-deleted.

The helper lives in ``scripts/`` (not the ``src`` package); load it by file path.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "doc_truth_up_merge",
    Path(__file__).resolve().parent.parent / "scripts" / "doc_truth_up_merge.py",
)
merge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(merge)

BR = "docs/truth-up-2026-05-30"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.test")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# original\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    return repo


def _make_recon_branch(repo: Path, *, files: dict[str, str]) -> None:
    """Create the reconciliation branch with one commit touching `files`, then
    return the repo to `main` (mirrors run_one restoring to the origin branch)."""
    _git(repo, "checkout", "-b", BR)
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        _git(repo, "add", name)
    _git(repo, "commit", "-m", "docs: reconcile")
    _git(repo, "checkout", "main")


class TestPlanMerge:
    def test_happy_doc_only_fast_forward(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _make_recon_branch(
            repo, files={"README.md": "# reconciled\n", "DOC-RECONCILIATION.md": "log\n"}
        )
        plan = merge.plan_merge(str(repo), BR)
        assert plan["action"] == "merge"
        assert plan["target"] == "main"

    def test_skips_when_no_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        plan = merge.plan_merge(str(repo), BR)
        assert plan["action"] == "skip"
        assert plan["reason"] == "no reconciliation branch"

    def test_skips_when_commit_touches_non_doc(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _make_recon_branch(repo, files={"README.md": "# r\n", "src/main.py": "print(1)\n"})
        plan = merge.plan_merge(str(repo), BR)
        assert plan["action"] == "skip"
        assert plan["reason"] == "non-doc files in commit"
        assert plan["non_doc"] == ["src/main.py"]

    def test_skips_when_base_moved(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _make_recon_branch(repo, files={"README.md": "# reconciled\n"})
        # main advances after the reconciliation was cut → ff-only is unsafe.
        (repo / "OTHER.md").write_text("later\n")
        _git(repo, "add", "OTHER.md")
        _git(repo, "commit", "-m", "later work on main")
        plan = merge.plan_merge(str(repo), BR)
        assert plan["action"] == "skip"
        assert "diverged" in plan["reason"]

    def test_skips_when_more_than_one_commit_ahead(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _git(repo, "checkout", "-b", BR)
        for i in range(2):
            (repo / "CLAUDE.md").write_text(f"rev {i}\n")
            _git(repo, "add", "CLAUDE.md")
            _git(repo, "commit", "-m", f"docs {i}")
        _git(repo, "checkout", "main")
        plan = merge.plan_merge(str(repo), BR)
        assert plan["action"] == "skip"
        assert "expected exactly 1 commit" in plan["reason"]


class TestMergeOne:
    def test_executes_fast_forward_and_deletes_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _make_recon_branch(repo, files={"README.md": "# reconciled\n"})
        recon_tip = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", BR], capture_output=True, text=True
        ).stdout.strip()

        r = merge.merge_one(str(repo), BR, execute=True)

        assert r["action"] == "merged"
        # main fast-forwarded to the reconciliation commit
        main_tip = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "main"], capture_output=True, text=True
        ).stdout.strip()
        assert main_tip == recon_tip
        # reconciliation branch deleted
        assert (
            subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"refs/heads/{BR}"],
                capture_output=True,
            ).returncode
            != 0
        )
        # the reconciled content is on main, no merge commit (linear history)
        assert (repo / "README.md").read_text() == "# reconciled\n"

    def test_dry_run_does_not_mutate(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _make_recon_branch(repo, files={"README.md": "# reconciled\n"})
        r = merge.merge_one(str(repo), BR, execute=False)
        assert r["action"] == "merge"  # planned, not performed
        # branch still exists, main untouched
        assert (
            subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"refs/heads/{BR}"],
                capture_output=True,
            ).returncode
            == 0
        )
        assert (repo / "README.md").read_text() == "# original\n"
