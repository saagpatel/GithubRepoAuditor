import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { fetchReport, ReportError } from "../lib/api.ts";

const report = {
	username: "octocat",
	mode: "api-only",
	fidelity_note: "API metadata only",
	repo_count: 1,
	repos: [
		{
			metadata: {
				name: "hello-world",
				full_name: "octocat/hello-world",
				description: null,
				language: "TypeScript",
				html_url: "https://github.com/octocat/hello-world",
				stars: 12,
				forks: 2,
				archived: false,
				fork: false,
				pushed_at: null,
			},
			analyzer_results: [],
			overall_score: 0.8,
			grade: "B",
			completeness_tier: "standard",
			flags: ["has-license"],
			action_candidates: [
				{
					key: "add-tests",
					title: "Add tests",
					action: "Add a test suite",
					lens: "quality",
					effort: "medium",
					confidence: 0.9,
					expected_lens_delta: 0.1,
					expected_tier_movement: "one tier",
					rationale: "No tests were found",
				},
			],
		},
	],
};

const originalFetch = globalThis.fetch;
afterEach(() => {
	globalThis.fetch = originalFetch;
});

async function getReport(payload) {
	globalThis.fetch = async () =>
		new Response(JSON.stringify(payload), {
			status: 200,
			headers: { "Content-Type": "application/json" },
		});
	return fetchReport("octocat");
}

async function getRawReport(body) {
	globalThis.fetch = async () =>
		new Response(body, {
			status: 200,
			headers: { "Content-Type": "application/json" },
		});
	return fetchReport("octocat");
}

test("accepts the fields rendered by ReportView and RepoCard", async () => {
	assert.deepEqual(await getReport(report), report);
});

test("reports malformed JSON as a ReportError", async () => {
	await assert.rejects(getRawReport("{"), (error) => {
		assert.ok(error instanceof ReportError);
		assert.equal(error.status, 502);
		assert.match(error.message, /unexpected response/i);
		return true;
	});
});

for (const [label, mutate] of [
	["missing report copy", (value) => delete value.fidelity_note],
	["invalid repo count", (value) => (value.repo_count = "1")],
	["empty repo object", (value) => (value.repos = [{}])],
	["missing rendered metadata", (value) => delete value.repos[0].metadata.name],
	["invalid score", (value) => (value.repos[0].overall_score = "high")],
	["invalid flags", (value) => (value.repos[0].flags = [null])],
	["incomplete rendered fix", (value) => (value.repos[0].action_candidates = [{ key: "x" }])],
]) {
	test(`rejects malformed payload: ${label}`, async () => {
		const payload = structuredClone(report);
		mutate(payload);
		await assert.rejects(getReport(payload), (error) => {
			assert.ok(error instanceof ReportError);
			assert.equal(error.status, 502);
			assert.match(error.message, /unexpected response/i);
			return true;
		});
	});
}
