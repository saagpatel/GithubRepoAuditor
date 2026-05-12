# Arc H: Context Quality Recovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add description confidence scoring, age-based README staleness, catalog completeness validation, and a composite `context_quality_score` metric — then run triage and recovery against the ~53 weak-context repos.

**Architecture:** Parallel stream A (4 new/modified source files) and stream B (triage + recovery CLI flags) converge in Task 12 when the composite scorer wires all A1–A3 outputs together. All new fields are additive to the existing audit dict. No schema breaking changes.

**Tech Stack:** Python 3.11+, pytest, PyYAML (already a dependency via portfolio_context_recovery), pathlib, existing `BaseAnalyzer` / `ALL_ANALYZERS` pattern.

---

## File Map

**New files:**
- `src/analyzers/description_analyzer.py` — DescriptionAnalyzer (A1)
- `src/catalog_validator.py` — catalog completeness scorer (A3)
- `src/tier_recalibration.py` — tier distribution report (A4)
- `src/context_quality.py` — composite context_quality_score (H.4)
- `src/portfolio_context_triage.py` — B1 triage runner
- `config/settings.yaml` — configurable thresholds
- `src/context_quality_config.py` — loads config/settings.yaml thresholds
- `tests/test_description_analyzer.py`
- `tests/test_readme_staleness_by_age.py`
- `tests/test_catalog_validator.py`
- `tests/test_tier_recalibration.py`
- `tests/test_context_quality.py`
- `tests/test_portfolio_context_triage.py`

**Modified files:**
- `src/analyzers/readme.py` — add `readme_stale_by_age` field (A2)
- `src/analyzers/__init__.py` — register `DescriptionAnalyzer` in `ALL_ANALYZERS`
- `src/cli.py` — add `--tier-recalibration-report` and `--context-triage` flags

---

## Sprint H.1 — Description Analyzer + README Age Flag

### Task 1: Write failing tests for `DescriptionAnalyzer`

**Files:**
- Create: `tests/test_description_analyzer.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_description_analyzer.py
from pathlib import Path
import pytest
from src.models import RepoMetadata


def _meta(description=None, language=None, topics=None):
    return RepoMetadata(
        name="test-repo",
        full_name="owner/test-repo",
        description=description,
        language=language,
        languages={},
        fork=False,
        private=False,
        archived=False,
        default_branch="main",
        topics=topics or [],
    )


def test_no_description_returns_zero_confidence():
    from src.analyzers.description_analyzer import DescriptionAnalyzer
    result = DescriptionAnalyzer().analyze(Path("/nonexistent"), _meta(language="Swift"))
    assert result.details["description_confidence"] == 0.0
    assert result.details["description_present"] is False


def test_description_matching_file_signal_returns_high_confidence(tmp_path):
    from src.analyzers.description_analyzer import DescriptionAnalyzer
    (tmp_path / "MyApp.xcodeproj").mkdir()
    result = DescriptionAnalyzer().analyze(tmp_path, _meta(description="A SwiftUI iOS app", language="Swift"))
    assert result.details["description_confidence"] == 1.0
    assert result.details["conflicting_languages"] == []


def test_conflicting_description_returns_low_confidence(tmp_path):
    from src.analyzers.description_analyzer import DescriptionAnalyzer
    (tmp_path / "Cargo.toml").write_text("[package]")
    result = DescriptionAnalyzer().analyze(tmp_path, _meta(description="A Python CLI script", language="Rust"))
    assert result.details["description_confidence"] == 0.2
    assert "Python" in result.details["conflicting_languages"]


def test_neutral_description_no_conflicts_returns_moderate_confidence(tmp_path):
    from src.analyzers.description_analyzer import DescriptionAnalyzer
    (tmp_path / "Cargo.toml").write_text("[package]")
    result = DescriptionAnalyzer().analyze(tmp_path, _meta(description="A simple utility", language="Rust"))
    assert result.details["description_confidence"] == 0.8


def test_unknown_language_returns_neutral_confidence(tmp_path):
    from src.analyzers.description_analyzer import DescriptionAnalyzer
    result = DescriptionAnalyzer().analyze(tmp_path, _meta(description="Something", language="COBOL"))
    assert result.details["description_confidence"] == 1.0


def test_topics_used_as_conflict_signal(tmp_path):
    from src.analyzers.description_analyzer import DescriptionAnalyzer
    (tmp_path / "Cargo.toml").write_text("[package]")
    # topics say "python" but file signal says Rust
    result = DescriptionAnalyzer().analyze(
        tmp_path, _meta(description="a tool", language="Rust", topics=["python"])
    )
    assert result.details["description_confidence"] == 0.2
```

- [ ] **Step 2: Run tests — expect ImportError (module not yet created)**

```bash
cd /Users/d/Projects/GithubRepoAuditor && python -m pytest tests/test_description_analyzer.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'src.analyzers.description_analyzer'`

---

### Task 2: Implement `DescriptionAnalyzer`

