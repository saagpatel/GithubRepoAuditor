import type { Report } from "./types";

const API_BASE = (
	process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8080"
).replace(/\/$/, "");

export class ReportError extends Error {
	readonly status: number;

	constructor(
		message: string,
		status: number,
	) {
		super(message);
		this.name = "ReportError";
		this.status = status;
	}
}

/** Fetch a clone-free portfolio report for `username` from the FastAPI engine. */
export async function fetchReport(
	username: string,
	signal?: AbortSignal,
): Promise<Report> {
	const url = `${API_BASE}/api/report/${encodeURIComponent(username)}`;

	let resp: Response;
	try {
		resp = await fetch(url, {
			headers: { Accept: "application/json" },
			signal,
		});
	} catch (err) {
		// A caller-initiated abort isn't an error to surface — rethrow it so the
		// effect cleanup can swallow it rather than showing a failure message.
		if (err instanceof DOMException && err.name === "AbortError") throw err;
		throw new ReportError(
			"Could not reach the report service. Is the API running?",
			0,
		);
	}

	if (!resp.ok) {
		throw new ReportError(messageForStatus(resp.status, username), resp.status);
	}

	let data: unknown;
	try {
		data = await resp.json();
	} catch {
		throw new ReportError(
			"The report service returned an unexpected response.",
			502,
		);
	}
	if (!isReport(data)) {
		throw new ReportError(
			"The report service returned an unexpected response.",
			502,
		);
	}
	return data;
}

export type WaitlistResult = "joined" | "already_joined";

/** Submit an email to the monitoring waitlist. `source` is optional context. */
export async function joinWaitlist(
	email: string,
	source?: string,
): Promise<WaitlistResult> {
	let resp: Response;
	try {
		resp = await fetch(`${API_BASE}/api/waitlist`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ email, source }),
		});
	} catch {
		throw new ReportError("Could not reach the service. Try again.", 0);
	}
	if (!resp.ok) {
		if (resp.status === 422) {
			throw new ReportError("Enter a valid email address.", 422);
		}
		if (resp.status === 429) {
			throw new ReportError("Too many requests — try again shortly.", 429);
		}
		throw new ReportError("Something went wrong. Try again.", resp.status);
	}
	const data = (await resp.json()) as { status?: string };
	return data.status === "already_joined" ? "already_joined" : "joined";
}

/** Validate the fields read by ReportView and RepoCard before rendering. */
function isReport(value: unknown): value is Report {
	if (typeof value !== "object" || value === null) return false;
	const v = value as Record<string, unknown>;
	return (
		typeof v.username === "string" &&
		typeof v.fidelity_note === "string" &&
		Number.isInteger(v.repo_count) &&
		(v.repo_count as number) >= 0 &&
		Array.isArray(v.repos) &&
		v.repo_count === v.repos.length &&
		v.repos.every(isRepoAudit)
	);
}

function isRepoAudit(value: unknown): boolean {
	if (typeof value !== "object" || value === null) return false;
	const repo = value as Record<string, unknown>;
	return (
		isRecord(repo.metadata) &&
		typeof repo.metadata.name === "string" &&
		typeof repo.metadata.full_name === "string" &&
		isNullableString(repo.metadata.description) &&
		isNullableString(repo.metadata.language) &&
		typeof repo.metadata.html_url === "string" &&
		number(repo.metadata.stars) &&
		Number.isInteger(repo.metadata.stars) &&
		repo.metadata.stars >= 0 &&
		number(repo.metadata.forks) &&
		Number.isInteger(repo.metadata.forks) &&
		repo.metadata.forks >= 0 &&
		typeof repo.metadata.archived === "boolean" &&
		typeof repo.metadata.fork === "boolean" &&
		isNullableString(repo.metadata.pushed_at) &&
		number(repo.overall_score) &&
		repo.overall_score >= 0 &&
		repo.overall_score <= 1 &&
		typeof repo.grade === "string" &&
		Array.isArray(repo.flags) &&
		repo.flags.every((flag) => typeof flag === "string") &&
		Array.isArray(repo.action_candidates) &&
		repo.action_candidates.every(isActionCandidate)
	);
}

function isActionCandidate(value: unknown): boolean {
	if (!isRecord(value)) return false;
	return (
		typeof value.key === "string" &&
		typeof value.title === "string" &&
		typeof value.action === "string" &&
		number(value.expected_lens_delta) &&
		typeof value.effort === "string" &&
		typeof value.expected_tier_movement === "string"
	);
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function number(value: unknown): value is number {
	return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
	return value === null || typeof value === "string";
}

function messageForStatus(status: number, username: string): string {
	switch (status) {
		case 404:
			return `No GitHub user named "${username}" was found.`;
		case 422:
			return "That doesn't look like a valid GitHub username.";
		case 429:
			return "We're being rate-limited by GitHub right now. Try again in a minute.";
		case 502:
			return "GitHub is having a moment. Try again shortly.";
		default:
			return `Something went wrong (HTTP ${status}).`;
	}
}
