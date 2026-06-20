/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pin the tracing root to this app — the repo has sibling lockfiles that
  // otherwise make Next infer the wrong workspace root (and warn on every boot).
  outputFileTracingRoot: import.meta.dirname,
};

export default nextConfig;
