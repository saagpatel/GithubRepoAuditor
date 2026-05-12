# GithubRepoAuditor — Portfolio Disposition

**Status:** Active (operator-tool / dogfood shape) — Python
**`github-repo-auditor` v0.19.0** on `origin/main`. Currently in
Arc F (PyPI publish + shiv binary distribution + FastAPI/HTMX
local web UI + CLI restructure) and Arc G (draft-readme writeback
via existing approval pipeline). **First member of a new operator-
tool / dogfood disposition shape** — this is the operator's own
portfolio audit tool, the very system this disposition campaign
is dogfooding. **Likely second member of the PyPI distribution
cluster** once Arc F's `feat(release): PyPI publish workflow +
shiv binary distribution` lands a tagged release.

> Disposition uses strict `origin/main` verification.
> **Introduces the operator-tool / dogfood shape** — distinct from
> "shipped to external users" categories because the operator is
> the audience.

---

## Verification posture

This repo has **only `origin`** (`saagpatel/GithubRepoAuditor`) —
no `legacy-origin` remote. Clean migration state. Local clone's
`main` is tracking `origin/main` correctly.

Specifically verified on `origin/main`:

- Tip: `9021c9d` fix(serve): render HTML 404 for unknown repos,
  suppress favicon console error (#164)
- **Arc G commits** (current frontier, draft-readme writeback):
  - `d462eb5` feat(draft-readmes): apply approved packets via
    existing writeback path (Arc G S5.5)
  - `54c26b2` feat(serve): render draft-readme diff view in
    `/approvals` (Arc G S5.4)
  - `f0fa9c5` feat(draft-readmes): core module + CLI wiring +
    prefs integration (Arc G S5.1-5.3)
- **Arc F commits** (PyPI + serve + CLI restructure):
  - `9ee3932` feat(cli): subcommand restructure run/triage/report
    with legacy shim (Arc F S4.3)
  - `1316aaf` feat(release): PyPI publish workflow + shiv binary
    distribution (Arc F S4.2)
  - `4da1496` feat(serve): add audit serve FastAPI + HTMX local
    web UI (Arc F S4.1)
- Package identity (`pyproject.toml` on `origin/main`):
  - `name = "github-repo-auditor"`
  - `version = "0.19.0"`
- Tree on `origin/main`:
  - `src/` — Python source
  - `tests/`, `fixtures/`
  - `assets/`, `config/`, `docs/`, `output/`
  - **`NEXT_CHAT_HANDOFF.md`** — operator's cross-chat handoff
    artifact, on canonical main
  - `IMPLEMENTATION-ROADMAP.md`
- Default branch: `main`

---

## Current state in one paragraph

GithubRepoAuditor (CLI: `github-repo-auditor`, currently v0.19.0)
is the operator's own portfolio operating system, written in Python.
It audits all repos under `/Users/d/Projects` across documentation,
testing, CI, dependencies, activity, security, structure, community
profile, completeness, and interest signals; scores them on dual
axes; tiers them into useful categories; surfaces quick wins;
generates aligned JSON / Markdown / HTML / workbook / review-pack /
control-center outputs from the same audit facts; writes a weekly
command-center digest; produces a canonical workspace-level
portfolio truth snapshot; preserves historical state in SQLite for
the operator loop to show change / regression / recovery / follow-
through. The workbook and `--control-center` are the day-to-day
operating surfaces. Currently 799 tests (per memory). Arc F is
landing PyPI publish + shiv binary + FastAPI + HTMX serve UI; Arc G
is landing draft-readme generation with operator approval flow.

For full detail see:
- `README.md` on `origin/main`
- `NEXT_CHAT_HANDOFF.md` on `origin/main` — operator's own ledger
- `IMPLEMENTATION-ROADMAP.md`

---

## Why "Active (operator-tool / dogfood shape)" — NOT shipped clusters

GithubRepoAuditor is unusual in the portfolio:

1. **The operator is the audience.** Unlike everything else in the
   cluster taxonomy (signing cluster, App Store, static-host,
   self-hosted service, PyPI), this isn't shipped *to* anyone —
   it's the operator's own portfolio operating surface.
2. **Active Arc F + Arc G work on canonical main.** Arc F is mid-
   delivery (the FastAPI + HTMX serve UI is live, the PyPI workflow
   is wired, but no tagged release has hit PyPI yet that I can see).
   Arc G's draft-readme writeback is freshly merged but not in a
   tagged release.
3. **Dogfood loop.** This very disposition campaign is feeding
   GithubRepoAuditor: every `docs/PORTFOLIO-DISPOSITION.md` shipped
   in this session changes the input that GithubRepoAuditor audits.
   The tool's own state is downstream of the disposition work.

This is the **first operator-tool / dogfood shape** in the session.
The shape is characterized by: tool used by operator, not shipped
to users; ongoing Arc-based development; the operator depends on
the tool for the same workflow the tool documents.

---

## Cluster taxonomy update

This row adds an **operator-tool / dogfood shape** alongside the
existing distribution clusters:

| Cluster / shape | Count | Audience |
|---|---|---|
| Signing (Apple desktop) | 22 | External users |
| iOS App Store | 1 | External users |
| Static-host (web) | 3 | External users |
| Self-hosted service | 1 | Operator-self-hosts for external users |
| PyPI distribution | 1 (likely 2 soon) | External Python users |
| Local-first pipeline | 1 | Operator runs, publishes externally |
| **Operator-tool / dogfood (new)** | **1** | Operator self |

When Arc F lands a tagged PyPI release, GithubRepoAuditor will
*also* be a PyPI distribution cluster member — at that point it's
dual-classified (operator tool + PyPI), with the operator-tool
classification being the primary one (the operator's reliance on
it is the dominant relationship).

---

## Why this row is Active, not Release Frozen

- **Active** — correct. Arc F and Arc G are in flight on canonical
  main. The shiv binary + PyPI publish workflow is wired, but no
  tagged release has actually cut yet from what's visible. The
  draft-readme feature is new enough that operator iteration is
  likely.
- **Release Frozen** — wrong. There's no "operator declared done"
  signal; the opposite is true (multiple Arc-named active stories).
- **Cold Storage / Archived** — wrong. Active development.

If Arc F tags a v1.0 PyPI release in the next session or two, this
row transitions to Release Frozen (PyPI cluster) — but until then,
Active is right.

---

## Next moves (operator priority, informational)

Per `NEXT_CHAT_HANDOFF.md` shape, the operator already maintains
their own next-priority ledger inline. The disposition's job here
is to acknowledge that ledger as authoritative and slot the row
into portfolio operations.

Likely near-term:

1. **Cut Arc F PyPI tagged release.** The publish workflow exists;
   it just needs a version-bump-and-tag invocation. Likely
   `github-repo-auditor` becomes installable via `pip install` once
   tagged.
2. **Close Arc G S5.5 follow-up.** The "apply approved packets via
   existing writeback path" commit landed; verify end-to-end
   draft-readme flow with at least one real-repo trial.
3. **Continue dogfood loop.** As more disposition docs land in the
   portfolio (this session, future sessions), confirm
   GithubRepoAuditor recognizes them as healthy signals in its
   audit / control-center / weekly-digest outputs.

---

## Portfolio operating system instructions

| Aspect | Posture |
|---|---|
| Portfolio status | `Active (operator-tool / dogfood)` |
| Audience | **Operator self** (primary); future PyPI users (secondary) |
| Review cadence | **Daily / on-demand** — operator uses this tool, drift in the tool affects all other audit work |
| Resurface conditions | (a) Arc F tags a PyPI release (transitions to Release Frozen / PyPI), (b) Arc G closes, (c) any operator-discovered audit-correctness bug |
| Do **not** auto-batch with external-shipped clusters | Audience is operator |
| **New shape: operator-tool / dogfood** | **First member.** Future internal tooling repos (if any) batch here. |
| Special concern | **Self-referential audit drift.** If this tool ever scores its own state incorrectly, the whole audit pipeline is compromised. Worth periodic operator review of the row this tool produces for itself. |
| Special concern | **`NEXT_CHAT_HANDOFF.md` is operator-canonical.** This disposition defers to the handoff file for active-state truth. |

---

## Reactivation procedure (for the next code session)

1. **Re-read `NEXT_CHAT_HANDOFF.md` first** — operator's own ledger
   is authoritative.
2. Verify `git branch -vv` shows `main` tracking `origin/main`.
   Already correct as of this disposition pass.
3. Review any local stash (`r11-gha-stash` if created) for
   uncommitted work.
4. Untracked `.playwright-mcp/` and `audit-serve-*.png` screenshots
   suggest recent serve-UI screenshot capture — confirm what they're
   for before discarding.
5. Re-run `uv sync && pytest` — should still pass 799 tests.
6. Check Arc F PyPI publish status. If a tagged release exists on
   PyPI, this row promotes to dual-classified (operator tool + PyPI
   distribution).

---

## Last known reference

| Field | Value |
|---|---|
| `origin/main` tip | `9021c9d` fix(serve): render HTML 404 for unknown repos, suppress favicon console error (#164) |
| Last substantive commit | `d462eb5` feat(draft-readmes): apply approved packets via existing writeback path (Arc G S5.5) |
| Default branch | `main` |
| Build system | Python 3.11+ (uv) + Click + FastAPI + HTMX + SQLite |
| Current version | **0.19.0** (pre-PyPI-tagged) |
| Test count | **799** (per memory) |
| Distribution channel (future) | PyPI + shiv binary (Arc F workflow wired but not yet tagged) |
| Active arcs | **Arc F** (PyPI + serve UI + CLI restructure), **Arc G** (draft-readme writeback) |
| Operator artifact | **`NEXT_CHAT_HANDOFF.md` on canonical main** — operator's own cross-chat ledger |
| Blocker | None for current state; future tagged-PyPI-release is operator-cadence |
| Migration state | **No `legacy-origin` remote** — clean |
| Distinguishing feature | **The operator's own portfolio operating system.** Audience is operator-self; the tool's outputs are what the disposition campaign is feeding into. First operator-tool / dogfood shape. |
