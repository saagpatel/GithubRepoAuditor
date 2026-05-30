# Run-Instructions External Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Note:** Tasks 7–8 (build + run the `Workflow`) must run in the main session, since only it can call the `Workflow` tool.

**Goal:** Independently re-check the snapshot's `run_instructions_present` claim against on-disk ground truth across a stratified pilot of ~19 repos, and produce a discrepancy report.

**Architecture:** A deterministic, read-only Python pre-step (`src/run_instructions_audit.py`, TDD'd) selects the pilot and computes per-repo metadata + a live `tool_today` recompute, emitting compact JSON. A `Workflow` (`scripts/run-instructions-audit.workflow.js`) fans out one Haiku subagent per repo to read the files and judge (blind to the tool's answer), tallies buckets in deterministic JS, and a single Sonnet call writes the markdown report.

**Tech Stack:** Python 3.11+ (pytest), the `Workflow` tool (JS orchestration, Haiku verifiers, Sonnet synthesis), `ctx_execute` to run the pre-step.

**Spec:** `docs/plans/2026-05-29-run-instructions-external-audit.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/run_instructions_audit.py` (create) | Stage 0 pilot selection + Stage 1 evidence prep + Stage 3 bucket logic (pure fns reused by the workflow's JS mirror). Read-only. |
| `tests/test_run_instructions_audit.py` (create) | Unit tests for every pure fn + tmp_path tests for the IO fns. |
| `scripts/run-instructions-audit.workflow.js` (create) | Stage 2 verifier fan-out + Stage 3 JS tally + Stage 4 synthesis. |
| `output/run-instructions-audit-2026-05-29.md` (generated) | The report. Gitignored. |

**Bucket / drift-bucket logic is defined once in Python and mirrored in the workflow JS.** The Python copy is the tested source of truth; the JS copy is a 6-line transcription verified against it in Task 7.

---

## Task 1: Module scaffold + `is_fork_junk` + `assign_bucket` (Stage 3 truth table)

**Files:**
- Create: `src/run_instructions_audit.py`
- Test: `tests/test_run_instructions_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_instructions_audit.py
from src.run_instructions_audit import assign_bucket, is_fork_junk


def test_is_fork_junk_flags_known_patterns():
    assert is_fork_junk("AssistSupport-openssl-cve-2026-42327")
    assert is_fork_junk("BrowserHistoryVisualizer-security-fix")
    assert is_fork_junk("ApplyKit-private-history-backup-20260517.bundle")
    assert not is_fork_junk("Fun:GamePrjs/BattleGrid")
    assert not is_fork_junk("mcpforge")


def test_assign_bucket_truth_table():
    # agreement
    assert assign_bucket(True, True, True) == "agree_present"
    assert assign_bucket(False, False, False) == "agree_absent"
    # false negatives (tool said absent, verifier found it)
    assert assign_bucket(False, True, True) == "fn_alias_gap"      # evidence in primary file
    assert assign_bucket(False, True, False) == "fn_blind_spot"    # evidence only in README/other
    # false positive (tool over-claimed)
    assert assign_bucket(True, False, False) == "fp_overclaim"
    assert assign_bucket(True, False, True) == "fp_overclaim"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.run_instructions_audit'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/run_instructions_audit.py
"""External audit of the snapshot's run_instructions_present claim (pre-step).

Stage 0 (stratified pilot selection) + Stage 1 (evidence prep + live tool_today
recompute) run here as a deterministic, read-only pre-step. The compact JSON this
emits is consumed as `args` by scripts/run-instructions-audit.workflow.js, whose
Haiku subagents read the repo files and judge. Never writes repos/snapshot/git.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from src.portfolio_context_contract import (
    analyze_project_context,
    choose_primary_context_file,
)
from src.portfolio_truth_sources import _collect_context_files

FORK_JUNK_PATTERNS = (r"-security-fix", r"-cve-", r"-backup-", r"\.bundle$", r"-openssl-")


def is_fork_junk(path: str) -> bool:
    return any(re.search(pattern, path) for pattern in FORK_JUNK_PATTERNS)


def assign_bucket(tool_today: bool, verdict: bool, evidence_in_primary: bool) -> str:
    if tool_today == verdict:
        return "agree_present" if verdict else "agree_absent"
    if verdict and not tool_today:
        return "fn_alias_gap" if evidence_in_primary else "fn_blind_spot"
    return "fp_overclaim"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/run_instructions_audit.py tests/test_run_instructions_audit.py
git commit -m "feat: add run-instructions audit pre-step scaffold + bucket logic"
```

---

## Task 2: `assign_drift_bucket` (snapshot-vs-today drift)

**Files:**
- Modify: `src/run_instructions_audit.py`
- Test: `tests/test_run_instructions_audit.py`

- [ ] **Step 1: Write the failing test**

```python
from src.run_instructions_audit import assign_drift_bucket


def test_assign_drift_bucket():
    # snapshot still matches today's recompute → no field drift
    assert assign_drift_bucket(True, True, True) == "claim_same"
    assert assign_drift_bucket(False, False, False) == "claim_same"
    # field value changed AND repo has commits since snapshot → explained by drift
    assert assign_drift_bucket(False, True, True) == "claim_changed_drift"
    # field value changed with NO commits since snapshot → unexplained (snapshot was wrong)
    assert assign_drift_bucket(False, True, False) == "claim_changed_nodrift"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_instructions_audit.py::test_assign_drift_bucket -q`
Expected: FAIL — `ImportError: cannot import name 'assign_drift_bucket'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/run_instructions_audit.py` after `assign_bucket`:

```python
def assign_drift_bucket(snapshot_claim: bool, tool_today: bool, repo_drifted: bool) -> str:
    if snapshot_claim == tool_today:
        return "claim_same"
    return "claim_changed_drift" if repo_drifted else "claim_changed_nodrift"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/run_instructions_audit.py tests/test_run_instructions_audit.py
git commit -m "feat: add drift bucket logic to run-instructions audit"
```

---

## Task 3: `select_pilot` (Stage 0 — stratified, deterministic)

**Files:**
- Modify: `src/run_instructions_audit.py`
- Test: `tests/test_run_instructions_audit.py`

- [ ] **Step 1: Write the failing test**

```python
from src.run_instructions_audit import select_pilot


def _project(key, quality, *, status="active", path=None):
    return {
        "identity": {"project_key": key, "path": path or key, "display_name": key.split("/")[-1]},
        "derived": {
            "registry_status": status,
            "context_quality": quality,
            "context_files": ["CLAUDE.md"],
            "run_instructions_present": False,
        },
    }


def test_select_pilot_stratifies_sorts_and_filters():
    projects = (
        [_project(f"b{i}", "boilerplate") for i in range(6)]
        + [_project("n1", "none"), _project("n2", "none")]
        + [_project("arch", "full", status="archived")]
        + [_project("junk-security-fix", "full")]
        + [_project("z-full", "full"), _project("a-full", "full")]
    )
    selected = select_pilot(projects, per_tier={"none": 3, "boilerplate": 4, "full": 4})
    keys = [p["identity"]["project_key"] for p in selected]

    # archived + fork-junk excluded
    assert "arch" not in keys and "junk-security-fix" not in keys
    # boilerplate capped at 4 of 6
    assert sum(k.startswith("b") for k in keys) == 4
    # full sorted by project_key → a-full before z-full
    assert keys.index("a-full") < keys.index("z-full")
    # both 'none' present (only 2 available, asked for 3)
    assert {"n1", "n2"} <= set(keys)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_instructions_audit.py::test_select_pilot_stratifies_sorts_and_filters -q`
Expected: FAIL — `ImportError: cannot import name 'select_pilot'`

- [ ] **Step 3: Write minimal implementation**

Add the `DEFAULT_PER_TIER` constant near the top (under `FORK_JUNK_PATTERNS`):

```python
DEFAULT_PER_TIER = {
    "none": 3,
    "boilerplate": 4,
    "minimum-viable": 4,
    "standard": 4,
    "full": 4,
}
```

Add the function:

```python
def select_pilot(projects: list[dict], *, per_tier: dict[str, int] = DEFAULT_PER_TIER) -> list[dict]:
    eligible = [
        p
        for p in projects
        if p["derived"]["registry_status"] != "archived"
        and not is_fork_junk(p["identity"]["path"])
    ]
    selected: list[dict] = []
    for tier, count in per_tier.items():
        tier_projects = sorted(
            (p for p in eligible if p["derived"]["context_quality"] == tier),
            key=lambda p: p["identity"]["project_key"],
        )
        selected.extend(tier_projects[:count])
    return selected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/run_instructions_audit.py tests/test_run_instructions_audit.py
git commit -m "feat: add stratified pilot selection (Stage 0)"
```

---

## Task 4: `build_record` (Stage 1a — compact record from snapshot, pure)

**Files:**
- Modify: `src/run_instructions_audit.py`
- Test: `tests/test_run_instructions_audit.py`

- [ ] **Step 1: Write the failing test**

```python
from src.run_instructions_audit import build_record


def test_build_record_resolves_path_and_primary():
    project = {
        "identity": {
            "project_key": "Fun:GamePrjs/BattleGrid",
            "path": "Fun:GamePrjs/BattleGrid",
            "display_name": "BattleGrid",
        },
        "derived": {
            "context_files": ["AGENTS.md", "README.md"],
            "run_instructions_present": False,
        },
    }
    record = build_record(project, "/Users/d/Projects")

    assert record["abs_path"] == "/Users/d/Projects/Fun:GamePrjs/BattleGrid"
    assert record["primary_file_name"] == "AGENTS.md"   # no CLAUDE.md → AGENTS.md
    assert record["snapshot_claim"] is False
    assert record["context_files"] == ["AGENTS.md", "README.md"]
    assert record["project_key"] == "Fun:GamePrjs/BattleGrid"


def test_build_record_prefers_claude_md():
    project = {
        "identity": {"project_key": "x", "path": "x", "display_name": "x"},
        "derived": {"context_files": ["AGENTS.md", "CLAUDE.md"], "run_instructions_present": True},
    }
    assert build_record(project, "/w")["primary_file_name"] == "CLAUDE.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_instructions_audit.py -k build_record -q`
Expected: FAIL — `ImportError: cannot import name 'build_record'`

- [ ] **Step 3: Write minimal implementation**

```python
def build_record(project: dict, workspace_root: str) -> dict:
    path = project["identity"]["path"]
    context_files = project["derived"]["context_files"]
    return {
        "project_key": project["identity"]["project_key"],
        "display_name": project["identity"]["display_name"],
        "abs_path": str(Path(workspace_root) / path),
        "primary_file_name": choose_primary_context_file(context_files),
        "context_files": context_files,
        "snapshot_claim": bool(project["derived"]["run_instructions_present"]),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/run_instructions_audit.py tests/test_run_instructions_audit.py
git commit -m "feat: add build_record (Stage 1a) for run-instructions audit"
```

---

## Task 5: IO fns — `is_after`, `compute_drifted`, `compute_tool_today` (Stage 1b/c)

**Files:**
- Modify: `src/run_instructions_audit.py`
- Test: `tests/test_run_instructions_audit.py`

- [ ] **Step 1: Write the failing test**

```python
import os
import subprocess

from src.run_instructions_audit import compute_drifted, compute_tool_today, is_after


def test_is_after_compares_tz_aware_iso():
    assert is_after("2026-05-25T19:25:00-07:00", "2026-05-17T05:01:39+00:00")
    assert not is_after("2026-05-10T00:00:00+00:00", "2026-05-17T05:01:39+00:00")


def test_compute_tool_today_true_when_run_heading_matches_alias(tmp_path):
    # "## Usage" IS a run_instructions alias → present
    (tmp_path / "CLAUDE.md").write_text(
        "# Proj\n\n## Usage\n\nRun the dev server with `npm run dev`. It serves on :3000.\n"
    )
    assert compute_tool_today(str(tmp_path)) is True


def test_compute_tool_today_false_when_run_heading_outside_alias(tmp_path):
    # "## Running" is NOT in the alias list → the tool misses it (alias-gap case)
    (tmp_path / "CLAUDE.md").write_text(
        "# Proj\n\n## Running\n\nStart it with `npm run dev`. This is genuine run guidance.\n"
    )
    assert compute_tool_today(str(tmp_path)) is False


def _git_commit_at(path, iso):
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": iso, "GIT_COMMITTER_DATE": iso,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, env=env, check=True)


def test_compute_drifted_true_when_commit_after_snapshot(tmp_path):
    _git_commit_at(tmp_path, "2026-05-25T00:00:00+00:00")
    assert compute_drifted(str(tmp_path), "2026-05-17T05:01:39+00:00") is True


def test_compute_drifted_false_when_commit_before_snapshot(tmp_path):
    _git_commit_at(tmp_path, "2026-05-01T00:00:00+00:00")
    assert compute_drifted(str(tmp_path), "2026-05-17T05:01:39+00:00") is False


def test_compute_drifted_false_for_non_git_dir(tmp_path):
    assert compute_drifted(str(tmp_path), "2026-05-17T05:01:39+00:00") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_instructions_audit.py -k "is_after or tool_today or drifted" -q`
Expected: FAIL — `ImportError: cannot import name 'is_after'`

- [ ] **Step 3: Write minimal implementation**

```python
def compute_tool_today(abs_path: str) -> bool:
    project_path = Path(abs_path)
    analysis = analyze_project_context(project_path, _collect_context_files(project_path))
    return bool(analysis.run_instructions_present)


def is_after(commit_iso: str, generated_at_iso: str) -> bool:
    return datetime.fromisoformat(commit_iso) > datetime.fromisoformat(generated_at_iso)


def compute_drifted(abs_path: str, generated_at: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", abs_path, "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    commit_iso = result.stdout.strip()
    if result.returncode != 0 or not commit_iso:
        return False
    return is_after(commit_iso, generated_at)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: PASS (12 passed). If `compute_tool_today` cases fail on heading parsing, inspect `analyze_project_context` behavior on the fixture and adjust the fixture headings — not the assertion intent.

- [ ] **Step 5: Commit**

```bash
git add src/run_instructions_audit.py tests/test_run_instructions_audit.py
git commit -m "feat: add live tool_today recompute + git drift detection (Stage 1)"
```

---

## Task 6: `prepare_pilot` + `main` (Stage 0+1 orchestration)

**Files:**
- Modify: `src/run_instructions_audit.py`
- Test: `tests/test_run_instructions_audit.py`

- [ ] **Step 1: Write the failing test**

```python
import json

from src.run_instructions_audit import prepare_pilot


def test_prepare_pilot_builds_records_and_reports_missing_dirs(tmp_path):
    workspace = tmp_path / "ws"
    real = workspace / "RealRepo"
    real.mkdir(parents=True)
    (real / "CLAUDE.md").write_text("# R\n\n## Usage\n\nRun `npm run dev` to start the server.\n")

    snapshot = {
        "workspace_root": str(workspace),
        "generated_at": "2026-05-17T05:01:39+00:00",
        "projects": [
            {
                "identity": {"project_key": "RealRepo", "path": "RealRepo", "display_name": "RealRepo"},
                "derived": {
                    "registry_status": "active", "context_quality": "full",
                    "context_files": ["CLAUDE.md"], "run_instructions_present": True,
                },
            },
            {
                "identity": {"project_key": "GhostRepo", "path": "GhostRepo", "display_name": "GhostRepo"},
                "derived": {
                    "registry_status": "active", "context_quality": "full",
                    "context_files": ["CLAUDE.md"], "run_instructions_present": False,
                },
            },
        ],
    }
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snapshot))

    result = prepare_pilot(str(snap_path), per_tier={"full": 4})

    assert result["workspace_root"] == str(workspace)
    assert len(result["records"]) == 1
    assert len(result["errors"]) == 1
    record = result["records"][0]
    assert record["project_key"] == "RealRepo"
    assert record["tool_today"] is True            # live recompute on the fixture file
    assert record["drifted"] is False              # no git repo → not drifted
    assert result["errors"][0]["error"] == "missing_dir"
    assert result["errors"][0]["project_key"] == "GhostRepo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_instructions_audit.py -k prepare_pilot -q`
