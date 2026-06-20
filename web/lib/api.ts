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
export async function fetchReport(username: string): Promise<Report> {
	const url = `${API_BASE}/api/report/${encodeURIComponent(username)}`;

	let resp: Response;
	try {
		resp = await fetch(url, { headers: { Accept: "application/json" } });
	} catch {
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
