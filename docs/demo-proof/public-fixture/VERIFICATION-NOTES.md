# Public Fixture Verification Notes

Date: 2026-08-02 (frames recaptured; supersedes the 2026-06-27 capture)

## Fixture Truth

- Fixture input: `fixtures/demo/sample-report.json` (audit-report lane) and
  `src/demo_portfolio.py` (PortfolioCommandCenter lane).
- Generated output directory: `output/demo`.
- Portfolio truth schema: sourced from the producer constant
  `src.portfolio_truth_types.SCHEMA_VERSION`, never restated in the generator.
- Visible project names: closed synthetic codename pool (`Aurora Ledger`,
  `Basalt Relay`, ... `Nocturne Spar`); no real repository is named.
- Visible workspace root: `/demo-workspace`.
- Freshness: `generated_at` is six hours before generation time, inside the
  consumer's 48h fresh band.

## Commands Run

```sh
./.venv/bin/python scripts/build_demo_artifacts.py
./.venv/bin/python scripts/validate_proof_package.py docs/demo-proof/public-fixture/proof-package.json
pnpm typecheck
pnpm test
pnpm build
pnpm demo:desktop:fixture
```

The 2026-08-02 recapture did not regenerate the fixture. The committed truth was
generated at `2026-08-01T22:50Z`, which was 20.6h old at capture time and well
inside the 48h fresh window, so regenerating would have churned the artifacts
without changing what the frames show. The consumer-side checks were re-run on
PortfolioCommandCenter `main` at `c4f572c` before capture: `pnpm typecheck`
clean, `pnpm test` 173 passing across 12 files.

## Visual Capture

Recaptured 2026-08-02 against the `0.11.0` fixture. Every frame comes from the
same live Tauri window launched with `pnpm demo:desktop:fixture`; no frame is
composited, cropped, or served from a Vite-only mock.

- Window normalised to 1280x820 and captured with `screencapture -x -R`, which
  yields 2560x1640 native-resolution PNGs.
- All eight tabs captured: Ops, Decisions, Portfolio, Risk + Security, Burndown,
  Trends, Weekly Digest, Automation.
- Tab switching was driven from the keyboard. The tab bar is a `role="tablist"`
  of plain buttons with no roving `tabindex`, so arrow keys do not move between
  tabs; the working sequence is Tab to walk focus onto the next tab button and
  Space to activate it. macOS System Events `click at` does not reach the
  WKWebView content and was not used.
- The active tab carries a keyboard focus ring in frames 01-07. That is the real
  rendered UI under keyboard navigation, not an annotation. Frame 00 was taken
  before focus entered the tab bar and therefore shows no ring.

## Public-Safety Review

Every frame was reviewed twice: once visually at full 2560x1640 resolution, and
once by OCR sweep so the claim rests on bytes rather than on eyeballing.

Visual inspection confirmed the frames show fixture labels only:

- project names come from the closed synthetic codename pool (`Aurora Ledger`,
  `Basalt Relay`, `Cinder Atlas`, ... `Umbra Trellis`);
- paths are synthetic relative slugs such as `flagship/aurora-ledger` and
  `studio/kestrel-loom`; no absolute local path appears;
- the header output-directory input renders the neutral label
  `demo fixture output (path redacted for capture)`;
- the boundary panel names `demo-org/demo-producer` and carries the
  `FIXTURE / DEMO DATA` pill;
- advisories and packages are synthetic (`demo-crypto-core`, `demo-ui-kit`,
  `demo-transport`, `GHSA-DEMO-0001` through `GHSA-DEMO-0003`);
- no terminal, browser chrome, account menu, token, email, calendar, Slack,
  Notion row, bridge-db row, personal-ops data, SecondBrain content, or real
  security finding is visible.

The OCR sweep ran `tesseract` over all eight frames and searched the extracted
text for the real producer owner and repository name (read directly from
`PortfolioCommandCenter/src-tauri/src/boundary.rs` rather than hardcoded), plus
`/Users/`, the operator's name, and a real workspace path fragment. No frame
matched any of them.