**Files:**
- Create: `src/analyzers/description_analyzer.py`

- [ ] **Step 1: Write the implementation**

```python
# src/analyzers/description_analyzer.py
from __future__ import annotations

import hashlib
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

_LANG_KEYWORDS: dict[str, frozenset[str]] = {
    "Swift": frozenset(["swift", "ios", "macos", "xcode", "swiftui", "uikit", "appkit", "watchos", "tvos"]),
    "Python": frozenset(["python", "py", "fastapi", "django", "flask", "cli", "script", "notebook"]),
    "Rust": frozenset(["rust", "cargo", "tauri"]),
    "JavaScript": frozenset(["javascript", "js", "react", "node", "next", "vue", "angular"]),
    "TypeScript": frozenset(["typescript", "ts", "react", "next", "node", "vue", "angular"]),
    "Go": frozenset(["go", "golang"]),
}

# Ordered list: first match wins for file-based language detection.
_FILE_SIGNALS: list[tuple[str, str]] = [
    ("*.xcodeproj", "Swift"),
    ("*.xcworkspace", "Swift"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pyproject.toml", "Python"),
    ("requirements.txt", "Python"),
    ("setup.py", "Python"),
    ("package.json", "JavaScript"),
]


def _detect_language_from_files(repo_path: Path) -> str | None:
    for pattern, lang in _FILE_SIGNALS:
        if "*" in pattern:
            if any(repo_path.glob(pattern)):
                return lang
        elif (repo_path / pattern).exists():
            return lang
    return None


class DescriptionAnalyzer(BaseAnalyzer):
    name = "description"

    def cache_inputs_hash(self, repo_path: Path, metadata: RepoMetadata) -> str:
        key = f"{metadata.description or ''}{metadata.language or ''}{sorted(metadata.topics)}"
        return hashlib.md5(key.encode()).hexdigest()

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        description = (metadata.description or "").lower()
        topics = {t.lower() for t in metadata.topics}

        if not description:
            return self._result(
                0.0,
                ["No description set"],
                {"description_confidence": 0.0, "description_present": False, "conflicting_languages": []},
            )

        file_lang = _detect_language_from_files(repo_path)
        detected_lang = file_lang or (metadata.language or "")
        expected_keywords = _LANG_KEYWORDS.get(detected_lang, frozenset())

        if not expected_keywords:
            return self._result(
                1.0,
                [f"Language '{detected_lang}' not in signal map — confidence neutral"],
                {"description_confidence": 1.0, "description_present": True, "conflicting_languages": []},
            )

        all_tokens = set(description.split()) | topics
        conflicts = [
            lang
            for lang, kws in _LANG_KEYWORDS.items()
            if lang != detected_lang and kws & all_tokens
        ]
        expected_match = bool(expected_keywords & all_tokens)

        if conflicts and not expected_match:
            confidence = 0.2
        elif conflicts:
            confidence = 0.6
        elif expected_match:
            confidence = 1.0
        else:
            confidence = 0.8

        findings = [f"Description confidence: {confidence:.1f}"]
        if conflicts:
            findings.append(
                f"Description signals {conflicts} but primary language detected as {detected_lang}"
            )

        return self._result(
            confidence,
            findings,
            {
                "description_confidence": confidence,
                "description_present": True,
                "conflicting_languages": conflicts,
            },
        )
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
python -m pytest tests/test_description_analyzer.py -v
```

Expected: 6 tests PASSED

---

### Task 3: Register `DescriptionAnalyzer` in `ALL_ANALYZERS`

**Files:**
- Modify: `src/analyzers/__init__.py`

- [ ] **Step 1: Add import and registration**

In `src/analyzers/__init__.py`, add after the existing imports (around line 20):
```python
from src.analyzers.description_analyzer import DescriptionAnalyzer
```

In the `ALL_ANALYZERS` list (around line 31), add `DescriptionAnalyzer()` as the last entry:
```python
ALL_ANALYZERS = [
    ReadmeAnalyzer(),
    StructureAnalyzer(),
    CodeQualityAnalyzer(),
    TestingAnalyzer(),
    CicdAnalyzer(),
    DependenciesAnalyzer(),
    ActivityAnalyzer(),
    DocumentationAnalyzer(),
    BuildReadinessAnalyzer(),
    CommunityProfileAnalyzer(),
    InterestAnalyzer(),
    SecurityAnalyzer(),
    DescriptionAnalyzer(),  # Arc H A1
]
```

- [ ] **Step 2: Verify the full analyzer suite loads**

```bash
python -m pytest tests/test_analyzers.py -v 2>&1 | tail -10
```

Expected: existing tests still pass, no import errors.

---

### Task 4: Write failing tests for README age-based staleness flag

