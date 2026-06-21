/** Return `url` only if it is a safe http(s) link, else undefined.
 *
 * Report strings (e.g. a repo's html_url) come from the GitHub API via the
 * relay; an unexpected `javascript:`/`data:` scheme would otherwise become an
 * href-based XSS vector. Callers render plain text when this returns undefined.
 */
export function safeHttpUrl(
	url: string | null | undefined,
): string | undefined {
	if (!url) return undefined;
	try {
		const parsed = new URL(url);
		return parsed.protocol === "https:" || parsed.protocol === "http:"
			? url
			: undefined;
	} catch {
		return undefined;
	}
}
