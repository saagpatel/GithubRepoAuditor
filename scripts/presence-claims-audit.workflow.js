// scripts/presence-claims-audit.workflow.js
// External audit of the snapshot's SIX presence claims against on-disk ground truth.
// Stage 2 (verifier fan-out, Haiku — judges all 6 claims per repo in one read)
//   + Stage 3 (deterministic per-(repo,claim) tally) + Stage 4 (Sonnet synthesis).
// args = output of `python -m src.run_instructions_audit` ({ generated_at, workspace_root, records, errors }),
//   where each record carries snapshot_claims{} and tool_today{} dicts over the 6 fields.
export const meta = {
	name: "presence-claims-audit",
	description:
		"Audit the snapshot's 6 presence claims against on-disk ground truth",
	phases: [
		{
			title: "Verify",
			detail: "one Haiku subagent per repo judges all 6 claims from the files",
		},
		{
			title: "Synthesize",
			detail: "one Sonnet call writes the per-claim scorecard report",
		},
	],
};

const CLAIM_FIELDS = [
	"project_summary_present",
	"current_state_present",
	"stack_present",
	"run_instructions_present",
	"known_risks_present",
	"next_recommended_move_present",
];

// What each claim means, for the verifier (semantic judgment, not heading-matching).
const CLAIM_DEFS = {
	project_summary_present:
		"states what the project IS — its purpose or what it does (not merely its name/tagline)",
	current_state_present:
		"states where the project stands now — status, current phase, or what is done / in progress",
	stack_present:
		"names the technology stack — languages, frameworks, or key tools",
	run_instructions_present:
		"tells a developer how to run/start it — a run command, dev server, or build+run steps (dependency install alone does NOT count)",
	known_risks_present:
		"documents known risks, issues, limitations, or intentional constraints",
	next_recommended_move_present:
		"states the recommended next step / what to do next",
};

const CLAIM_VERDICT = {
	type: "object",
	additionalProperties: false,
	required: [
		"verdict",
		"evidence_in_primary",
		"evidence_quote",
		"evidence_location",
		"confidence",
	],
	properties: {
		verdict: { type: "boolean" },
		evidence_in_primary: { type: "boolean" },
		evidence_quote: { type: "string", maxLength: 240 },
		evidence_location: { type: "string" },
		confidence: { type: "string", enum: ["high", "med", "low"] },
	},
};

const VERIFIER_SCHEMA = {
	type: "object",
	additionalProperties: false,
	required: CLAIM_FIELDS,
	properties: Object.fromEntries(CLAIM_FIELDS.map((f) => [f, CLAIM_VERDICT])),
};

const { generated_at, records, errors } = args;

function verifierPrompt(rec) {
	const defs = CLAIM_FIELDS.map(
		(f, i) => `${i + 1}. ${f}: ${CLAIM_DEFS[f]}`,
	).join("\n");
	return [
		`You audit whether a project's docs genuinely document SIX things. Judge each independently from the files — you are NOT told the tool's answers.`,
		`Project: ${rec.project_key}`,
		`Directory (absolute): ${rec.abs_path}`,
		`The tool treats "${rec.primary_file_name}" as the PRIMARY context file; it may be absent.`,
		`Listed context files: ${JSON.stringify(rec.context_files)}.`,
		``,
		`Read the primary file (if present), README.md, and the other listed context files by absolute path under the directory. Then, for EACH of these six claims, decide whether the docs genuinely document it:`,
		defs,
		``,
		`For each claim return an object with:`,
		`- verdict: true if genuinely documented, else false (default false when uncertain).`,
		`- evidence_in_primary: true ONLY if the evidence is inside "${rec.primary_file_name}". If that file is absent or the evidence is only in README/another file, false.`,
		`- evidence_quote: the exact heading or sentence (<=240 chars) that documents it, or "" if absent.`,
		`- evidence_location: e.g. "CLAUDE.md §Usage" or "README §Status", or "" if absent.`,
		`- confidence: "high" | "med" | "low".`,
		`Return one object per claim, keyed by the exact field names above.`,
	].join("\n");
}

// --- Stage 3 tally logic (mirror of src/run_instructions_audit.py) ---
function assignBucket(toolToday, verdict, inPrimary) {
	if (toolToday === verdict) return verdict ? "agree_present" : "agree_absent";
	if (verdict && !toolToday)
		return inPrimary ? "fn_alias_gap" : "fn_blind_spot";
	return "fp_overclaim";
}
function assignDrift(snapshotClaim, toolToday, drifted) {
	if (snapshotClaim === toolToday) return "claim_same";
	return drifted ? "claim_changed_drift" : "claim_changed_nodrift";
}

