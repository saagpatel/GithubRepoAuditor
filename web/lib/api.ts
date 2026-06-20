import type { Report } from "./types";

const API_BASE = (
	process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8080"
).replace(/\/$/, "");

export class ReportError extends Error {
	constructor(
		message: string,
		readonly status: number,
	) {
		super(message);
		this.name = "ReportError";
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

	const data: unknown = await resp.json();
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

/** Minimal boundary check that the payload has the shape we render. */
function isReport(value: unknown): value is Report {
	if (typeof value !== "object" || value === null) return false;
	const v = value as Record<string, unknown>;
	return typeof v.username === "string" && Array.isArray(v.repos);
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