Expected: FAIL — `ImportError: cannot import name 'prepare_pilot'`

- [ ] **Step 3: Write minimal implementation**

```python
def prepare_pilot(snapshot_path: str, *, per_tier: dict[str, int] = DEFAULT_PER_TIER) -> dict:
    snapshot = json.loads(Path(snapshot_path).read_text())
    workspace_root = snapshot["workspace_root"]
    generated_at = snapshot["generated_at"]
    records: list[dict] = []
    errors: list[dict] = []
    for project in select_pilot(snapshot["projects"], per_tier=per_tier):
        record = build_record(project, workspace_root)
        if not Path(record["abs_path"]).is_dir():
            errors.append(
                {
                    "project_key": record["project_key"],
                    "abs_path": record["abs_path"],
                    "error": "missing_dir",
                }
            )
            continue
        record["tool_today"] = compute_tool_today(record["abs_path"])
        record["drifted"] = compute_drifted(record["abs_path"], generated_at)
        records.append(record)
    return {
        "generated_at": generated_at,
        "workspace_root": workspace_root,
        "records": records,
        "errors": errors,
    }


def main() -> None:
    import sys

    snapshot_path = sys.argv[1] if len(sys.argv) > 1 else "output/portfolio-truth-latest.json"
    print(json.dumps(prepare_pilot(snapshot_path), indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_instructions_audit.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Verify ruff + run against the real snapshot (smoke, read-only)**

Run: `python -m ruff check src/run_instructions_audit.py && python -m src.run_instructions_audit output/portfolio-truth-latest.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('records', len(d['records']), 'errors', len(d['errors']))"`
Expected: ruff clean; ~15–20 records, errors listed (not crashed). Confirms real paths resolve.

