#!/usr/bin/env python3
"""Fail closed when mutmut 3 results do not satisfy the release threshold."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Iterable


KILLED_EXIT_CODES = {1, 3, 37}
SURVIVED_EXIT_CODES = {0}
TIMEOUT_EXIT_CODES = {-24, 24, 36, 152, 255}


def load_exit_codes(mutants_dir: Path) -> list[int | None]:
    codes: list[int | None] = []
    for meta_path in sorted(mutants_dir.rglob("*.meta")):
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        results = payload.get("exit_code_by_key")
        if not isinstance(results, dict):
            raise ValueError(f"{meta_path} has no exit_code_by_key object")
        for value in results.values():
            if value is not None and not isinstance(value, int):
                raise ValueError(f"{meta_path} contains a non-integer exit code")
            codes.append(value)
    return codes


def classify_exit_codes(codes: Iterable[int | None]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for code in codes:
        if code in KILLED_EXIT_CODES:
            counts["killed"] += 1
        elif code in SURVIVED_EXIT_CODES:
            counts["survived"] += 1
        elif code in TIMEOUT_EXIT_CODES:
            counts["timeout"] += 1
        elif code is None:
            counts["unchecked"] += 1
        else:
            counts["invalid"] += 1
    return counts


def evaluate_score(counts: Counter[str], minimum: float) -> tuple[bool, float]:
    denominator = counts["killed"] + counts["survived"]
    score = counts["killed"] / denominator if denominator else 0.0
    complete = counts["unchecked"] == 0 and counts["invalid"] == 0
    return complete and denominator > 0 and score >= minimum, score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutants-dir", type=Path, default=Path("mutants"))
    parser.add_argument("--minimum", type=float, default=0.85)
    args = parser.parse_args(argv)

    if not 0.0 <= args.minimum <= 1.0:
        parser.error("--minimum must be between 0 and 1")

    try:
        codes = load_exit_codes(args.mutants_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Mutation gate could not read results: {exc}")
        return 2

    if not codes:
        print(f"Mutation gate found no results under {args.mutants_dir}")
        return 2

    counts = classify_exit_codes(codes)
    passed, score = evaluate_score(counts, args.minimum)
    print(
        "Mutation gate: "
        f"killed={counts['killed']} survived={counts['survived']} "
        f"timeouts={counts['timeout']} unchecked={counts['unchecked']} "
        f"invalid={counts['invalid']} score={score:.1%} "
        f"threshold={args.minimum:.1%}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