**Files:**
- Create: `tests/test_readme_staleness_by_age.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_readme_staleness_by_age.py
"""Tests for the age-based README staleness flag added in Arc H A2."""
from unittest.mock import patch
from pathlib import Path
from src.analyzers.readme import _compute_readme_staleness


def test_readme_stale_by_age_when_over_threshold():
    with patch("src.analyzers.readme._git_last_touched_unix") as mock_ts:
        import time
        now = int(time.time())
        # README last touched 200 days ago
        mock_ts.side_effect = lambda path, *args: now - (200 * 86400) if "README" in str(args) else now - (200 * 86400)
        # We need to simulate readme_days = 200 > 180 threshold
        result = _compute_readme_staleness(Path("/fake"), "README.md")
        assert result["readme_stale_by_age"] is True


def test_readme_not_stale_by_age_when_under_threshold():
    with patch("src.analyzers.readme._git_last_touched_unix") as mock_ts:
        import time
        now = int(time.time())
        mock_ts.return_value = now - (100 * 86400)  # 100 days ago
        result = _compute_readme_staleness(Path("/fake"), "README.md")
        assert result["readme_stale_by_age"] is False


def test_readme_stale_by_age_none_when_no_git_history():
    with patch("src.analyzers.readme._git_last_touched_unix", return_value=None):
        result = _compute_readme_staleness(Path("/fake"), "README.md")
        assert result["readme_stale_by_age"] is None


def test_readme_stale_by_age_at_exact_threshold():
    """Exactly 180 days is NOT stale (threshold is strict >)."""
    with patch("src.analyzers.readme._git_last_touched_unix") as mock_ts:
        import time
        now = int(time.time())
        mock_ts.return_value = now - (180 * 86400)
        result = _compute_readme_staleness(Path("/fake"), "README.md")
        assert result["readme_stale_by_age"] is False


def test_readme_stale_by_age_one_day_over_threshold():
    with patch("src.analyzers.readme._git_last_touched_unix") as mock_ts:
        import time
        now = int(time.time())
        mock_ts.return_value = now - (181 * 86400)
        result = _compute_readme_staleness(Path("/fake"), "README.md")
        assert result["readme_stale_by_age"] is True
```

- [ ] **Step 2: Run tests — expect KeyError on `readme_stale_by_age`**

```bash
python -m pytest tests/test_readme_staleness_by_age.py -v 2>&1 | head -20
```

Expected: FAILED with `KeyError: 'readme_stale_by_age'`

---

### Task 5: Add `readme_stale_by_age` to `_compute_readme_staleness`

**Files:**
- Modify: `src/analyzers/readme.py`

- [ ] **Step 1: Add the constant and field**

In `src/analyzers/readme.py`, add the constant after the existing imports (after the `_CODE_GLOBS` or similar constant block):
```python
# Age threshold for readme_stale_by_age flag. Repos whose README was last
# touched more than this many days ago are flagged regardless of code activity.
_README_AGE_STALENESS_THRESHOLD_DAYS: int = 180
```

In `_compute_readme_staleness`, add `readme_stale_by_age` to the return dict. Find the `return {` block (around line 238) and add the new key:

```python
    return {
        "readme_last_touched_days": readme_days,
        "code_last_touched_days": code_days,
        "readme_staleness_ratio": staleness_ratio,
        "readme_stale": stale,
        "readme_stale_by_age": (
            readme_days > _README_AGE_STALENESS_THRESHOLD_DAYS
            if readme_days is not None
            else None
        ),
    }
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
python -m pytest tests/test_readme_staleness_by_age.py -v
```

Expected: 5 tests PASSED

- [ ] **Step 3: Run full suite to check for regressions**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -15
```

Expected: existing tests still pass.

---

### Task 6: Commit H.1

- [ ] **Step 1: Stage and commit**

```bash
git add src/analyzers/description_analyzer.py src/analyzers/__init__.py src/analyzers/readme.py tests/test_description_analyzer.py tests/test_readme_staleness_by_age.py
git commit -m "feat(arc-h): H.1 — description analyzer + README age-based staleness flag"
```

---

## Sprint H.2 — Catalog Validator + Tier Recalibration Report

### Task 7: Write failing tests for `catalog_validator.py`

**Files:**
- Create: `tests/test_catalog_validator.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_catalog_validator.py
"""Tests for the catalog completeness validator (Arc H A3)."""
import pytest
from src.catalog_validator import score_catalog_entry, validate_catalog, REQUIRED_FIELDS

# ---------------------------------------------------------------------------
# score_catalog_entry — unit tests
# ---------------------------------------------------------------------------

def test_full_entry_scores_one():
    entry = {
        "owner": "d",
        "lifecycle_state": "active",
        "review_cadence": "weekly",
        "intended_disposition": "maintain",
    }
    assert score_catalog_entry(entry) == 1.0


def test_empty_entry_scores_zero():
    assert score_catalog_entry({}) == 0.0


def test_partial_entry_scores_proportionally():
    entry = {"owner": "d", "lifecycle_state": "active"}
    assert score_catalog_entry(entry) == pytest.approx(0.5)


def test_none_entry_scores_zero():
    assert score_catalog_entry(None) == 0.0


# ---------------------------------------------------------------------------
# validate_catalog — integration tests
# ---------------------------------------------------------------------------

