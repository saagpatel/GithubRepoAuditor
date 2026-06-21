"use client";

import { type FormEvent, useState } from "react";
import { joinWaitlist, ReportError } from "@/lib/api";

type State =
	| { phase: "idle" }
	| { phase: "submitting" }
	| { phase: "done"; already: boolean }
	| { phase: "error"; message: string };

/** Email capture for the monitoring waitlist — the "earn the tier" signal. */
export default function WaitlistForm({ source }: { source?: string }) {
	const [email, setEmail] = useState("");
	const [state, setState] = useState<State>({ phase: "idle" });

	async function onSubmit(e: FormEvent<HTMLFormElement>) {
		e.preventDefault();
		const value = email.trim();
		if (!value || state.phase === "submitting") return;
		setState({ phase: "submitting" });
		try {
			const result = await joinWaitlist(value, source);
			setState({ phase: "done", already: result === "already_joined" });
		} catch (err: unknown) {
			const message =
				err instanceof ReportError ? err.message : "Something went wrong.";
			if (!(err instanceof ReportError)) console.error(err);
			setState({ phase: "error", message });
		}
	}

	if (state.phase === "done") {
		return (
			<p className="waitlist-done" role="status">
				{state.already
					? "You're already on the list — we'll be in touch."
					: "You're on the list. We'll email you when monitoring ships."}
			</p>
		);
	}

	const submitting = state.phase === "submitting";
	return (
		<form className="waitlist" onSubmit={onSubmit}>
			<div className="waitlist-copy">
				<strong>Want this tracked over time?</strong> Get notified when
				portfolio monitoring + trend alerts ship.
			</div>
			<div className="waitlist-row">
				<input
					type="email"
					name="email"
					placeholder="you@example.com"
					autoComplete="email"
					value={email}
					onChange={(e) => setEmail(e.target.value)}
					aria-label="Email for the monitoring waitlist"
					required
				/>
				<button type="submit" disabled={submitting}>
					{submitting ? "Joining…" : "Notify me"}
				</button>
			</div>
			{state.phase === "error" && (
				<div className="error" role="alert">
					{state.message}
				</div>
			)}
		</form>
	);
}
