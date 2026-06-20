"use client";

import { type FormEvent, useState } from "react";
import { fetchReport, ReportError } from "@/lib/api";
import type { Report } from "@/lib/types";
import ReportView from "./ReportView";

type Status =
	| { phase: "idle" }
	| { phase: "loading" }
	| { phase: "done"; report: Report }
	| { phase: "error"; message: string };

export default function ReportExplorer() {
	const [username, setUsername] = useState("");
	const [status, setStatus] = useState<Status>({ phase: "idle" });

	async function onSubmit(e: FormEvent<HTMLFormElement>) {
		e.preventDefault();
		const handle = username.trim().replace(/^@/, "");
		if (!handle || status.phase === "loading") return;

		setStatus({ phase: "loading" });
		try {
			const report = await fetchReport(handle);
			setStatus({ phase: "done", report });
		} catch (err) {
			let message = "Something went wrong. Try again.";
			if (err instanceof ReportError) {
				message = err.message;
			} else {
				// Unexpected (e.g. malformed JSON) — keep a diagnostic breadcrumb.
				console.error("Unexpected error fetching report:", err);
			}
			setStatus({ phase: "error", message });
		}
	}

	const loading = status.phase === "loading";

	return (
		<>
			<form className="form-row" onSubmit={onSubmit}>
				<label className="input-shell">
					<span className="at">@</span>
					<input
						type="text"
						name="username"
						placeholder="github-username"
						autoComplete="off"
						autoCapitalize="off"
						spellCheck={false}
						value={username}
						onChange={(e) => setUsername(e.target.value)}
						aria-label="GitHub username"
					/>
				</label>
				<button className="go" type="submit" disabled={loading}>
					{loading ? "Scanning…" : "Score it"}
				</button>
			</form>

			{status.phase === "loading" && (
				<div className="loading" role="status" aria-live="polite">
					<span className="dot" />
					Reading the GitHub API and scoring each repo — no cloning, ~10s…
				</div>
			)}

			{status.phase === "error" && (
				<div className="error" role="alert">
					{status.message}
				</div>
			)}

			{status.phase === "done" && <ReportView report={status.report} />}
		</>
	);
}