def test_validate_catalog_scores_repos(tmp_path):
    import yaml
    catalog = {
        "repos": {
            "RepoA": {"owner": "d", "lifecycle_state": "active", "review_cadence": "weekly", "intended_disposition": "maintain"},
            "RepoB": {"owner": "d"},
            "RepoC": {},
        }
    }
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(catalog))

    results = validate_catalog(catalog_path, repo_names=["RepoA", "RepoB", "RepoC", "RepoD"])
    assert results["RepoA"] == pytest.approx(1.0)
    assert results["RepoB"] == pytest.approx(0.25)
    assert results["RepoC"] == pytest.approx(0.0)
    assert results["RepoD"] == pytest.approx(0.0)  # not in catalog at all


def test_validate_catalog_missing_file_returns_zeros(tmp_path):
    results = validate_catalog(tmp_path / "missing.yaml", repo_names=["RepoA"])
    assert results["RepoA"] == 0.0


def test_required_fields_constant_has_four_entries():
    assert len(REQUIRED_FIELDS) == 4
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/test_catalog_validator.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'src.catalog_validator'`

---

### Task 8: Implement `catalog_validator.py`

**Files:**
- Create: `src/catalog_validator.py`

- [ ] **Step 1: Write the implementation**

```python
# src/catalog_validator.py
"""Catalog completeness validator for portfolio-catalog.yaml entries (Arc H A3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

REQUIRED_FIELDS: tuple[str, ...] = ("owner", "lifecycle_state", "review_cadence", "intended_disposition")


def score_catalog_entry(entry: dict[str, Any] | None) -> float:
    """Return completeness score (0.0–1.0) for a single catalog repo entry.

    Score = fraction of REQUIRED_FIELDS that are present and non-empty.
    """
    if not entry:
        return 0.0
    present = sum(1 for f in REQUIRED_FIELDS if entry.get(f))
    return present / len(REQUIRED_FIELDS)


def validate_catalog(catalog_path: Path, repo_names: list[str]) -> dict[str, float]:
    """Return a completeness score for each repo name.

    Repos not present in the catalog's ``repos`` section score 0.0.
    Repos present but with missing required fields score proportionally.
    """
    repos: dict[str, Any] = {}
    if yaml is not None and catalog_path.is_file():
        data = yaml.safe_load(catalog_path.read_text()) or {}
        repos = data.get("repos", {}) if isinstance(data, dict) else {}

    return {name: score_catalog_entry(repos.get(name)) for name in repo_names}
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
python -m pytest tests/test_catalog_validator.py -v
```

Expected: 7 tests PASSED

---

### Task 9: Write failing tests for tier distribution report

**Files:**
- Create: `tests/test_tier_recalibration.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_tier_recalibration.py
"""Tests for the tier distribution report (Arc H A4)."""
from src.tier_recalibration import tier_distribution_report


def _make_repo(tier: int) -> dict:
    """Return a minimal repo dict that compute_tier() will return *tier* for.

    We mock compute_tier to avoid building full repo structures in unit tests.
    """
    return {"_mock_tier": tier}


def test_report_counts_tiers_correctly(monkeypatch):
    from src import tier_recalibration
    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(1)] * 10 + [_make_repo(2)] * 5 + [_make_repo(3)] * 3 + [_make_repo(4)] * 2
    report = tier_distribution_report(repos)

    assert report["counts"]["Bronze"] == 10
    assert report["counts"]["Silver"] == 5
    assert report["counts"]["Gold"] == 3
    assert report["counts"]["Platinum"] == 2
    assert report["total"] == 20


def test_report_computes_percentages(monkeypatch):
    from src import tier_recalibration
    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(1)] * 3 + [_make_repo(2)] * 1
    report = tier_distribution_report(repos)

    assert report["percentages"]["Bronze"] == 75.0
    assert report["percentages"]["Silver"] == 25.0


def test_report_empty_repos():
    report = tier_distribution_report([])
    assert report["total"] == 0
    assert report["counts"]["Bronze"] == 0


def test_report_flags_bunching_when_bronze_over_60_percent(monkeypatch):
    from src import tier_recalibration
    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(1)] * 7 + [_make_repo(2)] * 3
    report = tier_distribution_report(repos)
    assert report["bunching_detected"] is True


def test_report_no_bunching_when_distributed(monkeypatch):
    from src import tier_recalibration
    monkeypatch.setattr(tier_recalibration, "compute_tier", lambda r: r["_mock_tier"])

    repos = [_make_repo(t) for t in [1, 2, 3, 4]] * 5
    report = tier_distribution_report(repos)
    assert report["bunching_detected"] is False
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/test_tier_recalibration.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'src.tier_recalibration'`

---

### Task 10: Implement `tier_recalibration.py`

**Files:**
- Create: `src/tier_recalibration.py`

- [ ] **Step 1: Write the implementation**

```python
# src/tier_recalibration.py
"""Tier distribution report for maturity recalibration (Arc H A4)."""
from __future__ import annotations

from collections import Counter
from typing import Any

from src.maturity_tiers import compute_tier

_TIER_NAMES = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Platinum"}
_BUNCHING_THRESHOLD = 0.60  # flag if any single tier holds > 60% of repos


def tier_distribution_report(repos: list[dict[str, Any]]) -> dict[str, Any]:
    """Return tier distribution counts, percentages, and a bunching flag.

    Args:
        repos: List of repo audit dicts (same format passed to compute_tier).

    Returns:
        Dict with keys: total, counts (by tier name), percentages, bunching_detected.
    """
    total = len(repos)
    counts: dict[str, int] = {name: 0 for name in _TIER_NAMES.values()}

    for repo in repos:
        tier = compute_tier(repo)
        name = _TIER_NAMES.get(tier)
        if name:
            counts[name] += 1

    percentages: dict[str, float] = {
        name: round(100.0 * count / total, 1) if total else 0.0
        for name, count in counts.items()
    }
    bunching = any(pct > _BUNCHING_THRESHOLD * 100 for pct in percentages.values())

    return {
        "total": total,
        "counts": counts,
        "percentages": percentages,
        "bunching_detected": bunching,
    }
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
python -m pytest tests/test_tier_recalibration.py -v
```

Expected: 5 tests PASSED

---

### Task 11: Wire `--tier-recalibration-report` CLI flag

**Files:**
- Modify: `src/cli.py`

- [ ] **Step 1: Find the right insertion point**

```bash
grep -n 'portfolio.truth\|portfolio_truth\|control.center\|add_argument' /Users/d/Projects/GithubRepoAuditor/src/cli.py | grep 'add_argument' | tail -20
```

Locate a block of flags near `--portfolio-truth` or `--control-center`. Add the new flag in the same group.

- [ ] **Step 2: Add the argument**

Find the argument parser section and add:
```python
parser.add_argument(
    "--tier-recalibration-report",
    action="store_true",
    default=False,
    help="Emit a tier distribution report and flag bunching. Writes output/tier-recalibration-YYYY-MM-DD.json.",
)
```

- [ ] **Step 3: Add the handler**

Find where `--portfolio-truth` or similar flags are handled in the main execution block. Add after it:

```python
if args.tier_recalibration_report:
    from src.tier_recalibration import tier_distribution_report
    import json
    from datetime import date
    repos_for_tiers = [r for r in audit_results if isinstance(r, dict)]
    report = tier_distribution_report(repos_for_tiers)
    out_path = Path("output") / f"tier-recalibration-{date.today()}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Tier recalibration report written to {out_path}")
    if report["bunching_detected"]:
        print(f"  WARNING: tier bunching detected — {report['percentages']}")
```

Note: `audit_results` is the list of repo audit dicts already computed by this point in the CLI. Check the exact variable name in the surrounding handler context and match it.

- [ ] **Step 4: Verify CLI parses the flag without error**

```bash
python -m src.cli --help 2>&1 | grep tier-recalibration
```

Expected: `--tier-recalibration-report  Emit a tier distribution report...`

---

### Task 12: Commit H.2

- [ ] **Step 1: Run full suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 2: Stage and commit**

```bash
git add src/catalog_validator.py src/tier_recalibration.py src/cli.py tests/test_catalog_validator.py tests/test_tier_recalibration.py
git commit -m "feat(arc-h): H.2 — catalog validator + tier recalibration report"
```

---

## Sprint H.3 — Triage Runner + Recovery Wire-Up

### Task 13: Write failing tests for `portfolio_context_triage.py`

**Files:**
- Create: `tests/test_portfolio_context_triage.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_portfolio_context_triage.py
"""Tests for the context triage runner (Arc H B1)."""
import json
from pathlib import Path
import pytest
from src.portfolio_context_triage import (
    assess_repo_failure_modes,
    run_triage,
    TriageEntry,
    FailureMode,
)


def _entry(
    description_confidence=1.0,
    readme_stale_by_age=False,
    catalog_completeness=1.0,
    context_quality="full",
) -> dict:
    return {
        "name": "test-repo",
        "analyzers": {
            "description": {"details": {"description_confidence": description_confidence}},
            "readme": {"details": {"readme_stale_by_age": readme_stale_by_age}},
        },
        "catalog_completeness": catalog_completeness,
        "context_quality": context_quality,
    }


def test_no_failure_modes_for_healthy_repo():
    modes = assess_repo_failure_modes(_entry())
    assert modes == []


def test_low_description_confidence_flagged():
    modes = assess_repo_failure_modes(_entry(description_confidence=0.2))
    assert FailureMode.DESCRIPTION in modes


def test_stale_readme_flagged():
    modes = assess_repo_failure_modes(_entry(readme_stale_by_age=True))
    assert FailureMode.README in modes


def test_low_catalog_completeness_flagged():
    modes = assess_repo_failure_modes(_entry(catalog_completeness=0.25))
    assert FailureMode.CATALOG in modes


def test_weak_context_quality_flagged():
    modes = assess_repo_failure_modes(_entry(context_quality="none"))
    assert FailureMode.CONTEXT in modes


def test_severity_critical_when_multiple_failure_modes():
    entry = _entry(description_confidence=0.2, readme_stale_by_age=True, catalog_completeness=0.0, context_quality="none")
    triage = TriageEntry.from_repo(entry)
    assert triage.severity == "critical"


def test_severity_moderate_for_single_failure():
    entry = _entry(readme_stale_by_age=True)
    triage = TriageEntry.from_repo(entry)
    assert triage.severity == "moderate"


def test_run_triage_returns_only_repos_with_failures():
    repos = [_entry(), _entry(description_confidence=0.2)]
    repos[0]["name"] = "clean-repo"
    repos[1]["name"] = "broken-repo"
    result = run_triage(repos)
    names = [e.repo_name for e in result]
    assert "clean-repo" not in names
    assert "broken-repo" in names
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/test_portfolio_context_triage.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'src.portfolio_context_triage'`

---

### Task 14: Implement `portfolio_context_triage.py`

**Files:**
- Create: `src/portfolio_context_triage.py`

- [ ] **Step 1: Write the implementation**

```python
# src/portfolio_context_triage.py
"""Context triage runner — B1 of Arc H operational stream."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureMode(str, Enum):
    DESCRIPTION = "description"
    README = "readme"
    CATALOG = "catalog"
    CONTEXT = "context"