phase("Verify");
const verified = await parallel(
	records.map(
		(rec) => () =>
			agent(verifierPrompt(rec), {
				label: `verify:${rec.project_key}`,
				phase: "Verify",
				model: "haiku",
				agentType: "Explore",
				schema: VERIFIER_SCHEMA,
			})
				.then((v) => ({ rec, v }))
				.catch(() => null),
	),
);

// Stage 3: one cell per (repo, claim).
const cells = [];
for (const item of verified.filter(Boolean)) {
	const { rec, v } = item;
	for (const claim of CLAIM_FIELDS) {
		const cv = v[claim];
		cells.push({
			project_key: rec.project_key,
			claim,
			primary_file_name: rec.primary_file_name,
			snapshot_claim: rec.snapshot_claims[claim],
			tool_today: rec.tool_today[claim],
			drifted: rec.drifted,
			verdict: cv.verdict,
			evidence_in_primary: cv.evidence_in_primary,
			evidence_quote: cv.evidence_quote,
			evidence_location: cv.evidence_location,
			confidence: cv.confidence,
			bucket: assignBucket(
				rec.tool_today[claim],
				cv.verdict,
				cv.evidence_in_primary,
			),
			drift_bucket: assignDrift(
				rec.snapshot_claims[claim],
				rec.tool_today[claim],
				rec.drifted,
			),
		});
	}
}

// Per-claim aggregates.
const perClaim = CLAIM_FIELDS.map((claim) => {
	const rows = cells.filter((c) => c.claim === claim);
	const counts = rows.reduce(
		(a, c) => ((a[c.bucket] = (a[c.bucket] || 0) + 1), a),
		{},
	);
	const dis = rows.filter((c) => !c.bucket.startsWith("agree"));
	const agree = rows.length - dis.length;
	return {
		claim,
		total: rows.length,
		agree,
		agreementRate: rows.length ? agree / rows.length : 0,
		counts,
		disagreements: dis.length,
	};
});

const repoCount = verified.filter(Boolean).length;
const disagreements = cells.filter((c) => !c.bucket.startsWith("agree"));
const totalCells = cells.length;
const overallAgree = totalCells - disagreements.length;
log(
	`Verified ${repoCount} repos × ${CLAIM_FIELDS.length} claims = ${totalCells} cells — ${disagreements.length} disagreements, overall ${(totalCells ? (overallAgree / totalCells) * 100 : 0).toFixed(0)}%`,
);

phase("Synthesize");
const synthesisPrompt = [
	`Write a markdown audit report for the snapshot's SIX presence claims. Return ONLY markdown, no preamble.`,
	`Snapshot generated_at=${generated_at}. Repos=${repoCount}, claims=${CLAIM_FIELDS.length}, cells=${totalCells}, overall agreement (verifier vs tool_today)=${(totalCells ? (overallAgree / totalCells) * 100 : 0).toFixed(0)}%.`,
	`Per-claim aggregates (JSON): ${JSON.stringify(perClaim, null, 2)}`,
	`Unresolved-path errors: ${JSON.stringify(errors)}.`,
	`All disagreement cells (JSON): ${JSON.stringify(disagreements, null, 2)}`,
	``,
	`Required sections:`,
	`1. Headline — repos, claims, overall agreement; a per-claim scorecard table: claim | agreement% | agree | fn_blind_spot | fn_alias_gap | fp_overclaim.`,
	`2. Weakest claims — which claims have the lowest agreement and the dominant failure bucket for each.`,
	`3. Disagreement details — grouped by claim; each row: project_key, bucket, evidence_quote, evidence_location, confidence, drifted.`,
	`4. Drift summary — cells where drift_bucket != "claim_same", split claim_changed_drift vs claim_changed_nodrift.`,
	`5. Prescriptive fixes — per claim. fn_blind_spot → content lives in a non-primary file (usually README): recommend choose_primary_context_file consider README.md. fn_alias_gap → the verifier found it in the PRIMARY file but the tool missed it; treat these as REVIEW CANDIDATES, not confirmed alias bugs. The verifier judges human-readability, so it may count text the tool's markdown parser correctly excluded. For each, cite the heading and list causes to check by hand: (a) the alias may ALREADY exist (verify before proposing it), (b) the section may be trapped in malformed markdown such as an unclosed code fence swallowing later headings, (c) the content may be below the tool's non-trivial-text threshold, (d) the verifier may have over-credited boilerplate. Only propose an alias addition for a heading plainly outside a normal alias set. fp_overclaim → flag the over-claim.`,
].join("\n");

const report = await agent(synthesisPrompt, {
	label: "synthesis",
	phase: "Synthesize",
	model: "sonnet",
});

return {
  report,
  stats: {
    repos: repoCount,
    claims: CLAIM_FIELDS.length,
    cells: totalCells,
    overallAgreement: totalCells ? overallAgree / totalCells : 0,
    perClaim,
  },
  cells,
}