- [ ] **Step 6: Commit**

```bash
git add src/run_instructions_audit.py tests/test_run_instructions_audit.py
git commit -m "feat: add prepare_pilot orchestrator + CLI entrypoint (Stage 0+1)"
```

---

## Task 7: The Workflow script (Stages 2–4) + 2-repo smoke

**Files:**
- Create: `scripts/run-instructions-audit.workflow.js`

This task is **main-session only** (it calls the `Workflow` tool). No pytest.

- [ ] **Step 1: Write the workflow script**

```javascript
// scripts/run-instructions-audit.workflow.js
export const meta = {
  name: 'run-instructions-audit',
  description: 'Audit snapshot run_instructions_present claim against on-disk ground truth',
  phases: [
    { title: 'Verify', detail: 'one Haiku subagent per pilot repo reads files and judges' },
    { title: 'Synthesize', detail: 'one Sonnet call writes the markdown report' },
  ],
}

const VERIFIER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'evidence_in_primary', 'evidence_quote', 'evidence_location', 'confidence'],
  properties: {
    verdict: { type: 'boolean' },
    evidence_in_primary: { type: 'boolean' },
    evidence_quote: { type: 'string', maxLength: 240 },
    evidence_location: { type: 'string' },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}

const { generated_at, records, errors } = args

function verifierPrompt(rec) {
  return [
    `You audit whether a project documents HOW TO RUN IT. Judge independently — you are NOT told the tool's answer.`,
    `Project: ${rec.project_key}`,
    `Directory (absolute): ${rec.abs_path}`,
    `The tool treats "${rec.primary_file_name}" as the PRIMARY context file; it may be absent.`,
    `Listed context files: ${JSON.stringify(rec.context_files)}.`,
    ``,
    `Do this:`,
    `1. Read the primary file (if present), README.md, and the other listed context files, by absolute path under the directory.`,
    `2. Decide: do these files genuinely tell a developer how to run/start the project — a run command, dev server, build+run steps, or quickstart? A bare dependency-install ("pip install", "## Installation" of deps) alone is NOT run instructions.`,
    `3. If yes: verdict=true; quote the exact run command or heading (<=240 chars) in evidence_quote; set evidence_location like "CLAUDE.md §Usage" or "README §Getting Started".`,
    `4. evidence_in_primary=true ONLY if that evidence is inside "${rec.primary_file_name}". If the primary file is absent, or the evidence is only in README/another file, set it false.`,
    `5. If no run instructions exist anywhere, verdict=false with empty quote/location. Default to false when uncertain.`,
  ].join('\n')
}

