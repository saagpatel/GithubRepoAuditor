import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
	title: "Portfolio Health — clone-free GitHub report",
	description:
		"Paste a GitHub username and get a clone-free portfolio health report: grades, the biggest drags, and the concrete fixes that move each repo forward.",
};

export default function RootLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return (
		<html lang="en">
			<body>{children}</body>
		</html>
	);
}
