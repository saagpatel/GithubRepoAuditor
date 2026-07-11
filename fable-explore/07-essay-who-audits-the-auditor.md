# Who Audits the Auditor?

*DRAFT for saagarpatel.dev/writing. Companion to "A Portfolio Is an Observability Problem"
(the pipeline's case) and "The Ghost in the Tauri Repos" (the evidence posture). This one
covers the part both of them skip: why the truth pipeline itself can't be trusted for free.*

*Suggested description: The tool that tells me the truth about my repos is also software,
and software rots. These are the receipts a truth pipeline owes you before you believe it.*

---

One morning the number of repos marked "decision needed" went from thirty-two to one.

Nothing got fixed overnight. No burst of documentation, no heroic triage session while I
slept. A scheduled regeneration ran, the way it was supposed to, and the fresh snapshot
disagreed with the stale one I'd been reading. For about a day I had been treating a
day-old file as the present tense, and the present tense had moved.

That stung more than a normal bug, because of what the file was. I built a portfolio
auditor on the premise that repositories misreport their own state: the README frozen at
peak confidence, the screenshot that can never go stale, the signed binary radiating a
completion it no longer has. The auditor's whole job is to route around those surfaces and
compute verdicts from evidence. And there I was, believing a surface. The snapshot is
JSON, structured and versioned and machine-readable, and none of that kept it current. A
truth file doesn't rot visibly. It just keeps on being well-formatted, confident as the
day it was written, while the world walks away from it.

The ghost repos lie one level down. The audit artifact can tell the same lie one level up.

## Four failures, four receipts

So the last few months of work on the auditor haven't gone into smarter verdicts. They've
gone into making the pipeline prove things about itself. Each proof exists because
something specific went wrong or nearly did.

**Consumers re-deriving the math.** The truth snapshot feeds a command center, a weekly
digest, a public page, an MCP server. Early on, some of those consumers computed their own
portfolio aggregates from the per-repo rows: count the elevated repos here, sum the alerts
there. Each one re-implemented a little of the auditor's judgment, and each
re-implementation was free to drift. There's now a comment in the schema that calls
consumer re-derivation the number one drift risk, and the fix that comment defends is
boring and total: the producer computes every rollup and ships it inside the artifact.
Consumers read aggregates. They don't get to have opinions about how aggregates are made.

**Publishes without provenance.** The nightly job that regenerates truth is itself a
program running unattended, and an unattended program can run from the wrong place. A
stale checkout. A dirty working tree with half an experiment in it. A detached HEAD from
last week's debugging. Any of those would publish a snapshot that looks perfect and
describes nothing. So the scheduled path now demands producer evidence: before publishing,
the job proves it's running from the canonical repository, on a clean tree, at the exact
commit it expected, and it embeds that evidence in the snapshot it writes. Then it checks
again, after the write, that the commit hasn't moved mid-publish. A snapshot without
evidence gets refused outright. Paranoid? The failure it prevents is the quiet kind, the
exit-code-zero kind, the kind you discover weeks later when a verdict doesn't smell right
and you can't say which code produced it.

**Carried data re-dating itself.** One of the auditor's sources is a project database
that isn't always reachable. When it isn't, the pipeline carries the previous run's
values forward, which is fine, and stamps them into a fresh artifact with a fresh
generation time, which is not. Carried-forward data inherits the new timestamp and
quietly launders its age. The fix walks the chain of predecessor artifacts back to the
oldest real observation and reports that date instead. Carrying stale data is honest as
long as the data admits how stale it is; the staleness was always forgivable, and the
fresh coat of paint never was.

**Silent exclusions.** Workspace discovery once came close to counting a folder of
backups as a fleet of new projects, which would have poisoned every aggregate downstream
while looking, on the surface, like growth. Now every directory the scan skips is
classified with a stable reason, and the counts of what was excluded, and why, are
published in the artifact next to what was included. An exclusion you can't see is
indistinguishable from a blind spot. An exclusion with a ledger entry is a decision.

## The linter at the seams

Underneath those four is a duller guard that runs across the whole operator system: a
seam linter that checks the truth artifact's freshness against a staleness budget,
verifies the published rollups still match the rows they summarize, confirms the schema
version is the one consumers pinned, and resolves project identities across the other
databases in the system, because the same project drifting into three names across three
tools is how cross-system truth dies in practice. None of this is clever. All of it is
the auditor pointing its own posture at itself.

Here's the ratio that tells you where this ends up. In the current snapshot, each repo's
record carries seven fields of risk verdict and thirty-four fields of provenance. The
receipts outweigh the judgment by almost five to one. Nobody set that ratio as a target;
it's just what accumulates when every value in the record has to name where it came from.
An audit you can't audit is an opinion with a timestamp.

## Where the chain bottoms out

I want to be honest about the limit, because the logic here recurses and the recursion
has to stop somewhere. The producer evidence trusts git to report HEAD truthfully. The
seam linter trusts the filesystem timestamps it reads. The whole arrangement trusts that
the linter itself runs, which is one more scheduled job that could silently not. You
cannot verify all the way down; at some point every verification chain ends at a thing
you simply trust. The discipline isn't eliminating that bottom layer. It's choosing it
on purpose, keeping it small, and knowing exactly which layer it is, so that when
something smells wrong you know where suspicion stops being useful.

## The rule, one level up

The observability essay ended on a short list of rules I still stand by, and two of them
matter here: if a surface matters, give it a source of truth, and if it can drift, make
the drift visible. This essay is those rules applied to their own output. A source of truth is a surface too. It matters more than the
surfaces it summarizes, drifts just as happily, and misreports with far more authority,
because you built it precisely so you could stop double-checking.

So it owes you more than the things it watches, and what it owes is specific. Proof of
when it was made. Proof of who made it and from what. A ledger of what it left out. An
honest age on anything it carried forward instead of observed. And aggregates computed
once, at the source, so no downstream reader has to re-derive judgment and get it subtly
wrong.

My repos don't get to self-report. The file that says so doesn't either.