// --- Stage 3 tally logic (mirror of src/run_instructions_audit.py) ---
function assignBucket(toolToday, verdict, inPrimary) {
  if (toolToday === verdict) return verdict ? 'agree_present' : 'agree_absent'
  if (verdict && !toolToday) return inPrimary ? 'fn_alias_gap' : 'fn_blind_spot'
  return 'fp_overclaim'
}
function assignDrift(snapshotClaim, toolToday, drifted) {
  if (snapshotClaim === toolToday) return 'claim_same'
  return drifted ? 'claim_changed_drift' : 'claim_changed_nodrift'
}

phase('Verify')
const verified = await parallel(
  records.map((rec) => () =>
    agent(verifierPrompt(rec), {
      label: `verify:${rec.project_key}`,
      phase: 'Verify',
      model: 'haiku',
      agentType: 'Explore',
      schema: VERIFIER_SCHEMA,
    })
      .then((v) => ({ rec, v }))
      .catch(() => null)
  )
)

const rows = verified.filter(Boolean).map(({ rec, v }) => ({
  project_key: rec.project_key,
  primary_file_name: rec.primary_file_name,
  snapshot_claim: rec.snapshot_claim,
  tool_today: rec.tool_today,
  drifted: rec.drifted,
  ...v,
  bucket: assignBucket(rec.tool_today, v.verdict, v.evidence_in_primary),
  drift_bucket: assignDrift(rec.snapshot_claim, rec.tool_today, rec.drifted),
}))