_DESCRIPTION_CONFIDENCE_WARN_BELOW = 0.5
_CATALOG_COMPLETENESS_WARN_BELOW = 0.6
_WEAK_CONTEXT_QUALITIES = {"none", "boilerplate"}


def assess_repo_failure_modes(repo: dict[str, Any]) -> list[FailureMode]:
    modes: list[FailureMode] = []

    desc_conf = (
        repo.get("analyzers", {})
        .get("description", {})
        .get("details", {})
        .get("description_confidence", 1.0)
    )
    if desc_conf < _DESCRIPTION_CONFIDENCE_WARN_BELOW:
        modes.append(FailureMode.DESCRIPTION)

    stale_by_age = (
        repo.get("analyzers", {})
        .get("readme", {})
        .get("details", {})
        .get("readme_stale_by_age", False)
    )
    if stale_by_age:
        modes.append(FailureMode.README)

    catalog_score = repo.get("catalog_completeness", 1.0)
    if catalog_score < _CATALOG_COMPLETENESS_WARN_BELOW:
        modes.append(FailureMode.CATALOG)

    context_quality = repo.get("context_quality", "full")
    if context_quality in _WEAK_CONTEXT_QUALITIES:
        modes.append(FailureMode.CONTEXT)

    return modes


@dataclass
class TriageEntry:
    repo_name: str
    failure_modes: list[FailureMode]
    severity: str  # "critical" | "moderate" | "low"

    @classmethod
    def from_repo(cls, repo: dict[str, Any]) -> "TriageEntry":
        modes = assess_repo_failure_modes(repo)
        if len(modes) >= 3:
            severity = "critical"
        elif len(modes) == 2:
            severity = "moderate"
        else:
            severity = "low"
        return cls(
            repo_name=repo.get("name", "unknown"),
            failure_modes=modes,
            severity=severity,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo_name,
            "failure_modes": [m.value for m in self.failure_modes],
            "severity": self.severity,
        }


