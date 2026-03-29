# CI Initiative Completion Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Close out the CI coverage initiative by shipping the analyzer bug fixes with proper test coverage, clearing the personal-ops false-positive, re-auditing 13 repos with corrected analyzer code, and formally documenting the 10 skeleton repos as out-of-scope.

**Architecture:** Four sequential tasks on the existing `fix/analyzer-bugs` branch. Tasks 1–2 land code changes (tests + PR merge); Tasks 3–4 are audit-run + documentation steps that require the merged fixes to be in effect.

**Tech Stack:** Python 3.11, pytest, GitHub CLI (`gh`), `python -m src` audit runner

---

## Current State

- Branch: `fix/analyzer-bugs` — rebased on current `main` (`3c41c2b`, post-PR #14), one commit ahead
- Three bugs already fixed: `src/analyzers/testing.py`, `src/analyzers/cicd.py`, `src/cloner.py`
- No regression tests written for those fixes yet
- Audit report: `output/audit-report-saagpatel-2026-03-29.json`
- `personal-ops` falsely flagged `no-ci` — it has had CI on `main` the whole time
- 12 xctest repos scored with `test_file_count=0` under the old (broken) analyzer

---

## Task 1: Add regression tests for the three analyzer fixes, then ship the branch

**Files:**
- Modify: `tests/test_analyzers.py` (add to existing `TestTestingAnalyzer`, `TestCicdAnalyzer` classes; add `TestCloneWorkspace`)
- Modify: `tests/conftest.py` (add `xctest_repo` fixture)

---

### Step 1: Add an `xctest_repo` fixture to `tests/conftest.py`

The existing `swift_repo` fixture already has a `SwiftAppTests.swift` file but is used for structure tests. Add a separate `xctest_repo` fixture that mirrors the pattern that tripped up the bug: test files using the `*Tests.swift` naming convention in a `Tests/` subdirectory (SPM layout, which is what SnippetLibrary uses).

Append to the bottom of `tests/conftest.py`:

```python
@pytest.fixture
def xctest_repo(tmp_path: Path) -> Path:
    """Swift repo with XCTest files in SPM-style Tests/ directory."""
    repo = tmp_path / "xctest-repo"
    repo.mkdir()
    (repo / "Package.swift").write_text(
        "// swift-tools-version:5.9\nimport PackageDescription\n"
        "let package = Package(name: \"MyLib\")\n"
    )
    tests = repo / "Tests" / "MyLibTests"
    tests.mkdir(parents=True)
    (tests / "MyLibTests.swift").write_text(
        "import XCTest\n@testable import MyLib\n\n"
        "final class MyLibTests: XCTestCase {\n"
        "    func testExample() { XCTAssertTrue(true) }\n}\n"
    )
    (tests / "HelperTest.swift").write_text(
        "import XCTest\nclass HelperTest: XCTestCase {}\n"
    )
    return repo
```

### Step 2: Run current tests to confirm baseline

```bash
python -m pytest tests/test_analyzers.py -v
```

Expected: all existing tests pass.

---

### Step 3: Add tests for Fix 1 — Swift test file counting

In `tests/test_analyzers.py`, add three test methods to the `TestTestingAnalyzer` class:

```python
def test_xctest_files_are_counted(self, xctest_repo, sample_metadata):
    """*Tests.swift and *Test.swift files must appear in test_file_count."""
    result = TestingAnalyzer().analyze(xctest_repo, sample_metadata)
    assert result.details["test_file_count"] == 2
    assert result.score == 1.0  # dirs(0.4) + framework(0.3) + files>0(0.3)

def test_xctest_framework_detected_with_files(self, xctest_repo, sample_metadata):
    result = TestingAnalyzer().analyze(xctest_repo, sample_metadata)
    assert result.details["framework"] == "xctest"
    assert any("Test framework: xctest" in f for f in result.findings)

def test_empty_xctest_dir_still_zero_count(self, tmp_path, sample_metadata):
    """Test dir exists + xctest framework marker, but no actual .swift test files."""
    repo = tmp_path / "empty-xctest"
    repo.mkdir()
    tests = repo / "XcodeTests"
    tests.mkdir()
    # xctest framework detection requires a *Tests.swift file; without one,
    # framework is None and file count is 0
    result = TestingAnalyzer().analyze(repo, sample_metadata)
    assert result.details["test_file_count"] == 0
    assert result.details["framework"] is None
```

### Step 4: Run new tests — they must all pass

```bash
python -m pytest tests/test_analyzers.py::TestTestingAnalyzer -v
```

Expected: all 5 tests pass (2 old + 3 new). If any fail, the fix in `testing.py` needs revisiting.

---

### Step 5: Add tests for Fix 2 — Swift build system detection in CI analyzer

Add to the `TestCicdAnalyzer` class in `tests/test_analyzers.py`:

```python
def test_package_swift_scores_build_scripts(self, tmp_path, sample_metadata):
    """Package.swift (SPM) should contribute 0.2 to cicd score via build scripts."""
    repo = tmp_path / "spm-repo"
    repo.mkdir()
    (repo / "Package.swift").write_text("// swift-tools-version:5.9\n")
    result = CicdAnalyzer().analyze(repo, sample_metadata)
    assert result.score >= 0.2
    assert any("build" in f.lower() or "script" in f.lower() for f in result.findings)

def test_xcodegen_project_yml_scores_build_scripts(self, tmp_path, sample_metadata):
    """project.yml (XcodeGen) should contribute 0.2 to cicd score."""
    repo = tmp_path / "xcodegen-repo"
    repo.mkdir()
    (repo / "project.yml").write_text("name: MyApp\ntargets:\n  MyApp:\n    type: application\n")
    result = CicdAnalyzer().analyze(repo, sample_metadata)
    assert result.score >= 0.2

def test_podfile_scores_build_scripts(self, tmp_path, sample_metadata):
    """Podfile (CocoaPods) should contribute 0.2 to cicd score."""
    repo = tmp_path / "pods-repo"
    repo.mkdir()
    (repo / "Podfile").write_text("target 'MyApp' do\n  use_frameworks!\nend\n")
    result = CicdAnalyzer().analyze(repo, sample_metadata)
    assert result.score >= 0.2
```

### Step 6: Run new CI tests — all must pass

```bash
python -m pytest tests/test_analyzers.py::TestCicdAnalyzer -v
```

Expected: all 5 pass (2 old + 3 new).

---

### Step 7: Add test for Fix 3 — clone workspace isolation

Add a new class to `tests/test_analyzers.py`:

```python
class TestCloneWorkspace:
    def test_workspace_uses_unique_temp_dir(self, monkeypatch):
        """Two concurrent clone_workspace calls must use different directories."""
        import tempfile
        from src.cloner import clone_workspace
        from src.models import RepoMetadata
        import inspect

        # Verify implementation uses TemporaryDirectory (not a fixed path)
        src = inspect.getsource(clone_workspace)
        assert "TemporaryDirectory" in src, "clone_workspace must use tempfile.TemporaryDirectory"
        assert "/tmp/audit-repos" not in src, "clone_workspace must not use hardcoded path"

    def test_cleanup_is_automatic(self, monkeypatch):
        """The temp dir created by clone_workspace must not persist after the context exits."""
        import tempfile
        from unittest.mock import patch, MagicMock
        from src.cloner import clone_workspace
        from src.models import RepoMetadata

        captured_dirs = []

        original_init = tempfile.TemporaryDirectory.__init__

        # Capture what directory gets created, then verify it's cleaned up
        # We do this by checking the TemporaryDirectory is used as a context manager
        from src.cloner import clone_workspace
        import inspect
        src = inspect.getsource(clone_workspace)
        # "with tempfile.TemporaryDirectory" proves it's used as a context manager (auto-cleanup)
        assert "with tempfile.TemporaryDirectory" in src
```

### Step 8: Run the new clone test

```bash
python -m pytest tests/test_analyzers.py::TestCloneWorkspace -v
```

Expected: both pass.

---

### Step 9: Run the full suite to confirm nothing regressed

```bash
python -m pytest tests/ -q
```

Expected: `249 passed` → `257 passed` (8 new tests added).

---

### Step 10: Commit the tests

```bash
git add tests/test_analyzers.py tests/conftest.py
git commit -m "test: add regression tests for xctest counting, Swift CI detection, and clone isolation"
```

---

### Step 11: Push branch and open PR

```bash
git push -u origin fix/analyzer-bugs
gh pr create \
  --title "fix: analyzer bugs — xctest counting, Swift CI detection, clone isolation" \
  --body "$(cat <<'EOF'
## What

Three bug fixes found during the CI coverage initiative, now with regression tests.

### Fix 1 — `testing.py`: XCTest files not counted
`*Tests.swift` and `*Test.swift` were missing from `TEST_PATTERNS`. The framework detector used these globs but the file counter did not. Swift repos with tests were capped at 0.7 instead of 1.0.

### Fix 2 — `cicd.py`: Swift build infrastructure invisible
`_has_build_scripts()` had no awareness of Swift build systems. Added `Package.swift` (SPM), `Podfile` (CocoaPods), `project.yml`/`project.yaml` (XcodeGen). XcodeGen repos (no committed `.xcodeproj`) received 0 CI score even when a full build system was present.

### Fix 3 — `cloner.py`: Shared `/tmp/audit-repos` causes cross-run collisions
Replaced hardcoded `CLONE_DIR = Path(\"/tmp/audit-repos\")` with `tempfile.TemporaryDirectory` per session. Cleanup is now automatic via context manager.

## Tests
8 new regression tests in `tests/test_analyzers.py` and `tests/conftest.py`.
All 257 tests pass.
EOF
)"
```

### Step 12: Merge the PR

```bash
# Get the PR number from the output of the previous command, then:
gh pr merge <PR_NUMBER> --merge --delete-branch
```

---

## Task 2: Clear the personal-ops false-positive `no-ci` flag

**Files:**
- Read/write: `output/audit-report-saagpatel-2026-03-29.json` (updated by audit runner)

personal-ops has had a working CI workflow on `main` since before the original full-portfolio audit — it uses Node's built-in `--test` runner, which leaves no config file for the framework detector to find. The `no-ci` flag persists because personal-ops was never re-audited after the original run.

**This task requires Task 1 to be complete** (merged to main) so the fixed `cloner.py` is in effect.

---

### Step 1: Re-audit personal-ops

```bash
python -m src saagpatel --repos personal-ops
```

Expected output includes:
```
✓ Targeted audit: 1 new/updated + 102 existing = 103 total
```

### Step 2: Verify `no-ci` flag is cleared

```bash
python3 -c "
import json
with open('output/audit-report-saagpatel-2026-03-29.json') as f:
    data = json.load(f)
for r in data['audits']:
    if r['metadata']['name'] == 'personal-ops':
        cicd = next(a for a in r['analyzer_results'] if a['dimension']=='cicd')
        print(f\"cicd score: {cicd['score']}\")
        print(f\"flags: {r['flags']}\")
        print(f\"no-ci cleared: {'no-ci' not in r['flags']}\")
"
```

Expected:
```
cicd score: 0.5
flags: [...]   ← no 'no-ci' in the list
no-ci cleared: True
```

If `cicd score` is still 0.0, the workflow file might not be at the path the analyzer expects. Inspect with:
```bash
gh api "repos/saagpatel/personal-ops/git/trees/main?recursive=1" \
  --jq '.tree[] | select(.path | contains(".github")) | .path'
```

---

## Task 3: Re-audit 12 xctest repos with fixed analyzer

**Files:**
- Read/write: `output/audit-report-saagpatel-2026-03-29.json`

These 12 repos were audited under the broken `testing.py` which couldn't count `*Tests.swift` files. Re-running will either confirm the test dirs are genuinely empty (no score change) or reveal test files that were previously invisible (score jumps from 0.3 → 1.0).

**This task requires Task 1 to be complete.**

Repos: Chromafield, SnippetLibrary, Calibrate, Cartograph, Conductor, Liminal, Nocturne, Redact, RoomTone, seismoscope, TideEngine, Wavelength

---

### Step 1: Re-audit all 12 in one pass

```bash
python -m src saagpatel --repos \
  Chromafield SnippetLibrary Calibrate Cartograph Conductor \
  Liminal Nocturne Redact RoomTone seismoscope TideEngine Wavelength
```

Expected: `✓ Targeted audit: 12 new/updated + 91 existing = 103 total`

### Step 2: Print before/after comparison

```bash
python3 << 'EOF'
import json
with open('output/audit-report-saagpatel-2026-03-29.json') as f:
    data = json.load(f)

targets = ['Chromafield','SnippetLibrary','Calibrate','Cartograph','Conductor',
           'Liminal','Nocturne','Redact','RoomTone','seismoscope','TideEngine','Wavelength']

print(f"{'Repo':20} {'Tier':12} {'Test':5} {'Files':6} {'CI':5}")
print("-" * 55)
for r in sorted(data['audits'], key=lambda x: x['metadata']['name']):
    if r['metadata']['name'] in targets:
        t = next(a for a in r['analyzer_results'] if a['dimension']=='testing')
        c = next(a for a in r['analyzer_results'] if a['dimension']=='cicd')
        files = t.get('details', {}).get('test_file_count', '?')
        print(f"{r['metadata']['name']:20} {r['completeness_tier']:12} {t['score']:.1f}  {str(files):6} {c['score']:.1f}")
EOF
```

### Step 3: Interpret results

- **Score unchanged at 0.3** → test dir is empty, no actual `.swift` test files committed. Expected for most of these repos (they were "skeleton test dirs"). No action needed.
- **Score jumped to 0.7 or 1.0** → the fixed analyzer found actual test files that were previously invisible. Note which repos improved — these are candidates for test-quality work later.
- **SnippetLibrary specifically** should jump to 1.0: the agent found 5 real test files in `Tests/SnippetLibraryTests/` during the CI workflow work.

---

## Task 4: Document skeleton repos as out of scope

**Files:**
- Create: `docs/ci-coverage-initiative.md`

This is a lightweight audit trail document, not code. It captures the scope decision so future sessions don't re-investigate the same 10 repos.

---

### Step 1: Create the document

Create `docs/ci-coverage-initiative.md`:

```markdown
# CI Coverage Initiative — 2026-03-29

## Summary

Added GitHub Actions CI workflows to **18 of 29** repos that had zero CI/CD.
One additional repo (personal-ops) already had CI but was falsely flagged.

## Repos with CI added

| Repo | Language | Workflow type |
|------|----------|---------------|
| GPT_RAG | Python | pip + pytest |
| RedditSentimentAnalyzer | Python | pip + pytest |
| JSMTicketAnalyticsExport | Python | pip + pytest |
| NetworkMapper | Python | pip + pytest (backend/) |
| SnippetLibrary | Swift/SPM | swift test |
| GhostRoutes | Swift/XcodeGen | xcodegen + xcodebuild test |
| Terroir | Swift/Xcode | xcodebuild test |
| Calibrate | Swift/Xcode | xcodebuild build |
| Cartograph | Swift/XcodeGen | xcodegen + xcodebuild build |
| Chromafield | Swift/Xcode | xcodebuild build |
| Conductor | Swift/Xcode | xcodebuild build |
| Liminal | Swift/Xcode | xcodebuild build |
| Nocturne | Swift/XcodeGen | xcodegen + xcodebuild build |
| Redact | Swift/XcodeGen | xcodegen + xcodebuild build |
| RoomTone | Swift/XcodeGen | xcodegen + xcodebuild build |
| seismoscope | Swift/Xcode | xcodebuild build |
| TideEngine | Swift/Xcode | xcodebuild build |
| Wavelength | Swift/XcodeGen | xcodegen + xcodebuild build |

## Skeleton repos — explicitly out of scope

These 10 repos were audited and intentionally skipped. They have more fundamental
gaps (missing README, minimal or placeholder code) where CI is not the priority.

| Repo | Language | Reason skipped |
|------|----------|----------------|
| Afterimage | Swift | skeleton tier — no substantive code yet |
| app | Swift | skeleton tier — unnamed placeholder repo |
| job-search-2026 | Unknown | skeleton tier — no code |
| LifeCadenceLedger | TypeScript | skeleton tier — no code |
| PageDiffBookmark | JavaScript | skeleton tier — no code |
| PhantomFrequencies | GDScript | skeleton tier — Godot project stub |
| portfolio-actuation-sandbox | Unknown | skeleton tier — sandbox/scratch repo |
| Recall | GDScript | skeleton tier — Godot project stub |
| SignalDecay | GDScript | skeleton tier — Godot project stub |
| SynthWave | Unknown | skeleton tier — no code |

**Decision:** Do not add CI to skeleton-tier repos. If any graduate to wip or
functional tier, re-evaluate at that time.

## Analyzer bugs fixed

Three bugs discovered during this work:

1. **`src/analyzers/testing.py`** — `*Tests.swift` / `*Test.swift` missing from
   `TEST_PATTERNS`. XCTest file count was always 0; fixed in PR #XX.

2. **`src/analyzers/cicd.py`** — `Package.swift`, `Podfile`, `project.yml`/`project.yaml`
   not in `_has_build_scripts()`. XcodeGen repos had no build score; fixed in PR #XX.

3. **`src/cloner.py`** — hardcoded `/tmp/audit-repos` shared across sessions.
   Replaced with `tempfile.TemporaryDirectory`; fixed in PR #XX.
```

### Step 2: Commit

```bash
git add docs/ci-coverage-initiative.md
git commit -m "docs: record CI initiative scope, decisions, and analyzer fixes"
```

### Step 3: Push to main (this is a docs-only commit on main after the fix PR is merged)

```bash
git push origin main
```

---

## Verification Checklist

After all four tasks are complete, run this check:

```bash
python3 << 'EOF'
import json
with open('output/audit-report-saagpatel-2026-03-29.json') as f:
    data = json.load(f)

no_ci = [r for r in data['audits'] if 'no-ci' in r.get('flags', [])]
print(f"Repos still flagged no-ci: {len(no_ci)}")
for r in no_ci:
    print(f"  {r['completeness_tier']:12} {r['metadata']['name']}")

print()
snippet = next(r for r in data['audits'] if r['metadata']['name'] == 'SnippetLibrary')
t = next(a for a in snippet['analyzer_results'] if a['dimension'] == 'testing')
print(f"SnippetLibrary testing score: {t['score']} (expect 1.0)")
print(f"SnippetLibrary test file count: {t['details']['test_file_count']} (expect 5)")
EOF
```

Expected final state:
- `no-ci` repos: 10 (all skeleton tier — acceptable and documented)
- `SnippetLibrary` testing score: 1.0, file count: 5
- `fix/analyzer-bugs` PR merged and branch deleted
- `docs/ci-coverage-initiative.md` committed to main
