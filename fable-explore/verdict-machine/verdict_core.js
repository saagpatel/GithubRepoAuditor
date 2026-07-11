/*
 * verdict_core.js — faithful JavaScript port of GithubRepoAuditor's verdict cascade.
 *
 * Source of truth (main @ f58ad43):
 *   src/portfolio_truth_reconcile.py  (_activity_status_for, _registry_status_for,
 *                                      _attention_state_for, orchestration order)
 *   src/portfolio_pathing.py          (build_operating_path_entry, resolve_declared_operating_path)
 *   src/portfolio_risk.py             (build_risk_entry)
 *   src/portfolio_context_contract.py (context-quality classification tail of
 *                                      analyze_project_context)
 *
 * Every branch, threshold, and rationale string is ported verbatim and verified by the
 * golden harness in ./golden/ (thousands of input combinations diffed against the
 * actual Python functions). One deliberate abstraction: build_risk_entry takes
 * `is_strategic` (boolean) instead of checking display_name against the private
 * STRATEGIC_REPOS list, so no private repo names ship in this file. The golden harness
 * proves the boolean is equivalent to set membership.
 *
 * Works as a classic browser script (defines window.VerdictCore) and as a CJS module.
 */

((root, factory) => {
	const api = factory();
	if (typeof module !== "undefined" && module.exports) module.exports = api;
	else root.VerdictCore = api;
})(typeof self !== "undefined" ? self : globalThis, () => {
	// ---- constants (portfolio_pathing.py / portfolio_risk.py / context contract) ----

	const VALID_OPERATING_PATHS = new Set([
		"maintain",
		"finish",
		"archive",
		"experiment",
	]);
	const INVESTIGATE_OVERRIDE = "investigate";
	const ACTIVE_STATUSES = new Set(["active", "recent"]);
	const WEAK_CONTEXT = new Set(["none", "boilerplate"]);

	const STANDARD_SIGNAL_FILES = new Set([
		"IMPLEMENTATION-ROADMAP.md",
		"RESUMPTION-PROMPT.md",
		"HANDOFF.md",
		"STATUS.md",
		"PROJECT.md",
		"PLAN.md",
	]);
	const FULL_SIGNAL_FILES = new Set([
		"DISCOVERY-SUMMARY.md",
		"IMPLEMENTATION-ROADMAP.md",
		"RESUMPTION-PROMPT.md",
		"HANDOFF.md",
	]);
	const SUPPORTING_CONTEXT_FILES = new Set([
		"DISCOVERY-SUMMARY.md",
		"IMPLEMENTATION-ROADMAP.md",
		"RESUMPTION-PROMPT.md",
		"HANDOFF.md",
		"STATUS.md",
		"PROJECT.md",
		"PLAN.md",
		"ROADMAP.md",
		"NOTES.md",
	]);

	// Order matters: mirrors CONTEXT_SECTION_ALIASES dict order.
	const REQUIRED_SECTION_ORDER = [
		"project_summary",
		"current_state",
		"stack",
		"run_instructions",
		"known_risks",
		"next_recommended_move",
	];
	const SECTION_LABELS = {
		project_summary: "what the project is",
		current_state: "current state",
		stack: "stack",
		run_instructions: "how to run",
		known_risks: "known risks",
		next_recommended_move: "next recommended move",
	};

	const FACTOR_LABELS = {
		"weak-context-active": "weak context quality",
		"investigate-override": "investigate override active",
		"missing-operating-path": "no operating path declared",
		"missing-doctor-standard": "doctor standard not declared",
		"no-run-instructions": "run instructions missing",
		"undocumented-risks": "known risks not documented",
		"active-high-severity-alerts": "open high/critical security alerts",
	};

	const DEFERRED_ARCHIVED = {
		risk_tier: "deferred",
		risk_factors: [],
		risk_summary: "Archived or archive-path project.",
		doctor_gap: false,
		context_risk: false,
		path_risk: false,
		security_risk: false,
	};
	const DEFERRED_STALE = {
		risk_tier: "deferred",
		risk_factors: [],
		risk_summary: "Stale project not on maintain path.",
		doctor_gap: false,
		context_risk: false,
		path_risk: false,
		security_risk: false,
	};

	// ---- small helpers mirroring the Python ones ----

	function safeText(value) {
		return String(value == null ? "" : value).trim();
	}
	function normalizeKey(value) {
		return safeText(value).toLowerCase();
	}
	// Python str.title(): uppercase any alphabetic char that follows a non-alphabetic char.
	function pyTitle(text) {
		let out = "";
		let prevAlpha = false;
		for (const ch of text) {
			const isAlpha = /[a-zA-Z]/.test(ch);
			out += isAlpha ? (prevAlpha ? ch.toLowerCase() : ch.toUpperCase()) : ch;
			prevAlpha = isAlpha;
		}
		return out;
	}
	function labelize(value) {
		return pyTitle(value.replace(/-/g, " ").replace(/_/g, " "));
	}

	// ---- 1. activity: _activity_status_for (reconcile.py:960) ----
	// lastActivityDays: integer days since last meaningful activity, or null (= None).

	function activityStatusFor({
		lastActivityDays,
		lifecycleState = "",
		githubArchived = false,
	}) {
		if (githubArchived || lifecycleState === "archived") return "archived";
		if (lastActivityDays === null || lastActivityDays === undefined)
			return "stale";
		if (lastActivityDays <= 14) return "active";
		if (lastActivityDays <= 30) return "recent";
		return "stale";
	}

	// ---- 2. registry: _registry_status_for (reconcile.py:979) ----

	function registryStatusFor(activityStatus) {
		if (activityStatus === "stale") return "parked";
		return activityStatus;
	}

	// ---- 3. context quality: classification tail of analyze_project_context ----
	// Inputs are the section-presence booleans and file inventory that the Python
	// derives by parsing markdown; the classification below is the verbatim decision.
	// NOTE: hasReadme mirrors the contract's `has_readme = bool(readme_text.strip())` —
	// it means "README.md exists with non-empty text", not mere file existence.

	function contextQualityFor({
		primaryExists,
		hasReadme,
		sections, // {project_summary: bool, ..., next_recommended_move: bool}
		supportingFileNames = [], // top-level names, e.g. ["HANDOFF.md", "ROADMAP.md"]
		primaryContextFile = "AGENTS.md",
	}) {
		const missingFields = REQUIRED_SECTION_ORDER.filter(
			(f) => !sections[f],
		).map((f) => SECTION_LABELS[f]);
		const supporting = [...supportingFileNames]
			.filter(
				(n) => SUPPORTING_CONTEXT_FILES.has(n) && n !== primaryContextFile,
			)
			.sort();

		let contextQuality;
		if (!primaryExists && !hasReadme) {
			contextQuality = "none";
		} else if (missingFields.length > 0) {
			contextQuality = "boilerplate";
		} else {
			const supportNames = new Set(supporting);
			const intersects = (setA) => [...supportNames].some((n) => setA.has(n));
			if (supportNames.size >= 2 && intersects(FULL_SIGNAL_FILES)) {
				contextQuality = "full";
			} else if (intersects(STANDARD_SIGNAL_FILES)) {
				contextQuality = "standard";
			} else {
				contextQuality = "minimum-viable";
			}
		}
		return {
			context_quality: contextQuality,
			missing_fields: missingFields,
			supporting_context_files: supporting,
		};
	}

	// ---- 4+5. declared path + confidence: build_operating_path_entry (pathing.py:43) ----

	function resolveDeclaredOperatingPath(entry) {
		const explicitPath = normalizeKey(entry.operating_path);
		if (VALID_OPERATING_PATHS.has(explicitPath))
			return [explicitPath, "explicit-operating-path"];

		const intendedDisposition = normalizeKey(entry.intended_disposition);
		if (VALID_OPERATING_PATHS.has(intendedDisposition))
			return [intendedDisposition, "intended-disposition"];

		const explicitContract = Boolean(entry.has_explicit_entry);
		const maturityProgram = normalizeKey(entry.maturity_program);
		if (explicitContract && VALID_OPERATING_PATHS.has(maturityProgram))
			return [maturityProgram, "maturity-program"];

		return ["", ""];
	}

	function buildOperatingPathEntry(
		entry,
		{
			contextQuality = "",
			intentAlignment = "",
			archived = false,
			registryStatus = "",
			completenessTier = "",
			decisionQualityStatus = "",
		} = {},
	) {
		const [stablePath, pathSource] = resolveDeclaredOperatingPath(entry);
		const maturityProgram = normalizeKey(entry.maturity_program);
		const intendedDisposition = normalizeKey(entry.intended_disposition);
		const explicitContract = Boolean(entry.has_explicit_entry);
		const contextQ = normalizeKey(contextQuality);
		const intentA = normalizeKey(intentAlignment);
		const registryS = normalizeKey(registryStatus);
		const completenessT = normalizeKey(completenessTier);
		const decisionQ = normalizeKey(decisionQualityStatus);

		const concerns = [];
		const rationaleParts = [];

		if (stablePath) {
			rationaleParts.push(
				`Stable path is ${labelize(stablePath)} from ${pathSource.replace(/-/g, " ")}.`,
			);
		} else {
			concerns.push("missing-operating-path");
			rationaleParts.push("No stable operating path is declared yet.");
		}

		if (
			VALID_OPERATING_PATHS.has(maturityProgram) &&
			VALID_OPERATING_PATHS.has(intendedDisposition) &&
			maturityProgram !== intendedDisposition
		) {
			concerns.push("program-disposition-conflict");
			rationaleParts.push(
				"Declared maturity program and intended disposition point at different paths.",
			);
		}

		if (!explicitContract) {
			concerns.push("missing-explicit-contract");
			rationaleParts.push(
				"This repo is still relying on defaults or inferred portfolio intent.",
			);
		}

		if (intentA === "needs-review") {
			concerns.push("intent-needs-review");
			rationaleParts.push(
				"Current repo condition is no longer clearly aligned with the declared intent.",
			);
		}

		if (WEAK_CONTEXT.has(contextQ)) {
			concerns.push("weak-context");
			rationaleParts.push(
				"Context quality is still too weak for path guidance to stand on its own.",
			);
		}

		if (archived || registryS === "archived") {
			if (stablePath !== "archive") {
				concerns.push("archived-outside-archive-path");
				rationaleParts.push(
					"The repo currently looks archival, but the declared operating path is not archive.",
				);
			}
		} else if (
			(completenessT === "abandoned" || completenessT === "skeleton") &&
			(stablePath === "maintain" || stablePath === "finish")
		) {
			concerns.push("repo-state-below-path-bar");
			rationaleParts.push(
				"Current repo maturity is still below what the declared operating path usually expects.",
			);
		}

		if (decisionQ === "needs-skepticism" || decisionQ === "insufficient-data") {
			rationaleParts.push(
				"Portfolio decision quality still requires review before path guidance should be treated as strong.",
			);
		}

		const HARD_CONCERNS = new Set([
			"missing-operating-path",
			"program-disposition-conflict",
			"intent-needs-review",
			"weak-context",
			"archived-outside-archive-path",
		]);
		let pathConfidence;
		if (concerns.some((c) => HARD_CONCERNS.has(c))) {
			pathConfidence = "low";
		} else if (!explicitContract) {
			pathConfidence = "medium";
		} else if (contextQ === "minimum-viable") {
			pathConfidence = "medium";
		} else if (
			decisionQ === "needs-skepticism" ||
			decisionQ === "insufficient-data"
		) {
			pathConfidence = "medium";
		} else {
			pathConfidence = "high";
		}

		const pathOverride = pathConfidence === "low" ? INVESTIGATE_OVERRIDE : "";
		if (pathOverride) {
			rationaleParts.push(
				"Treat this repo as investigate until path confidence improves.",
			);
		}

		let rationale = rationaleParts.filter(Boolean).join(" ").trim();
		if (!rationale) rationale = "No operating-path rationale is recorded yet.";

		return {
			operating_path: stablePath,
			operating_path_source: pathSource,
			path_override: pathOverride,
			path_confidence: pathConfidence,
			path_rationale: rationale,
			_concerns: concerns, // extra for the explainer UI; not part of the Python contract
		};
	}

	// ---- 6. risk: build_risk_entry (portfolio_risk.py:53) ----
	// `isStrategic` replaces the Python's `display_name in STRATEGIC_REPOS` membership test.

	function buildRiskEntry({
		isStrategic = false,
		operatingPath = "",
		pathOverride = "",
		contextQuality = "",
		activityStatus = "",
		registryStatus = "",
		criticality = "",
		doctorStandard = "",
		knownRisksPresent = false,
		runInstructionsPresent = false,
		securityHighAlerts = 0,
		securityCriticalAlerts = 0,
	}) {
		if (registryStatus === "archived" || operatingPath === "archive") {
			return { ...DEFERRED_ARCHIVED, risk_factors: [] };
		}
		if (activityStatus === "stale" && operatingPath !== "maintain") {
			return { ...DEFERRED_STALE, risk_factors: [] };
		}

		const factors = [];

		if (
			ACTIVE_STATUSES.has(activityStatus) &&
			WEAK_CONTEXT.has(contextQuality)
		) {
			factors.push("weak-context-active");
		}
		if (pathOverride === "investigate" && ACTIVE_STATUSES.has(activityStatus)) {
			factors.push("investigate-override");
		}
		if (!operatingPath && ACTIVE_STATUSES.has(activityStatus)) {
			factors.push("missing-operating-path");
		}
		if (isStrategic && !doctorStandard) {
			factors.push("missing-doctor-standard");
		}
		if (ACTIVE_STATUSES.has(activityStatus) && !runInstructionsPresent) {
			factors.push("no-run-instructions");
		}
		if (
			(criticality === "high" || criticality === "critical") &&
			!knownRisksPresent
		) {
			factors.push("undocumented-risks");
		}

		const active = ACTIVE_STATUSES.has(activityStatus);
		if (active && (securityHighAlerts > 0 || securityCriticalAlerts > 0)) {
			factors.push("active-high-severity-alerts");
		}

		const securityForcesElevated = active && securityCriticalAlerts > 0;
		const isElevated =
			factors.length >= 3 ||
			(factors.includes("weak-context-active") &&
				factors.includes("investigate-override")) ||
			securityForcesElevated;

		let riskTier;
		if (isElevated) riskTier = "elevated";
		else if (factors.length > 0) riskTier = "moderate";
		else riskTier = "baseline";

		const doctorGap = factors.includes("missing-doctor-standard");
		const contextRisk = factors.includes("weak-context-active");
		const pathRisk =
			factors.includes("investigate-override") ||
			factors.includes("missing-operating-path");
		const securityRisk = factors.includes("active-high-severity-alerts");

		let riskSummary;
		if (factors.length === 0) {
			riskSummary = "No elevated risk factors.";
		} else {
			const parts = factors.map((f) => FACTOR_LABELS[f] || f);
			riskSummary = `${factors.length} risk factor(s): ${parts.join(", ")}.`;
		}

		return {
			risk_tier: riskTier,
			risk_factors: factors,
			risk_summary: riskSummary,
			doctor_gap: doctorGap,
			context_risk: contextRisk,
			path_risk: pathRisk,
			security_risk: securityRisk,
		};
	}

	// ---- 7. attention: _attention_state_for (reconcile.py:985) ----

	function attentionStateFor({
		registryStatus,
		lifecycleState = "",
		operatingPath = "",
		intendedDisposition = "",
		category = "",
		pathOverride = "",
		riskEntry = {},
		githubArchived = false,
	}) {
		if (
			githubArchived ||
			registryStatus === "archived" ||
			lifecycleState === "archived" ||
			operatingPath === "archive"
		) {
			return "archived";
		}
		if (
			operatingPath === "experiment" ||
			intendedDisposition === "experiment" ||
			lifecycleState === "experimental"
		) {
			return "experiment";
		}
		if (registryStatus === "parked") return "parked";
		if (
			pathOverride === "investigate" ||
			!operatingPath ||
			riskEntry.security_risk
		) {
			return "decision-needed";
		}
		if (
			(registryStatus === "active" || registryStatus === "recent") &&
			(operatingPath === "maintain" || operatingPath === "finish")
		) {
			if (category === "infrastructure") return "active-infra";
			if (category === "commercial") return "active-product";
			return "manual-only";
		}
		if (registryStatus === "active" || registryStatus === "recent")
			return "manual-only";
		return "parked";
	}

	// ---- Orchestrated cascade (mirrors _build_truth_project call order,
	//      reconcile.py:600-676: activity → registry → pathing → risk → attention) ----

	function runCascade(signals) {
		const s = signals;

		const activity_status = activityStatusFor({
			lastActivityDays: s.lastActivityDays,
			lifecycleState: s.lifecycleState || "",
			githubArchived: Boolean(s.githubArchived),
		});
		const registry_status = registryStatusFor(activity_status);

		const context = contextQualityFor({
			primaryExists: Boolean(s.primaryExists),
			hasReadme: Boolean(s.hasReadme),
			sections: s.sections,
			supportingFileNames: s.supportingFileNames || [],
			primaryContextFile: s.primaryContextFile || "AGENTS.md",
		});

		// Live pipeline passes only these three keyword args (reconcile.py:608-624);
		// intent_alignment / completeness_tier / decision_quality_status default to "".
		const path_entry = buildOperatingPathEntry(
			{
				operating_path: s.declaredOperatingPath || "",
				intended_disposition: s.intendedDisposition || "",
				maturity_program: s.maturityProgram || "",
				has_explicit_entry: Boolean(s.hasExplicitEntry),
			},
			{
				contextQuality: context.context_quality,
				archived: Boolean(s.githubArchived),
				registryStatus: registry_status,
			},
		);

		const risk_entry = buildRiskEntry({
			isStrategic: Boolean(s.isStrategic),
			operatingPath: path_entry.operating_path,
			pathOverride: path_entry.path_override,
			contextQuality: context.context_quality,
			activityStatus: activity_status,
			registryStatus: registry_status,
			criticality: s.criticality || "",
			doctorStandard: s.doctorStandard || "",
			knownRisksPresent: Boolean(s.sections && s.sections.known_risks),
			runInstructionsPresent: Boolean(
				s.sections && s.sections.run_instructions,
			),
			securityHighAlerts: s.securityHighAlerts || 0,
			securityCriticalAlerts: s.securityCriticalAlerts || 0,
		});

		const attention_state = attentionStateFor({
			registryStatus: registry_status,
			lifecycleState: s.lifecycleState || "",
			operatingPath: path_entry.operating_path,
			intendedDisposition: s.intendedDisposition || "",
			category: s.category || "",
			pathOverride: path_entry.path_override,
			riskEntry: risk_entry,
			githubArchived: Boolean(s.githubArchived),
		});

		return {
			activity_status,
			registry_status,
			context,
			path_entry,
			risk_entry,
			attention_state,
		};
	}

	return {
		activityStatusFor,
		registryStatusFor,
		contextQualityFor,
		resolveDeclaredOperatingPath,
		buildOperatingPathEntry,
		buildRiskEntry,
		attentionStateFor,
		runCascade,
		constants: {
			VALID_OPERATING_PATHS: [...VALID_OPERATING_PATHS],
			REQUIRED_SECTION_ORDER,
			SECTION_LABELS,
			FACTOR_LABELS,
			STANDARD_SIGNAL_FILES: [...STANDARD_SIGNAL_FILES],
			FULL_SIGNAL_FILES: [...FULL_SIGNAL_FILES],
			SUPPORTING_CONTEXT_FILES: [...SUPPORTING_CONTEXT_FILES],
		},
	};
});
