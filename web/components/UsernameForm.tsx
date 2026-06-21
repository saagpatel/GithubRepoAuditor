"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState, useTransition } from "react";

/** Username input that routes to the shareable report URL on submit. */
export default function UsernameForm({
	initial = "",
	cta = "Score it",
}: {
	initial?: string;
	cta?: string;
}) {
	const [username, setUsername] = useState(initial);
	// useTransition's pending flag tracks the navigation and resets itself, so
	// the button never gets stuck disabled if the push is cancelled.
	const [submitting, startTransition] = useTransition();
	const router = useRouter();

	function onSubmit(e: FormEvent<HTMLFormElement>) {
		e.preventDefault();
		const handle = username.trim().replace(/^@/, "");
		if (!handle) return;
		startTransition(() => {
			router.push(`/u/${encodeURIComponent(handle)}`);
		});
	}

	return (
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
			<button className="go" type="submit" disabled={submitting}>
				{submitting ? "Opening…" : cta}
			</button>
		</form>
	);
}