const counts = rows.reduce((acc, r) => ((acc[r.bucket] = (acc[r.bucket] || 0) + 1), acc), {})
const disagreements = rows.filter((r) => !r.bucket.startsWith('agree'))
const agreementRate = rows.length ? (rows.length - disagreements.length) / rows.length : 0
log(`Verified ${rows.length} repos — ${disagreements.length} disagreements, agreement ${(agreementRate * 100).toFixed(0)}%`)

phase('Synthesize')
const synthesisPrompt = [
  `Write a markdown audit report for the snapshot claim "run_instructions_present". Return ONLY markdown, no preamble.`,
  `Facts: snapshot generated_at=${generated_at}; repos verified=${rows.length}; agreement rate (verifier vs tool_today)=${(agreementRate * 100).toFixed(0)}%.`,
  `Bucket counts: ${JSON.stringify(counts)}.`,
  `Unresolved-path errors: ${JSON.stringify(errors)}.`,
  `Disagreement rows (JSON): ${JSON.stringify(disagreements, null, 2)}`,
  ``,
  `Required sections:`,
  `1. Headline — repos, agreement rate, counts per bucket.`,
  `2. Disagreements — a table keyed by project_key with columns: bucket, evidence_quote, evidence_location, confidence, drifted.`,
  `3. Drift summary — count rows where drift_bucket != "claim_same", split claim_changed_drift (explained) vs claim_changed_nodrift (snapshot likely wrong).`,
  `4. Prescriptive fixes — for fn_alias_gap rows, the exact headings to add to CONTEXT_SECTION_ALIASES; if any fn_blind_spot rows, recommend choose_primary_context_file consider README.md; for fp_overclaim, flag the over-claim.`,
].join('\n')

