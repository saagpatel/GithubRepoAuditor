# Release Gates

This document describes the pre-release quality gates for the GithubRepoAuditor project. Gates must pass before tagging a release.

## Standard Gate (all releases)

```bash
python3 -m pytest -q -p no:cacheprovider   # full suite must be green
python3 -m ruff check src/ tests/           # no lint errors
```

## Mutation-Testing Gate (scope: auto_apply + scorer)

Mutation testing is scoped to the two files that guard automated actions:

| File | Why gated |
|------|-----------|
| `src/auto_apply.py` | Trust-bar gating — controls which repos receive automated writes |
| `src/scorer.py` | Scoring/tier logic — drives completeness tiers and portfolio grades |

### Required threshold

**Kill rate ≥ 85%** per combined run (killed ÷ (killed + survived), timeouts excluded).

### Running the gate

```bash
make release-gate
```

Or manually:

```bash
rm -rf .mutmut-cache mutants/
python3.13 -m mutmut run
```

Query results directly (the `mutmut results` command crashes on Python 3.13):

```bash
python3.13 -c "
import sqlite3
conn = sqlite3.connect('.mutmut-cache')
rows = conn.execute('SELECT status, count(*) FROM Mutant GROUP BY status').fetchall()
for r in rows: print(r)
killed = next(r[1] for r in rows if r[0] == 'ok_killed')
survived = next((r[1] for r in rows if r[0] == 'bad_survived'), 0)
print(f'Kill rate: {killed / (killed + survived):.1%}')
"
```

### Setup requirements

mutmut 2.x is incompatible with Python 3.14 (pony ORM `deepcopy` crash). Use Python 3.13:

```bash
python3.13 -m pip install 'mutmut>=2.0,<3.0'
python3.13 -m pip install -e ".[dev,config]"
```

mutmut 3.x is incompatible with this project's `src.` layout (rejects module names starting with `src.`). The locked version constraint in `pyproject.toml` (`mutmut>=2.5` under `[tool.mutmut]`) documents this.

### Configuration

`[tool.mutmut]` in `pyproject.toml`:

```toml
[tool.mutmut]
paths_to_mutate = "src/auto_apply.py,src/scorer.py"
runner = "python3.13 -m pytest -q -p no:cacheprovider -x tests/test_auto_apply.py tests/test_scorer.py"
tests_dir = "tests/"
```

### Equivalent mutants

The following survivors are confirmed equivalent mutants — behavioral tests cannot distinguish them:

**src/auto_apply.py**

| ID | Line | Pattern | Why equivalent |
|----|------|---------|----------------|
| 27, 28 | 48 | Second `or "elevated"` in risk_tier | `str()` always returns a string; the outer `or` fallback is unreachable |
| 43, 44 | 64 | Default `""` in display_name | Guarded immediately by `if not repo_name: continue` |
| 58 | 71 | `or "XXelevatedXX"` in summarize_trust_bar | Same unreachable-fallback pattern |
| 75, 80 | 92–93 | `or "XXXX"` in get_approved_manual_campaigns | Mutated default never equals the string being compared |
| 106 | 132 | `or "XXXX"` in filter_trusted_repo_actions | Same pattern |

**src/scorer.py**

| ID | Line | Pattern | Why equivalent |
|----|------|---------|----------------|
| 168 | 66 | `security_offline: bool = False` | Parameter default; never mutated at call sites under test |
| 173 | 75 | `+ FORK_ACTIVITY_WEIGHT` vs `-` | With uniform scores, redistribution direction doesn't change overall_score materially |
| 175 | 76 | `weights["XXactivityXX"]` | activity weight is read back in the weighted sum; XXactivity key is ignored |
| 178 | 77 | `k != "XXactivityXX"` | activity is always in weights; excluding a nonexistent key is a no-op |
| 183, 184 | 80 | `* (w/other_total)` vs `/ (w/other_total)` | With uniform scores, proportional redistribution gives same weighted average |
| 225, 226 | 112 | `tier = "XXabandonedXX"` / `None` | Loop always overwrites (COMPLETENESS_TIERS ends with threshold 0.0) |
| 227 | 114 | `>= threshold` → `> threshold` | Floating-point prevents exact equality at tier boundaries in practice |
| 230, 231 | 119 | `interest_tier = "XXmundaneXX"` / `None` | Loop always overwrites (INTEREST_TIERS ends with threshold 0.0) |
| 236, 241, 246 | 126–130 | Default `2.0` vs `1.0` for missing dims | `== 0.0` check: neither `1.0` nor `2.0` equals `0.0` |
| 251 | 136 | `>= 0.5` vs `> 0.5` | Score exactly 0.5 yields "functional" tier anyway (not "shipped"), so cap doesn't fire |
| 304 | 213 | `>= 0.3` vs `> 0.3` for mid-tier boundary | Exact 0.3 shipped_ratio is rare in test scenarios |

