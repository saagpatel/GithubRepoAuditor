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

## GHAS Alert Fetch

Pass `--ghas-alerts` (or use `--vuln-check`, which implicitly enables it) to fetch live open alert counts from GitHub Advanced Security endpoints.

Three endpoints are queried per repo, all filtered to `state=open`:

- Dependabot alerts — `GET /repos/{owner}/{repo}/dependabot/alerts`
- Code scanning alerts — `GET /repos/{owner}/{repo}/code-scanning/alerts`
- Secret scanning alerts — `GET /repos/{owner}/{repo}/secret-scanning/alerts`

Required scope: `repo` for private repos; alerts are read-only and no mutation occurs. Public repos may surface partial data if GHAS features are not enabled.

Failure behavior: a 403 or 404 on any endpoint records `available: false` for that alert type and continues without raising an exception. This handles repos where GHAS is not enabled or the token lacks the right scope.

Output lands in `output/ghas-alerts-<user>-<date>.json`. Excel and control-center surfacing is wired via S2.4.

## OSSF Scorecard

Pass `--ossf-scorecard` to enrich each repo with pre-computed OSSF Scorecard data.

Endpoint: `GET https://api.securityscorecards.dev/projects/github.com/{owner}/{repo}` — no authentication required.

Failure behavior: a 404 records `{"available": false}` and continues without raising an exception. Repos without a scorecard entry are skipped gracefully.

Output lands in `output/ossf-scorecard-<user>-<date>.json`. Excel and control-center surfacing happens automatically when `--ossf-scorecard` is set (S2.4): the operator brief shows the OSSF score and flags repos with low scores.

Override the endpoint with `OSSF_SCORECARD_BASE_URL` (useful for test isolation).

## GitHub SBOM as Dependency Source

Pass `--sbom-source github` to switch `DependenciesAnalyzer` from lockfile parsing to GitHub's dependency-graph SBOM endpoint.

Endpoint: `GET /repos/{owner}/{repo}/dependency-graph/sbom` — returns an SPDX 2.3 document. Required scope: `repo` for private repos (same token used elsewhere).

Failure behavior: a 403 or 404 falls back to lockfile parsing for that repo and continues without raising an exception.

Advantages over lockfile parsing: catches transitive dependencies that lockfiles omit; does not require a local clone for the dep pass.

Default is `--sbom-source lockfile`, which preserves existing behavior.

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
