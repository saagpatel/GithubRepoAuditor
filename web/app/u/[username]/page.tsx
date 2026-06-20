import Link from "next/link";
import ReportLoader from "@/components/ReportLoader";

export default async function UserReport({
	params,
}: {
	params: Promise<{ username: string }>;
}) {
	// Next.js already URL-decodes dynamic segment values.
	const { username } = await params;

	return (
		<main className="wrap">
			<nav className="report-nav">
				<Link href="/" className="back">
					← scan another
				</Link>
			</nav>
			<ReportLoader username={username} />
		</main>
	);
}
