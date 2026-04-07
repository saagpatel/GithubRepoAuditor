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

## Governed Controls

Security governance is no longer preview-only in the abstract. The tool now supports a bounded, manual, opt-in governed control family:

- enable GitHub code security
- enable secret scanning
- enable push protection
- configure CodeQL default setup

Important boundaries:

- Governed apply remains manual and explicit.
- Approval can be invalidated when the governance fingerprint drifts.
- Operator surfaces report ready, approved, applied, drifted, and rollback-coverage state when governance context exists.
- The tool still does **not** expand governance into rulesets, branch protection, or repo-content mutation in this phase.

Examples:

- enable CodeQL default setup
- enable secret scanning
- ensure dependency graph coverage / export SBOM
- add Dependabot config
- add `SECURITY.md`
- add Scorecard workflow
