import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Self-hosted (SIL OFL, see app/fonts) so builds never depend on Google Fonts.
const sans = localFont({
	src: "./fonts/SpaceGrotesk-latin-wght.woff2",
	weight: "300 700",
	variable: "--font-sans",
	display: "swap",
});

const mono = localFont({
	src: "./fonts/JetBrainsMono-latin-wght.woff2",
	weight: "100 800",
	variable: "--font-mono",
	display: "swap",
});

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
		<html lang="en" className={`${sans.variable} ${mono.variable}`}>
			<body>{children}</body>
		</html>
	);
}
