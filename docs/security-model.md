# Security Model

GithubRepoAuditor now treats security posture as a merged intelligence model instead of a single local heuristic.

## Evidence Sources

- **Local**: committed secret patterns, dangerous files, `SECURITY.md`, Dependabot config
- **GitHub-native**: dependency graph/SBOM availability, code scanning status, secret scanning status, open alert counts
- **Scorecard**: optional public-repo enrichment from OpenSSF Scorecard

## Availability Rules

- `unavailable` means the provider could not be observed because of permissions, feature availability, or endpoint access.
- `not-configured` means the provider was observable and the control does not appear to be enabled.
- Unavailable provider state is **not** treated as a hard failure by itself.

## Merged Posture

Each repo keeps backward-compatible top-level security fields:

- `score`
- `label`
- `secrets_found`
- `dangerous_files`
- `has_security_md`
- `has_dependabot`

It also adds nested provider detail:

- `local`
- `github`
- `scorecard`
- `providers`
- `recommendations`

## Dry-Run Governance

Security governance is preview-only in this phase. Recommendations are generated for later writeback, but the tool does not mutate GitHub or Notion yet.

Examples:

- enable CodeQL default setup
- enable secret scanning
- ensure dependency graph coverage / export SBOM
- add Dependabot config
- add `SECURITY.md`
- add Scorecard workflow