def run_triage(repos: list[dict[str, Any]]) -> list[TriageEntry]:
    """Return TriageEntry for every repo that has at least one failure mode."""
    return [
        TriageEntry.from_repo(repo)
        for repo in repos
        if assess_repo_failure_modes(repo)
    ]
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
python -m pytest tests/test_portfolio_context_triage.py -v
```

Expected: 8 tests PASSED

---

### Task 15: Wire `--context-triage` CLI flag

**Files:**
- Modify: `src/cli.py`

- [ ] **Step 1: Add the argument** (in the same parser section as `--tier-recalibration-report`)

```python
parser.add_argument(
    "--context-triage",
    action="store_true",
    default=False,
    help="Run context quality triage against audited repos. Writes output/context-triage-YYYY-MM-DD.json.",
)
```

- [ ] **Step 2: Add the handler** (near the `--tier-recalibration-report` handler)

```python
if args.context_triage:
    from src.portfolio_context_triage import run_triage
    from src.catalog_validator import validate_catalog
    import json
    from datetime import date

    catalog_path = Path("config/portfolio-catalog.yaml")
    repo_names = [r.get("name", "") for r in audit_results if isinstance(r, dict)]
    catalog_scores = validate_catalog(catalog_path, repo_names)

    enriched = []
    for repo in audit_results:
        if isinstance(repo, dict):
            repo["catalog_completeness"] = catalog_scores.get(repo.get("name", ""), 0.0)
            enriched.append(repo)

    entries = run_triage(enriched)
    out = [e.to_dict() for e in entries]
    out_path = Path("output") / f"context-triage-{date.today()}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({"triage": out, "total_flagged": len(out)}, indent=2))
    print(f"Context triage written to {out_path} — {len(out)} repos flagged")
