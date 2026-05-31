"""Tests for the parallel doc-truth-up batch runner.

Covers the two behaviors added for the time-optimized Tier 2 sweep:
1. ``select_targets`` orders repos drift-priority (drifted, then disagreement
   count) so a small ``--limit`` smoke samples the most-likely-drifted repos.
2. ``run_batch`` fans ``run_one`` out across a bounded thread pool, aggregates
   every result, and isolates a crashing repo instead of sinking the batch.

The runner lives in ``scripts/`` (not the ``src`` package), so it is loaded by
file path to keep the test self-contained.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

_SPEC = importlib.util.spec_from_file_location(
    "doc_truth_up_batch",
    Path(__file__).resolve().parent.parent / "scripts" / "doc_truth_up_batch.py",
)
batch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(batch)


def _args(targets_path: Path, **overrides) -> SimpleNamespace:
    base = {"targets": str(targets_path), "repo": "", "tier": "2", "limit": 0}
    base.update(overrides)
    return SimpleNamespace(**base)


def _write_targets(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "targets.json"
    p.write_text(json.dumps(rows))
    return p


class TestSelectTargetsDriftPriority:
    def test_orders_drifted_first_then_by_disagreement_count(self, tmp_path: Path):
        # Deliberately NOT in priority order in the file.
        rows = [
            {
                "project_key": "A",
                "abs_path": "/tmp/a",
                "tier": 2,
                "drifted": False,
                "disagreement_count": 0,
            },
            {
                "project_key": "B",
                "abs_path": "/tmp/b",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 1,
            },
            {
                "project_key": "C",
                "abs_path": "/tmp/c",
                "tier": 2,
                "drifted": False,
                "disagreement_count": 5,
            },
            {
                "project_key": "D",
                "abs_path": "/tmp/d",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 3,
            },
        ]
        out = batch.select_targets(_args(_write_targets(tmp_path, rows)))
        # drifted (D,B by count desc) before non-drifted (C,A by count desc).
        assert [t["project_key"] for t in out] == ["D", "B", "C", "A"]

    def test_sort_is_stable_for_equal_priority(self, tmp_path: Path):
        rows = [
            {
                "project_key": "D",
                "abs_path": "/tmp/d",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 3,
            },
            {
                "project_key": "E",
                "abs_path": "/tmp/e",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 3,
            },
        ]
        out = batch.select_targets(_args(_write_targets(tmp_path, rows)))
        assert [t["project_key"] for t in out] == ["D", "E"]

    def test_limit_takes_top_priority_after_sort(self, tmp_path: Path):
        rows = [
            {
                "project_key": "A",
                "abs_path": "/tmp/a",
                "tier": 2,
                "drifted": False,
                "disagreement_count": 0,
            },
            {
                "project_key": "B",
                "abs_path": "/tmp/b",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 1,
            },
            {
                "project_key": "D",
                "abs_path": "/tmp/d",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 3,
            },
        ]
        out = batch.select_targets(_args(_write_targets(tmp_path, rows), limit=2))
        assert [t["project_key"] for t in out] == ["D", "B"]

    def test_tolerates_missing_drift_fields(self, tmp_path: Path):
        rows = [
            {"project_key": "A", "abs_path": "/tmp/a", "tier": 2},  # no drift fields
            {
                "project_key": "B",
                "abs_path": "/tmp/b",
                "tier": 2,
                "drifted": True,
                "disagreement_count": 2,
            },
        ]
        out = batch.select_targets(_args(_write_targets(tmp_path, rows)))
        assert [t["project_key"] for t in out] == ["B", "A"]


class TestRunBatch:
    def _targets(self, n: int) -> list[dict]:
        return [{"project_key": f"R{i}", "abs_path": f"/tmp/r{i}"} for i in range(n)]

    def test_runs_every_target_exactly_once(self):
        targets = self._targets(20)

        def fake(t, prompt, settings, model, timeout, done_branch):
            return {"project_key": t["project_key"], "status": "ran"}

        results = batch.run_batch(
            targets, "p", "s", "sonnet", 1200, "docs/truth-up-x", 8, runner=fake
        )

        assert len(results) == 20
        assert {r["project_key"] for r in results} == {f"R{i}" for i in range(20)}
        assert all(r["status"] == "ran" for r in results)

    def test_isolates_a_crashing_repo(self):
        targets = self._targets(5)

        def fake(t, prompt, settings, model, timeout, done_branch):
            if t["project_key"] == "R2":
                raise ValueError("boom")
            return {"project_key": t["project_key"], "status": "ran"}

        results = batch.run_batch(
            targets, "p", "s", "sonnet", 1200, "docs/truth-up-x", 4, runner=fake
        )

        by_key = {r["project_key"]: r for r in results}
        assert len(results) == 5
        assert by_key["R2"]["status"] == "error"
        assert "runner raised" in by_key["R2"]["reason"]
        assert all(by_key[f"R{i}"]["status"] == "ran" for i in (0, 1, 3, 4))

    def test_concurrency_one_still_processes_all(self):
        targets = self._targets(3)

        def fake(t, prompt, settings, model, timeout, done_branch):
            return {"project_key": t["project_key"], "status": "ran"}

        results = batch.run_batch(
            targets, "p", "s", "sonnet", 1200, "docs/truth-up-x", 1, runner=fake
        )
        assert {r["project_key"] for r in results} == {"R0", "R1", "R2"}

    def test_passes_runner_args_through(self):
        targets = self._targets(1)
        seen = {}

        def fake(t, prompt, settings, model, timeout, done_branch):
            seen.update(
                prompt=prompt,
                settings=settings,
                model=model,
                timeout=timeout,
                done_branch=done_branch,
            )
            return {"project_key": t["project_key"], "status": "ran"}

        batch.run_batch(targets, "PROMPT", "SETT", "haiku", 999, "docs/truth-up-z", 2, runner=fake)
        assert seen == {
            "prompt": "PROMPT",
            "settings": "SETT",
            "model": "haiku",
            "timeout": 999,
            "done_branch": "docs/truth-up-z",
        }
