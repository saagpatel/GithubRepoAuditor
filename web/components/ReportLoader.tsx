"use client";

import { useEffect, useState } from "react";
import { fetchReport, ReportError } from "@/lib/api";
import type { Report } from "@/lib/types";
import ReportView from "./ReportView";

type State =
	| { phase: "loading" }
	| { phase: "done"; report: Report }
	| { phase: "error"; message: string };

/** Fetches and renders the report for `username` (client-side, with loading UX). */
export default function ReportLoader({ username }: { username: string }) {
	const [state, setState] = useState<State>({ phase: "loading" });

	useEffect(() => {
		const controller = new AbortController();
		setState({ phase: "loading" });
		fetchReport(username, controller.signal)
			.then((report) => setState({ phase: "done", report }))
			.catch((err: unknown) => {
				// Aborted on unmount / username change — drop it silently.
				if (controller.signal.aborted) return;
				let message = "Something went wrong. Try again.";
				if (err instanceof ReportError) {
					message = err.message;
				} else {
					console.error("Unexpected error fetching report:", err);
				}
				setState({ phase: "error", message });
			});
		return () => controller.abort();
	}, [username]);

	if (state.phase === "loading") {
		return (
			<div className="loading" role="status" aria-live="polite">
				<span className="dot" />
				Scoring @{username} from the GitHub API — no cloning, ~10s…
			</div>
		);
	}
	if (state.phase === "error") {
		return (
			<div className="error" role="alert">
				{state.message}
			</div>
		);
	}
	return <ReportView report={state.report} />;
}
