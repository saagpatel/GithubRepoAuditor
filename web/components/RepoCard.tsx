import type { RepoAudit } from "@/lib/types";
import { safeHttpUrl } from "@/lib/url";

function gradeClass(grade: string): string {
	const g = grade.trim().toUpperCase().charAt(0);
	return ["A", "B", "C", "D", "F"].includes(g) ? `g-${g.toLowerCase()}` : "g-f";
}

function pct(score01: number): string {
	return `${Math.round(score01 * 100)}%`;
}

function impactLabel(delta: number): string {
	return `+${Math.round(delta * 100)} pts`;
}

export default function RepoCard({ repo }: { repo: RepoAudit }) {
	const { metadata, grade, overall_score, flags, action_candidates } = repo;
	// Lead with fixes, not the number: the top 3 highest-leverage actions.
	const fixes = action_candidates.slice(0, 3);
	const repoUrl = safeHttpUrl(metadata.html_url);

	return (
		<article className="card">
			<div className="card-top">
				<div
					className={`grade ${gradeClass(grade)}`}
					aria-label={`Grade ${grade}`}
				>
					{grade.charAt(0)}
				</div>

				<div className="card-title">
					<h3>
						{repoUrl ? (
							<a href={repoUrl} target="_blank" rel="noopener noreferrer">
								{metadata.name}
							</a>
						) : (
							metadata.name
						)}
					</h3>
					{metadata.description && (
						<p className="desc">{metadata.description}</p>
					)}
					<div className="card-meta">
						{metadata.language && <span>{metadata.language}</span>}
						<span>★ {metadata.stars}</span>
						{metadata.fork && <span>fork</span>}
						{metadata.archived && <span>archived</span>}
					</div>
				</div>

				<div className="score">
					<div className="pct">{pct(overall_score)}</div>
					<div className="pct-label">health</div>
				</div>
			</div>

			{flags.length > 0 && (
				<div className="flags">
					{flags.map((flag) => (
						<span className="flag" key={flag}>
							{flag}
						</span>
					))}
				</div>
			)}

			{fixes.length > 0 ? (
				<div className="fixes">
					<h4>Top fixes</h4>
					{fixes.map((fix, i) => (
						<div className="fix" key={`${fix.key}-${i}`}>
							<div className="fix-rank">{i + 1}</div>
							<div className="fix-body">
								<div className="fix-title">{fix.title}</div>
								<div className="fix-action">{fix.action}</div>
								<div className="fix-tags">
									<span className="impact">
										{impactLabel(fix.expected_lens_delta)}
									</span>
									<span>{fix.effort} effort</span>
									<span>{fix.expected_tier_movement}</span>
								</div>
							</div>
						</div>
					))}
				</div>
			) : (
				<p className="clean">
					No high-leverage fixes flagged — this one is in good shape.
				</p>
			)}
		</article>
	);
}
