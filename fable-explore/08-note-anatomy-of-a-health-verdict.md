# Anatomy of a Health Verdict

*DRAFT for saagarpatel.dev/notes. Companion text to the Verdict Machine explainer;
embeds diagrams/truth-pipeline.svg. NOTE: the closing paragraph links the "Who Audits
the Auditor?" essay (07), so that essay should publish with or before this note. Suggested description: Every repo in my portfolio
gets a verdict from a chain of small, readable judgments. Here is the entire decision,
stage by stage, with the reason each rule exists.*

---

Every repo in my portfolio gets a verdict. Not a health score out of a hundred; a chain
of small judgments that ends in two words I can act on: an attention lane (where does
this sit in my week) and a risk tier (how expensive is neglecting it). I've written about
why the pipeline exists and what it refuses to believe. This note is the wiring: the
entire decision, stage by stage, with the reason each rule is shaped the way it is. If
you'd rather drive it than read it, the [Verdict Machine](/verdict-machine) runs these
exact functions live.

## Stage 1: is it alive?

The evidence is the git log: when did the last commit land. For directories without git
history, the newest modification time of a file that counts, where "counts" means source
files and manifests, with vendor directories, dotfiles, and symlinks filtered out so a
`node_modules` refresh can't fake a pulse. Fourteen days or newer is active, thirty is
recent, older is stale. Archived anywhere (GitHub, declared lifecycle, archive path)
short-circuits everything.

Two deliberate oddities. Uncommitted work doesn't count: if the repo has commit history,
the commit date wins, so forty modified files sitting on a sixty-day-old commit read as
plain stale. That's the honest reading (work isn't real until it's committed) and also a
known blind spot (stalled-mid-change is a more urgent state than resting, and the
pipeline currently can't see the difference). And the thresholds are universal. A tool
you touch quarterly spends most of its life "stale" through no fault of its own. Both are
on the improvement list; neither is fatal, because of what happens next.

## Stage 2: the vocabulary move

Stale doesn't stay stale. The registry immediately re-files it as *parked*. That's not a
euphemism; it's a deliberate shift from a judgment word to an attention word. The system
doesn't need to decide whether a quiet repo is dying or done, which it can't know. It
needs to decide whether the repo is asking for my time this week, which it can.

## Stage 3: does it explain itself?

Every repo owes its future reader six answers: what this is, its current state, the
stack, how to run it, the known risks, and the next recommended move. The checker looks
for those six sections (generous about heading aliases, and a real lead paragraph counts
as the summary) in the repo's context file or its README. No file and no README is
*none*. Any section missing is *boilerplate*. All six present is *minimum-viable*, and
supporting artifacts like a handoff or roadmap upgrade that to *standard* or *full*.

The contract checks presence, not truth. A Current State section that's beautifully
written and wrong sails through, and I've written a whole essay about repos that lie
well. The rule is shaped this way because presence is the largest claim the tool can
verify without guessing: cheap, deterministic, and wrong only in legible ways. A section
hiding under an unconventional heading reads as missing, which the missing-fields list
makes easy to spot and one heading-edit to fix. The truth-checking ambition is real, and
it belongs in a separate, more suspicious instrument; it isn't built yet.

## Stage 4: what did I say I'd do with it?

Observation runs out here. A quiet repo with a perfect README might be finished or
abandoned, and no scanner can tell you which, because the difference lives in my head.
So intent is a first-class input: a catalog file declares, per repo, its operating path
(maintain, finish, archive, or experiment), its criticality, its category. Declarations
resolve through an explicit precedence order: a repo-specific entry beats its group's
entry, which beats the portfolio default, which beats the old registry, which beats the
Notion database. Every resolved value records which source supplied it.

## Stage 5: should the system trust its own advice?

My favorite stage, and the one that took longest to see clearly. Before routing
attention, the pipeline audits its own footing. Concerns accumulate: no operating path
declared, declared program and disposition pointing different directions, no explicit
catalog entry, context too weak for guidance to stand on. Any hard concern drops path
confidence to low, and low confidence forces an override called *investigate*.

Read that override carefully, because it isn't aimed at the repo. It's the system
declaring that *it* doesn't know enough to advise me. Weak context doesn't get a scolding
about documentation hygiene; it gets "path guidance can't stand on its own yet." The
verdict machinery treats its own confidence as a first-class output, which is rarer than
it should be.

## Stage 6: what does neglect cost?

Risk is a list of named factors, not a number: weak context on an active repo, the
investigate override, no declared path, missing run instructions, undocumented risks on
a high-criticality repo, open high-severity alerts. Three or more factors is elevated.
One specific pair (weak context plus investigate, together on an active repo) elevates
on its own, because that combination means the system is flying blind on something that's
moving. A single open critical CVE force-elevates regardless, so one bad alert can't
hide behind an otherwise clean record.

The tier I'm proudest of is *deferred*: archived repos, and stale repos not on a
maintain path, are explicitly excused from risk accounting. Permission to ignore is a
real output, and it's what keeps 170 repos governable by one person; the alternative is
a wall of amber that trains you to stop looking.

## Stage 7: the ladder

The verdict lands last. Attention lane is a strict priority ladder, first match wins:
archived, then experiment, then parked, then decision-needed, then the active lanes,
then manual-only as the default bucket for anything alive that didn't match a stronger
rung. Three things about it are worth stealing.

Decision-needed fires on the investigate override, on a missing operating path, or on an
open security risk. In practice it's the "I can't advise you here" lane, and clearing it
almost never means writing code. It means answering the six questions from stage 3.

Security hijacks the ladder. A repo can be active, maintained, fully documented, high
confidence, and one open critical alert from stage 6 still drags it into decision-needed.
The system trusts its guidance about the repo and *still* demands a human decision,
because those are different questions.

And manual-only, the default bucket, currently holds about half my estate. That's an
honest number, not a proud one: the catch-all lane is where categorization debt piles
up, and a lane that holds the majority is closer to a fact about the distribution than a
signal about any repo in it.

## Why there's no score

Every stage above could be multiplied into a 0-to-100 health score, and the result would
look more professional and mean less. A score is a verdict you can only accept or
reject. A factor list, a concern list, and a rationale string make a verdict you can
*argue with*: when the machine surprises you, there's a specific line to disagree with,
and the disagreement usually teaches you something about either the repo or the rule.
That's the property I'd tell anyone building one of these to protect. A verdict you can
argue with beats a score you can only accept.

## The whole flow

![How the truth pipeline flows](/diagrams/truth-pipeline.svg)

One structural note the diagram makes visible: the artifact in the middle carries its own
receipts (who produced it, what was excluded, rollups computed at the source so
consumers can't drift), and a linter checks the artifact's seams continuously. That half
of the story, the part where the auditor has to prove *itself*, is its own essay.