The sweep was scored against a known answer before its silence was trusted: each
frame was also required to yield the control strings `demo-org` and
`demo-producer`. All eight frames returned both controls (168-325 words
extracted per frame), so a clean result reflects absent text rather than a
failed OCR pass.

The generated truth artifacts were re-checked for the same boundary: no absolute
local path, operator name, or real repository name appears in
`output/demo/portfolio-truth*.json`, and every advisory remains synthetic.

## Recapture Blocker (2026-08-02)

A recapture attempt against the regenerated `0.11.0` fixture was made on
2026-08-02 and **abandoned before any frame was accepted**. The fixture itself is
sound: the app launched via `pnpm demo:desktop:fixture` rendered
`schema 0.11.0 · 40 projects`, `Freshness: fresh`, synthetic codenames only, and
the relative output path `../GithubRepoAuditor/output/demo`.

The blocker is in the consumer, not the fixture. PortfolioCommandCenter now
renders a persistent `SELECTED PRODUCER` boundary panel above the tab bar
(`src/App.tsx` renders `BoundaryPanel` unconditionally, immediately before the
tab nav), and that panel prints the operator's real GitHub owner and repository
name plus the canonical ref. Both values are compile-time constants in
`src-tauri/src/boundary.rs`:

```rust
pub(crate) const EXPECTED_PRODUCER_REPOSITORY: &str = "<owner>/<producer-repo>";
pub(crate) const EXPECTED_PRODUCER_REF: &str = "refs/remotes/origin/main";
```

They are surfaced through `BoundaryStatus.expected_repository` /
`expected_ref`. No environment variable, fixture path, demo Tauri config, or
output-directory choice overrides them, so **every tab of every frame carries the
real producer identity**. That is a public-safety stop under this package's own
"do not publish" list, which forbids private repo names and account identifiers.

Cropping or patching the band was rejected: the boundary panel is now
load-bearing UI, and a redacted frame is a doctored exhibit rather than evidence
of what the app renders.

Unblocking requires a PortfolioCommandCenter change that lets a demo build
present a fixture producer identity (for example, sourcing the expected producer
from configuration with the current constant as the default). That is consumer
work outside this package; until it lands, the visual-capture claim stays
`stale` and `verification.overall` stays `partial`.

### Resolved (2026-08-02)

The consumer change landed and this blocker is closed. PortfolioCommandCenter
`main` at `c4f572c` carries it across two merged pull requests:

- **#38**, which added display redaction to the boundary panel. When the resolved
  output directory is the configured demo fixture directory *and* the boundary
  reports `output_lock` is not `locked`, the panel renders
  `demo-org/demo-producer` plus a `FIXTURE / DEMO DATA` pill.
- a follow-up commit in the same pull request, which routes the header
  output-directory input through `outputDirDisplay` so it renders
  `demo fixture output (path redacted for capture)` read-only in demo mode. That
  input was the second leak: the real path names the producer repository.

Two properties of the fix matter for whether these frames count as evidence
rather than as a doctored exhibit:

1. **It is display-only.** The Rust boundary still verifies the real compile-time
   producer constants. Nothing in the redaction path can repoint that check, and
   the locks and capability reasons shown in the frames are the genuine
   evaluation of the real producer. The panel says so on its face.
2. **It cannot blank a real producing session.** The demo gate needs both a
   matching `VITE_DEMO_OUTPUT_DIR` *and* an unlocked output. Pointing the
   environment variable at the canonical output does not silence the identity,
   because `output_lock` is `locked` there.

The redaction is also applied to derived strings, not just the identity line.
`redactor()` rewrites the producer name out of enforcement reasons and recovery
detail on their way to the DOM, which is visible in the captured frames: the
Produce capability reads "locked to the canonical demo-producer output
directory". Redacting only the identity line would have leaked the name through
those strings.

Accordingly the visual-capture claim is now `passed` and
`verification.overall` is `passed`. The earlier judgement that a cropped or
patched band would be unacceptable still stands, and these frames do not rely on
one: nothing was cropped, painted over, or composited. The app rendered the
redacted values itself.
