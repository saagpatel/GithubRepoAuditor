from __future__ import annotations

import json
from pathlib import Path

from scripts.check_mutation_score import classify_exit_codes, evaluate_score, main


def _write_meta(root: Path, values: list[int | None]) -> None:
    path = root / "src" / "example.py.meta"
    path.parent.mkdir(parents=True)
    payload = {"exit_code_by_key": {f"mutant_{index}": value for index, value in enumerate(values)}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluate_score_excludes_timeouts() -> None:
    counts = classify_exit_codes([1] * 9 + [0, 36])

    passed, score = evaluate_score(counts, 0.85)

    assert passed is True
    assert score == 0.9


def test_main_fails_closed_on_unchecked_results(tmp_path: Path) -> None:
    _write_meta(tmp_path, [1, 0, None])

    assert main(["--mutants-dir", str(tmp_path), "--minimum", "0.5"]) == 1


def test_main_fails_when_no_results_exist(tmp_path: Path) -> None:
    assert main(["--mutants-dir", str(tmp_path)]) == 2


def test_main_passes_complete_results_at_threshold(tmp_path: Path) -> None:
    _write_meta(tmp_path, [1] * 17 + [0] * 3 + [36])

    assert main(["--mutants-dir", str(tmp_path), "--minimum", "0.85"]) == 0
