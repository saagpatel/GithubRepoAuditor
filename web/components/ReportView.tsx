import type { Report } from "@/lib/types";
import RepoCard from "./RepoCard";

export default function ReportView({ report }: { report: Report }) {
	// Worst-graded first: the report's job is to point at what to fix.
	const repos = [...report.repos].sort(
		(a, b) => a.overall_score - b.overall_score,
	);

	return (
		<section>
			<div className="report-head">
				<h2>
					<a
						href={`https://github.com/${encodeURIComponent(report.username)}`}
						target="_blank"
						rel="noopener noreferrer"
					>
						@{report.username}
					</a>
				</h2>
				<div className="sub">
					{report.repo_count} {report.repo_count === 1 ? "repo" : "repos"}{" "}
					scored clone-free
				</div>
				<p className="fidelity">{report.fidelity_note}</p>
			</div>

			<div className="cards">
				{repos.map((repo) => (
					<RepoCard key={repo.metadata.full_name} repo={repo} />
				))}
			</div>

			<div className="cta">
				<span className="label">
					Want the deep scan — code quality, secrets, dependency age?
				</span>
				<code>pipx run github-repo-auditor audit {report.username}</code>
			</div>
		</section>
	);
}
