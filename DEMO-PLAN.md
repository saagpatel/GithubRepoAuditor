# Demo Plan — Operator OS in 90 Seconds

A shot-by-shot script for a screen recording that makes a hiring manager
*understand the system* — not just see a pretty dashboard. The throughline:
**`git log` can't grade a portfolio; this can — and two agents act on it.**

The demo is driven entirely by **PortfolioCommandCenter** (the Tauri 2 desktop
shell), because it renders the truth artifact every other layer produces. Five
tabs, one header action, one closing line.

---

## What the viewer should walk away knowing

1. There's a **single source of truth** over 129 repos — graded, not just dated.
2. It surfaces the one number `git log` can't: **49 repos with live high/critical
   security alerts**, and exactly which package bump clears each.
3. The truth is **regenerated live** from the app, and it knows **which agent**
   (Claude Code / Codex) built which repo.

If those three land in 90 seconds, the demo worked.

---

## Pre-record setup (off-camera)

Do this before hitting record so the app opens warm and current:

1. **Refresh the producer artifacts** so the snapshot is today's:
   ```sh
   # in the auditor repo — flags FIRST, then username, run via python -m
   python -m src.cli --portfolio-truth --portfolio-truth-include-security <user>
   ```
2. **Launch the desktop shell** (release `.app`, or `pnpm tauri dev` for a dev run).
3. Confirm the header shows the correct **output directory** and a fresh
   `generated_at`.
4. Set window to a **clean 1920×1080 capture**; hide the macOS menu bar clutter.

> **Privacy callout (this is for a public audience):** the Portfolio tab lists
> real repo names. Before publishing, either (a) scroll/zoom to the **aggregate
> counts and risk columns** rather than individual rows, or (b) blur repo-name
> cells in post. Show the *shape* of the portfolio, not the contents.

---

## The 90-second shot list

| Time | Screen | Action | Line to land |
|---|---|---|---|
| **0:00–0:10** | App launch / **Portfolio** tab | Open cold. Let the full 129-row table paint. | *"Every repo I've ever started — 129 of them — in one graded view. Not a commit log. A judgement."* |
| **0:10–0:28** | **Portfolio** tab | Sort by risk tier; point at the columns: risk, context quality, registry status, **tool**, open high/critical alert count. | *"Each repo carries a risk tier, a context-quality grade, and who built it. `git log` gives you a timestamp; this tells you what the timestamp means."* |
| **0:28–0:48** | **Risk + Security** tab | Filter to elevated-risk; show the posture counts (scanned / open-high-critical / critical / high). | *"49 of 129 repos have a live high or critical security alert. That's the number a timestamp can never give you."* |
| **0:48–1:02** | **Burndown** tab | Show the advisory-grouped fix list — one package bump → the repos it clears. | *"And it's actionable: each advisory is grouped by the single dependency bump that burns it down across every affected repo."* |
| **1:02–1:14** | **Trends** → **Weekly Digest** | Flash the risk/security drift chart across snapshots, then the digest's headline + decision + next-step. | *"It keeps history, so I can see drift over time — and it hands me one decision and one next move each week."* |
| **1:14–1:26** | Header **Run auditor** action | Click **Run auditor** (fast); show the views reload on completion. | *"This isn't a static export. I regenerate the truth live, right from the app."* |
| **1:26–1:30** | Back on **Portfolio**, point at the **tool** column | Rest on the Claude Code / Codex attribution. | *"And it knows which agent built what — because two of them work this portfolio under one control plane."* |

Total: **90 seconds**, six beats, one number that sticks (**49**).

---

## Optional extended cut (~2:30) — the coordination story

If the audience is technical and you have extra runway, append a second act that
shows the *control plane*, not just the dashboard:

| Time | What to show | Point |
|---|---|---|
| +0:00–0:25 | A terminal split: Claude Code on a `feat/...` branch in one repo, Codex on a `fix/...` branch in another. | Two autonomous agents, different lanes, same portfolio. |
| +0:25–0:50 | bridge-db handoff flow: a dispatched handoff being **picked up**, then **cleared** (via the MCP tools or the bridge markdown). | Work is shared state, not chat history — it survives session boundaries. |
| +0:50–1:10 | A blocked push to `main` (the pre-tool guard firing), then the same work landing via a **server-side merge**. | Safety is enforced at the boundary, not requested politely. |
| +1:10–1:30 | A **notification-hub** event arriving (macOS push) after a session completes. | Events are classified and routed deterministically — no LLM in the plumbing. |

---

## Recording checklist

- [ ] Artifacts regenerated today (`generated_at` is current in the header).
- [ ] Window at 1920×1080, menu-bar/desktop clutter hidden.
- [ ] Individual repo names blurred or kept off-frame; show aggregates.
- [ ] No terminal scrollback exposing absolute home paths, tokens, or hostnames.
- [ ] The number **49** is on screen and called out by voice.
- [ ] Closing line names both agents (Claude Code + Codex) and "one control plane."
- [ ] Final cut ≤ 90 seconds for the core demo.

---

*This plan drives PortfolioCommandCenter against a real
`portfolio-truth-latest.json` snapshot (schema 0.5.0). Keep individual repo names
out of the published frame — show the system's shape, not the portfolio's
contents.*
