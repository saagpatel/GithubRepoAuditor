/* Local progressive enhancement for audit serve. No external runtime required. */
(function () {
	"use strict";

	const liveRegion = document.getElementById("audit-live-region");

	function announce(message) {
		if (!liveRegion) return;
		liveRegion.textContent = "";
		window.setTimeout(() => {
			liveRegion.textContent = message;
		}, 20);
	}

	function targetFor(trigger) {
		const selector = trigger.dataset.auditTarget;
		if (!selector) return null;
		if (selector.startsWith("closest ")) {
			return trigger.closest(selector.slice(8));
		}
		return document.querySelector(selector);
	}

	function focusResult(element) {
		if (!(element instanceof HTMLElement)) return;
		element.setAttribute("tabindex", "-1");
		element.focus({ preventScroll: true });
	}

	function updateCounts(scope, decision) {
		if (!scope || !decision) return;
		const pending = scope.querySelector('[data-audit-count="pending"]');
		const decided = scope.querySelector(`[data-audit-count="${decision}"]`);
		if (!pending || !decided) return;
		pending.textContent = String(Math.max(0, Number(pending.textContent) - 1));
		decided.textContent = String(Number(decided.textContent) + 1);
	}

	async function replaceFromResponse(trigger, response, succeeded = true) {
		const target = targetFor(trigger);
		if (!target) return;
		const source = await response.text();
		let html = source;
		const select = trigger.dataset.auditSelect;
		if (select) {
			const parsed = new DOMParser().parseFromString(source, "text/html");
			const selected = parsed.querySelector(select);
			if (!selected) throw new Error("The requested local view was incomplete.");
			html = selected.innerHTML;
		}
		let result = target;
		if (trigger.dataset.auditSwap === "outerHTML") {
			target.insertAdjacentHTML("afterend", html);
			const replacement = target.nextElementSibling;
			target.remove();
			focusResult(replacement);
			result = replacement;
		} else {
			target.innerHTML = html;
			focusResult(target);
		}
		announce(
			succeeded
				? trigger.dataset.auditSuccess || "Local view updated."
				: result?.textContent?.trim() || "The local action could not be verified.",
		);
	}

	async function submitLocalForm(form) {
		const target = targetFor(form);
		const countScope = form.closest("[data-audit-count-scope]");
		const decision = form.dataset.auditDecision;
		if (target) target.setAttribute("aria-busy", "true");
		try {
			const response = await fetch(form.action, {
				method: form.method || "POST",
				body: new FormData(form),
				headers: { "X-Audit-Request": "partial" },
			});
			if (!response.ok) {
				await replaceFromResponse(form, response, false);
				return;
			}
			await replaceFromResponse(form, response);
			updateCounts(countScope, decision);
		} catch (error) {
			announce(error instanceof Error ? error.message : "The local action failed.");
			if (target) {
				target.textContent = "The local action failed. Try again or reload this page.";
				focusResult(target);
			}
		} finally {
			if (target) target.removeAttribute("aria-busy");
		}
	}

	document.addEventListener("click", async (event) => {
		const trigger = event.target.closest("[data-audit-get]");
		if (!trigger) return;
		event.preventDefault();
		const target = targetFor(trigger);
		if (target) target.setAttribute("aria-busy", "true");
		try {
			const response = await fetch(trigger.dataset.auditGet);
			if (!response.ok) throw new Error(`Request failed (${response.status}).`);
			await replaceFromResponse(trigger, response);
		} catch (error) {
			announce(error instanceof Error ? error.message : "The local view could not be loaded.");
		} finally {
			if (target) target.removeAttribute("aria-busy");
		}
	});

	document.addEventListener("submit", (event) => {
		const form = event.target;
		if (!(form instanceof HTMLFormElement) || !form.matches("[data-audit-form]")) return;
		event.preventDefault();
		if (form.dataset.auditConfirm && !window.confirm(form.dataset.auditConfirm)) return;
		void submitLocalForm(form);
	});

	const runForm = document.querySelector("[data-audit-run-form]");
	if (runForm instanceof HTMLFormElement) {
		const storageKey = "audit-serve-active-run";
		const panel = document.getElementById("stream-panel");
		const output = document.getElementById("stream-output");
		const status = document.getElementById("run-status");
		const result = document.getElementById("run-result");
		const cancel = document.getElementById("cancel-run");
		const resume = document.getElementById("resume-run");
		let activeRun = null;
		let stream = null;

		function setRunStatus(message) {
			if (status) status.textContent = message;
			announce(message);
		}

		function showPanel() {
			if (panel) panel.hidden = false;
		}

		function finishRun(message) {
			setRunStatus(message);
			sessionStorage.removeItem(storageKey);
			if (cancel) cancel.disabled = true;
			if (resume) resume.hidden = true;
			activeRun = null;
		}

		function appendLine(line) {
			if (!output) return;
			output.textContent += `${line}\n`;
			output.scrollTop = output.scrollHeight;
		}

		function startStream(runId, cursor) {
			showPanel();
			activeRun = runId;
			sessionStorage.setItem(storageKey, runId);
			if (stream) stream.close();
			if (cancel) cancel.disabled = false;
			if (resume) resume.hidden = true;
			setRunStatus("Run in progress. Output is streaming.");
			stream = new EventSource(`/runs/new/stream/${encodeURIComponent(runId)}?after=${cursor}`);
			stream.onmessage = (event) => {
				appendLine(event.data);
				if (event.data.startsWith("[CANCELLED")) {
					stream.close();
					finishRun(`Run cancelled. ${event.data}`);
				} else if (event.data.startsWith("[DONE")) {
					stream.close();
					const succeeded = event.data.includes("rc=0");
					finishRun(`${succeeded ? "Run completed" : "Run failed"}. ${event.data}`);
				}
			};
			stream.onerror = () => {
				stream.close();
				setRunStatus("The stream disconnected. The run may still be active; resume to recover buffered output.");
				if (resume) resume.hidden = false;
			};
		}

		async function recover(runId) {
			showPanel();
			try {
				const response = await fetch(`/runs/new/status/${encodeURIComponent(runId)}`);
				if (!response.ok) throw new Error(`Recovery failed (${response.status}).`);
				const data = await response.json();
				const truncationNotice = "Earlier output was truncated from the bounded buffer.";
				const recoveredLines = data.truncated
					? [`[${truncationNotice}]`, ...data.lines]
					: data.lines;
				if (output) output.textContent = recoveredLines.length ? `${recoveredLines.join("\n")}\n` : "";
				if (data.status === "running") {
					startStream(runId, data.cursor);
					if (data.truncated) {
						setRunStatus(`Run in progress. ${truncationNotice}`);
					}
				} else {
					finishRun(
						`Recovered terminal state: ${data.status}, return code ${data.return_code}.` +
							(data.truncated ? ` ${truncationNotice}` : ""),
					);
				}
			} catch (error) {
				setRunStatus(error instanceof Error ? error.message : "Run recovery failed.");
			}
		}

		runForm.addEventListener("submit", async (event) => {
			event.preventDefault();
			if (!runForm.reportValidity()) return;
			const startButton = document.getElementById("start-run");
			if (startButton) startButton.disabled = true;
			if (result) result.textContent = "Starting the local audit process…";
			try {
				const response = await fetch(runForm.action, {
					method: "POST",
					body: new FormData(runForm),
				});
				const data = await response.json();
				if (!response.ok) throw new Error(data.detail || `Run start failed (${response.status}).`);
				if (output) output.textContent = "";
				if (result) result.textContent = `Run ${data.run_id.slice(0, 12)} started.`;
				focusResult(result);
				startStream(data.run_id, 0);
			} catch (error) {
				if (result) {
					result.textContent = error instanceof Error ? error.message : "The run could not start.";
					focusResult(result);
				}
			} finally {
				if (startButton) startButton.disabled = false;
			}
		});

		if (cancel) {
			cancel.addEventListener("click", async () => {
				if (!activeRun) return;
				cancel.disabled = true;
				setRunStatus("Cancellation requested…");
				try {
					const response = await fetch(`/runs/new/cancel/${encodeURIComponent(activeRun)}`, {
						method: "POST",
					});
					if (!response.ok) throw new Error(`Cancellation failed (${response.status}).`);
				} catch (error) {
					setRunStatus(error instanceof Error ? error.message : "Cancellation failed.");
					cancel.disabled = false;
				}
			});
		}

		if (resume) {
			resume.addEventListener("click", () => {
				if (activeRun) void recover(activeRun);
			});
		}

		const storedRun = sessionStorage.getItem(storageKey);
		if (storedRun) {
			activeRun = storedRun;
			showPanel();
			if (resume) resume.hidden = false;
			setRunStatus("A previous local run can be recovered.");
		}
	}

	window.auditServe = { announce };
})();