const report = await agent(synthesisPrompt, { label: 'synthesis', phase: 'Synthesize', model: 'sonnet' })

return {
  report,
  stats: { verified: rows.length, agreementRate, counts, disagreements: disagreements.length, errors: errors.length },
  rows,
}
```

- [ ] **Step 2: Sanity-check the JS bucket logic matches Python**

Confirm by eye that `assignBucket`/`assignDrift` in the JS are line-for-line equivalent to `assign_bucket`/`assign_drift_bucket` in `src/run_instructions_audit.py` (same branch order, same string returns). They are the same six lines.

- [ ] **Step 3: 2-repo smoke run (main session)**

In the main session:
1. Run the pre-step and capture the JSON payload:
   `python -m src.run_instructions_audit output/portfolio-truth-latest.json`
2. Slice the payload to its first 2 `records` (keep `generated_at`, `workspace_root`, `errors`).
3. Call `Workflow({ scriptPath: "scripts/run-instructions-audit.workflow.js", args: <sliced payload> })`.

Expected: 2 Haiku verifiers run + 1 Sonnet synthesis; the tool returns `{ report, stats, rows }` with `rows.length === 2` and each row carrying a `bucket` + `drift_bucket`. If schema validation errors occur, fix the prompt/schema and re-run only this smoke.

- [ ] **Step 4: Commit the workflow script**

```bash
git add scripts/run-instructions-audit.workflow.js
git commit -m "feat: add run-instructions audit Workflow (verify fan-out + tally + synthesis)"
```

---

## Task 8: Run the full pilot + write the report + hand-validate

This task is **main-session only**. No pytest.

- [ ] **Step 1: Run the pilot end-to-end**

1. `python -m src.run_instructions_audit output/portfolio-truth-latest.json` → full payload (~19 records).
2. `Workflow({ scriptPath: "scripts/run-instructions-audit.workflow.js", args: <full payload> })`.

Expected: ~19 Haiku verifiers + 1 Sonnet synthesis; returns `{ report, stats, rows }`.

- [ ] **Step 2: Write the report + a rows sidecar for auditing**

In the main session, `Write` the returned `report` to `output/run-instructions-audit-2026-05-29.md`, and `Write` `JSON.stringify(rows, null, 2)` to `output/run-instructions-audit-2026-05-29.rows.json` (so every verdict is inspectable).

- [ ] **Step 3: Hand-validate (the whole point of a small pilot)**

For **every** disagreement row, open the cited file at `evidence_location` in the repo and confirm the verifier's call by hand. Note any verifier error. Confirm buckets sum to the verified count and that `errors` (unresolved dirs) were reported, not dropped.

- [ ] **Step 4: Record the outcome**

Append a short "Pilot result" note to the spec (`docs/plans/2026-05-29-run-instructions-external-audit.md`): agreement rate, dominant bucket (tests the blind-spot hypothesis), and any verifier misses found during hand-validation. Commit:

```bash
git add output/run-instructions-audit-2026-05-29.md output/run-instructions-audit-2026-05-29.rows.json docs/plans/2026-05-29-run-instructions-external-audit.md
git commit -m "chore: run-instructions audit pilot results"
```

> Note: `output/` is gitignored. If you want the report in git, add an explicit force-add (`git add -f`) — otherwise the commit captures only the spec note, which is fine.

---

## Self-Review

**Spec coverage:**
- §5 Stage 0 (pilot selection) → Task 3. Stage 1 (evidence prep + `tool_today` + drift) → Tasks 4–5. Stage 2 (verifier) → Task 7. Stage 3 (tally) → Tasks 1–2 (logic) + Task 7 (applied in JS). Stage 4 (synthesis + report) → Task 7 + Task 8. ✓
- §5 "where each stage runs" (pre-step in main session via `ctx_execute`/CLI; fan-out in workflow; FS reads in subagents) → Tasks 6–8. ✓
- §6 data contract (record + verifier schema fields) → Task 4 (record), Task 7 (`VERIFIER_SCHEMA`). ✓
- §7 guarantees: read-only (no writes in any fn), Haiku fan-out + Sonnet synthesis + no Opus in fan-out (Task 7 `model` pins), blind verification (prompt omits the claim). ✓
- §8 gotchas: drift via `tool_today`+drift bucket (Tasks 2,5); README blind spot as `fn_blind_spot` (Task 1); polluted population filtered (Task 3); path encoding via snapshot `path` join + `is_dir()` pre-flight (Tasks 4,6); workflow JS no-FS handled by pre-step split (Tasks 6–8). ✓
- §9 out of scope respected (no extra booleans, no numeric score, pilot-only N). ✓
- §10 done criteria → Task 8 steps 2–3. ✓

**Placeholder scan:** No TBD/TODO; all steps have real code or exact commands. ✓

**Type consistency:** `assign_bucket(tool_today, verdict, evidence_in_primary)` / `assign_drift_bucket(snapshot_claim, tool_today, repo_drifted)` identical in Python (Tasks 1–2) and JS (`assignBucket`/`assignDrift`, Task 7). Record keys (`project_key, display_name, abs_path, primary_file_name, context_files, snapshot_claim, tool_today, drifted`) consistent across Tasks 4/6/7. Verifier schema fields (`verdict, evidence_in_primary, evidence_quote, evidence_location, confidence`) consistent Task 7 ↔ spec §6. Bucket strings (`agree_present/agree_absent/fn_alias_gap/fn_blind_spot/fp_overclaim`) and drift strings (`claim_same/claim_changed_drift/claim_changed_nodrift`) consistent. ✓