### Current kill rates (last measured: 2026-05-10)

| File | Mutants | Killed | Survived | Kill Rate |
|------|---------|--------|----------|-----------|
| src/auto_apply.py | ~155 | ~146 | ~9 | ~94% |
| src/scorer.py | ~200 | ~182 | ~16 | ~92% |
| **Combined** | **354** | **328** | **25** | **92.9%** |

(1 timeout excluded from denominator; 1 suspicious counted as killed)

## Distribution Gate (scope: GitHub Release assets)

Run before any public release tag. Requires the `[build]` extra:

```bash
pip install -e '.[build]'   # installs shiv, build, twine
```

### Steps

```bash
make build        # python -m build → dist/*.whl + dist/*.tar.gz
make dist-check   # python -m twine check dist/*  (must be clean)
make shiv         # builds dist/audit.pyz via shiv
```

Verify the shiv binary boots:

```bash
./dist/audit.pyz --help
```

Expected: help text printed, exit 0. Any import error or missing-extra warning is a
blocking failure.

### Gate criteria

All three must pass before tagging:

1. `make build` exits 0 with a `.whl` and `.tar.gz` present in `dist/`.
2. `python -m twine check dist/*` reports no errors or warnings.
3. `./dist/audit.pyz --help` exits 0 and prints the CLI help text.

### Notes

- The GitHub Actions `release.yml` workflow runs these same steps on every PEP 440-compatible `v*` tag
  and uploads all three artifacts to the GitHub Release.
- Use tags like `v0.1.0` or `v0.1.1`. Avoid suffix tags such as
  `v0.1.0-public-baseline`; package version derivation comes from `setuptools-scm`
  and non-PEP 440 tag suffixes can break the release build.
- Public hardening releases should use patch versions (`v0.1.x`). Feature releases
  should move the minor version (`v0.2.0`, `v0.3.0`, and so on).
- PyPI upload is explicit opt-in and not part of the current public install story.
  `scripts/release.sh` builds and checks artifacts by default; it uploads only when
  run as `scripts/release.sh --publish-pypi` with valid credentials. CI only checks
  and uploads to GitHub Releases.
- After PyPI Trusted Publishing is configured, prefer the manual `Publish to PyPI`
  workflow over local token-based uploads. It builds the release tag in one job and
  publishes from a separate `pypi` environment job with `id-token: write`.
- The `[serve]` extra is not bundled in the shiv binary by default. Users who need the
  web UI should install from the GitHub source with the `[serve]` extra or use a local
  editable clone.

See [distribution.md](distribution.md) for the public distribution policy and the
remaining PyPI activation checklist.

## Web UI Gate (scope: audit serve)

Run when any change touches `src/serve/` or `tests/test_serve.py`.

### Steps

```bash
python3 -m pytest tests/test_serve.py -q -p no:cacheprovider
```

The test file covers:

- Route smoke tests: all 5 routes (`/`, `/repos/{name}`, `/runs`, `/approvals`,
  `/runs/new`) return 200 or the expected status code.
- 404 for an unknown repo name at `/repos/{name}`.
- 422 / rejection for disallowed flags in `POST /runs/new`.
- Shell-metacharacter injection strings rejected by `validate_flags`.
- SSE happy-path: `/runs/new/stream/{run_id}` yields output lines.
- Runner unit tests: `spawn_run` and `validate_flags` behave correctly.
- CLI flag wiring: `audit serve --port` and `--host` propagate to `run_serve`.

### Gate criteria

All tests in `tests/test_serve.py` must pass. Any injection-rejection test failure is a
blocking issue — do not ship a serve release with a failing injection test.
