// Mirrors the JSON shape emitted by the Python engine's
// `ApiOnlyReport.to_dict()` / `RepoAudit.to_dict()` (src/api_only.py, src/models.py).
// Only the fields the UI renders are typed; the payload carries more.

export interface RepoMetadata {
	name: string;
	full_name: string;
	description: string | null;
	language: string | null;
	html_url: string;
	stars: number;
	forks: number;
	archived: boolean;
	fork: boolean;
	pushed_at: string | null;
}

export interface AnalyzerResult {
	dimension: string;
	score: number;
	max_score: number;
}

// One entry of `action_candidates` — the engine's ranked, concrete fixes.
export interface ActionCandidate {
	key: string;
	title: string;
	action: string;
	lens: string;
	effort: string;
	confidence: number;
	expected_lens_delta: number;
	expected_tier_movement: string;
	rationale: string;
}

export interface RepoAudit {
	metadata: RepoMetadata;
	analyzer_results: AnalyzerResult[];
	overall_score: number; // 0..1
	grade: string;
	completeness_tier: string;
	flags: string[];
	action_candidates: ActionCandidate[];
}

export interface Report {
	username: string;
	mode: string;
	fidelity_note: string;
	repo_count: number;
	repos: RepoAudit[];
}