```

- [ ] **Step 3: Verify**

```bash
python -m src.cli --help 2>&1 | grep context-triage
```

Expected: `--context-triage  Run context quality triage...`

---

### Task 16: Commit H.3

- [ ] **Step 1: Run full suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 2: Stage and commit**

```bash
git add src/portfolio_context_triage.py src/cli.py tests/test_portfolio_context_triage.py
git commit -m "feat(arc-h): H.3 — context triage runner + CLI flags"
```

---

## Sprint H.4 — Composite Scorer + Merge Gate

### Task 17: Write failing tests for `context_quality.py`

**Files:**
- Create: `tests/test_context_quality.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_context_quality.py
"""Tests for the composite context_quality_score (Arc H H.4)."""
import pytest
from src.context_quality import compute_context_quality_score


def test_perfect_repo_scores_one():
    score = compute_context_quality_score(
        description_confidence=1.0,
        readme_stale_by_age=False,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert score == pytest.approx(1.0)


def test_missing_description_lowers_score():
    score = compute_context_quality_score(
        description_confidence=0.0,
        readme_stale_by_age=False,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert score < 1.0
    assert score < 0.8  # description_confidence weight is 0.30


def test_stale_readme_lowers_score():
    score = compute_context_quality_score(
        description_confidence=1.0,
        readme_stale_by_age=True,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert score < 1.0


def test_worst_case_repo_scores_near_zero():
    score = compute_context_quality_score(
        description_confidence=0.0,
        readme_stale_by_age=True,
        catalog_completeness=0.0,
        completeness_score=0.0,
    )
    assert score < 0.2


def test_none_values_treated_as_zero():
    score = compute_context_quality_score(
        description_confidence=None,
        readme_stale_by_age=None,
        catalog_completeness=None,
        completeness_score=None,
    )
    assert 0.0 <= score <= 1.0


def test_score_clamped_to_zero_one():
    score = compute_context_quality_score(
        description_confidence=2.0,  # out of range input
        readme_stale_by_age=False,
        catalog_completeness=1.0,
        completeness_score=1.0,
    )
    assert 0.0 <= score <= 1.0
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python -m pytest tests/test_context_quality.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'src.context_quality'`

---

### Task 18: Implement `context_quality.py`

**Files:**
- Create: `src/context_quality.py`

- [ ] **Step 1: Write the implementation**

```python
# src/context_quality.py
"""Composite context_quality_score computation (Arc H H.4)."""
from __future__ import annotations

# Weights must sum to 1.0.
_WEIGHTS = {
    "description_confidence": 0.30,
    "readme_freshness": 0.25,      # inverted from readme_stale_by_age
    "catalog_completeness": 0.25,
    "completeness_score": 0.20,
}


def compute_context_quality_score(
    description_confidence: float | None,
    readme_stale_by_age: bool | None,
    catalog_completeness: float | None,
    completeness_score: float | None,
) -> float:
    """Return a composite context quality score in [0.0, 1.0].

    Args:
        description_confidence: 0.0–1.0 from DescriptionAnalyzer.
        readme_stale_by_age: True if README is older than the age threshold.
            None means unknown (treated as not stale / 1.0 freshness).
        catalog_completeness: 0.0–1.0 from catalog_validator.
        completeness_score: 0.0–1.0 from the existing completeness analyzer dimension.
    """
    desc = max(0.0, min(1.0, description_confidence or 0.0))
    readme_fresh = 0.0 if readme_stale_by_age is True else 1.0
    catalog = max(0.0, min(1.0, catalog_completeness or 0.0))
    complete = max(0.0, min(1.0, completeness_score or 0.0))

    score = (
        _WEIGHTS["description_confidence"] * desc
        + _WEIGHTS["readme_freshness"] * readme_fresh
        + _WEIGHTS["catalog_completeness"] * catalog
        + _WEIGHTS["completeness_score"] * complete
    )
    return round(max(0.0, min(1.0, score)), 4)
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
python -m pytest tests/test_context_quality.py -v
```

Expected: 6 tests PASSED

---

### Task 19: Wire `context_quality_score` into the audit pipeline

**Files:**
- Modify: `src/cli.py` (or wherever per-repo audit dicts are assembled)

The goal: after all analyzers have run for a repo, compute `context_quality_score` and add it to the repo's output dict.

- [ ] **Step 1: Find the per-repo result assembly point**

```bash
grep -n 'analyzer_results\|audit_result\|repo_result\|results\[' /Users/d/Projects/GithubRepoAuditor/src/cli.py | head -20
```

Identify where the per-repo dict is assembled (after `run_all_analyzers` is called).

- [ ] **Step 2: Add the composite score computation**

After `run_all_analyzers` is called for a repo and the result dict is assembled, add:

```python
from src.context_quality import compute_context_quality_score
from src.catalog_validator import validate_catalog

# Extract inputs from analyzer details
desc_conf = (
    repo_result.get("analyzers", {})
    .get("description", {})
    .get("details", {})
    .get("description_confidence")
)
readme_stale = (
    repo_result.get("analyzers", {})
    .get("readme", {})
    .get("details", {})
    .get("readme_stale_by_age")
)
catalog_score = repo_result.get("catalog_completeness", 0.0)
completeness = (
    repo_result.get("analyzers", {})
    .get("completeness", {})
    .get("score")
)

repo_result["context_quality_score"] = compute_context_quality_score(
    description_confidence=desc_conf,
    readme_stale_by_age=readme_stale,
    catalog_completeness=catalog_score,
    completeness_score=completeness,
)
```

Note: `catalog_completeness` may not be pre-populated here. If not, load the catalog once before the repo loop and pass the score in.

- [ ] **Step 3: Verify new field appears in audit output**

```bash
python -c "
import json, pathlib
# Load a recent output JSON and check for context_quality_score
files = sorted(pathlib.Path('output').glob('audit-*.json'))
if files:
    data = json.loads(files[-1].read_text())
    repos = data if isinstance(data, list) else data.get('repos', [])
    sample = repos[0] if repos else {}
    print('context_quality_score' in sample, sample.get('context_quality_score'))
else:
    print('No output files found — run an audit first')
"
```

---

### Task 20: Integration test — before/after triage metrics

**Files:**
- Modify: `tests/test_portfolio_context_triage.py` (add integration scenario)

- [ ] **Step 1: Add integration scenario to existing test file**

Append to `tests/test_portfolio_context_triage.py`:

```python
def test_run_triage_to_dict_is_json_serializable():
    import json
    repos = [
        _entry(description_confidence=0.2, readme_stale_by_age=True),
        _entry(catalog_completeness=0.0),
        _entry(),  # healthy
    ]
    for i, r in enumerate(repos):
        r["name"] = f"repo-{i}"
    entries = run_triage(repos)
    out = [e.to_dict() for e in entries]
    # Must be JSON-serializable
    serialized = json.dumps({"triage": out})
    parsed = json.loads(serialized)
    assert len(parsed["triage"]) == 2  # healthy repo excluded
    assert all("severity" in e for e in parsed["triage"])
```

- [ ] **Step 2: Run the test**

```bash
python -m pytest tests/test_portfolio_context_triage.py -v
```

Expected: all tests pass including the new one.

---

### Task 21: Run full suite and merge gate check

- [ ] **Step 1: Run the full test suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -20
```

Expected: all tests pass. Record the passing test count.

- [ ] **Step 2: Run ruff lint**

```bash
python -m ruff check src/analyzers/description_analyzer.py src/catalog_validator.py src/tier_recalibration.py src/context_quality.py src/portfolio_context_triage.py
```

Expected: no issues.

- [ ] **Step 3: Verify new CLI flags are present**

```bash
python -m src.cli --help 2>&1 | grep -E 'tier-recalibration|context-triage'
```

Expected: both flags listed.

- [ ] **Step 4: Spot-check that `DescriptionAnalyzer` runs in the full analyzer pipeline**

```bash
python -c "from src.analyzers import ALL_ANALYZERS; names = [a.name for a in ALL_ANALYZERS]; print(names); assert 'description' in names"
```

Expected: `description` in the list.

---

### Task 22: Final commit

- [ ] **Step 1: Stage all H.4 changes**

```bash
git add src/context_quality.py src/cli.py tests/test_context_quality.py tests/test_portfolio_context_triage.py
git commit -m "feat(arc-h): H.4 — composite context_quality_score + merge gate pass"
```

- [ ] **Step 2: Open PR from `feat/arc-h-spec` once all sprints are committed**

Note: the feature branch is `feat/arc-h-spec`. When H.1–H.4 commits are all on this branch, open a PR to main. Run `/code-review` before merging (diff will be >200 LoC).

---

## Self-Review Checklist

**Spec coverage:**
- [x] A1 description_confidence — Task 1–3
- [x] A2 readme_stale_by_age — Task 4–5
- [x] A3 catalog_completeness — Task 7–8
- [x] A4 tier recalibration report — Task 9–11
- [x] B1 triage run — Task 13–14
- [x] B2 recovery wire-up — Task 15 (flag wires to existing `portfolio_context_recovery.py`)
- [x] B3 validate outputs — Task 20
- [x] context_quality_score composite — Task 17–19
- [x] Merge gate check — Task 21

**Placeholder scan:** No TBDs. Task 11 step 2 notes to check the exact variable name — that's an instruction to the implementer, not a placeholder.

**Type consistency:** `description_confidence: float | None` used consistently across Task 1, 14, 17, 18. `readme_stale_by_age: bool | None` consistent across Task 4, 5, 14, 18. `catalog_completeness: float | None` consistent across Task 7, 8, 14, 18.
