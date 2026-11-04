"use client";

import { useEffect, useState } from "react";
import { fetchReport, ReportError } from "@/lib/api";
import type { Report } from "@/lib/types";
import ReportView from "./ReportView";

// A settled result remembers which username it belongs to, so a username change
// shows the loading state without resetting state inside the effect.
type Settled =
	| { phase: "done"; username: string; report: Report }
	| { phase: "error"; username: string; message: string };

/** Fetches and renders the report for `username` (client-side, with loading UX). */
export default function ReportLoader({ username }: { username: string }) {
	const [settled, setSettled] = useState<Settled | null>(null);

	useEffect(() => {
		const controller = new AbortController();
		fetchReport(username, controller.signal)
			.then((report) => setSettled({ phase: "done", username, report }))
			.catch((err: unknown) => {
				// Aborted on unmount / username change — drop it silently.
				if (controller.signal.aborted) return;
				let message = "Something went wrong. Try again.";
				if (err instanceof ReportError) {
					message = err.message;
				} else {
					console.error("Unexpected error fetching report:", err);
				}
				setSettled({ phase: "error", username, message });
			});
		return () => controller.abort();
	}, [username]);

	const state = settled?.username === username ? settled : null;
	if (state === null) {
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
