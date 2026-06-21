import UsernameForm from "@/components/UsernameForm";

export default function Home() {
	return (
		<main className="wrap">
			<section className="hero">
				<p className="eyebrow">Portfolio health · clone-free</p>
				<h1>See what your GitHub portfolio is missing.</h1>
				<p className="lede">
					Paste a username. We read the GitHub API — no cloning — score every
					public repo, and surface the highest-leverage fixes for each one.
					Free, no signup.
				</p>
				<UsernameForm />
			</section>

			<footer className="foot wrap" style={{ paddingLeft: 0, paddingRight: 0 }}>
				Scored from public API metadata and repository structure. Deep
				code-quality, secret-scanning, and dependency-age signals need the full
				local scan (the open-source CLI).
			</footer>
		</main>
	);
}
