// scripts/run-instructions-audit.workflow.js
// External audit of the snapshot's run_instructions_present claim.
// Stage 2 (verifier fan-out, Haiku) + Stage 3 (deterministic tally) + Stage 4 (Sonnet synthesis).
// args = output of `python -m src.run_instructions_audit` ({ generated_at, workspace_root, records, errors }).
export const meta = {
	name: "run-instructions-audit",
	description:
		"Audit snapshot run_instructions_present claim against on-disk ground truth",
	phases: [
		{
			title: "Verify",
			detail: "one Haiku subagent per pilot repo reads files and judges",
		},
		{
			title: "Synthesize",
			detail: "one Sonnet call writes the markdown report",
		},
	],
};

const VERIFIER_SCHEMA = {
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

const { generated_at, records, errors } = args;

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

const rows = verified.filter(Boolean).map(({ rec, v }) => ({
	project_key: rec.project_key,
	primary_file_name: rec.primary_file_name,
	snapshot_claim: rec.snapshot_claim,
	tool_today: rec.tool_today,
	drifted: rec.drifted,
	...v,
	bucket: assignBucket(rec.tool_today, v.verdict, v.evidence_in_primary),
	drift_bucket: assignDrift(rec.snapshot_claim, rec.tool_today, rec.drifted),
}));

const counts = rows.reduce(
	(acc, r) => ((acc[r.bucket] = (acc[r.bucket] || 0) + 1), acc),
	{},
);
const disagreements = rows.filter((r) => !r.bucket.startsWith("agree"));
const agreementRate = rows.length
	? (rows.length - disagreements.length) / rows.length
	: 0;
log(
	`Verified ${rows.length} repos — ${disagreements.length} disagreements, agreement ${(agreementRate * 100).toFixed(0)}%`,
);

phase("Synthesize");
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
].join("\n");

const report = await agent(synthesisPrompt, {
	label: "synthesis",
	phase: "Synthesize",
	model: "sonnet",
});

return {
  report,
  stats: {
    verified: rows.length,
    agreementRate,
    counts,
    disagreements: disagreements.length,
    errors: errors.length,
  },
  rows,
}
