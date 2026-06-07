# Proof Package Contract v1

Proof packages are small, durable evidence bundles for done-state claims. They do
not replace each repo's native reports, screenshots, release assets, dry-run
outputs, or health commands. They point at those artifacts and make the claim
auditable from one manifest.

Use a proof package whenever future work needs to prove that a demo, live write,
dry run, release, sync, health gate, or operational burn-in is actually done.

## Layout

```text
docs/proof-packages/<YYYYMMDD>-<lane>/
  proof-package.json
  SUMMARY.md
  evidence/
  receipts/
  logs/
```

The package may reference existing artifacts outside the package when copying
them would create churn. Cross-repo references are allowed, but the manifest must
name the producer, subject, and evidence owner explicitly.

## Manifest

`proof-package.json` is required.

Required top-level fields:

- `schema_version`: must be `proof-package.v1`.
- `package_id`: stable package identifier.
- `subject`: repo, lane, and claim being proven.
- `producer`: repo or command surface that produced the evidence.
- `source_state`: generation time, branch/status when known, and freshness.
- `claims`: list of specific statements with status and evidence.
- `verification`: overall result, checks, missing receipts, and known gaps.
- `safety`: live-write and redaction posture.
- `artifacts`: all referenced files or external evidence.

Allowed claim and verification statuses:

- `passed`
- `failed`
- `partial`
- `stale`

## Artifact Rules

Each artifact entry should include:

- `id`
- `kind`
- `path`
- `description`
- `required`

Optional artifact fields:

- `external`: set to `true` when the path is outside the manifest directory and
  should not be checked by the lightweight validator.
- `owner_repo`: useful for cross-repo proof, such as PortfolioCommandCenter proof
  stored under GithubRepoAuditor.

Local relative artifacts are validated relative to the manifest file.

## Claim Rules

Every claim needs:

- `id`
- `statement`
- `status`
- `evidence`

`evidence` is a list of artifact IDs. A claim may also include `notes` when the
proof is intentionally bounded or stale-prone.

## Done-State Rules

- Demo proof requires source truth plus screenshots or recording.
- Dry-run proof requires planned writes, failed/partial steps, and a live
  go/no-go decision.
- Live-write proof requires read-back or downstream receipt.
- Runtime proof requires a health, burn-in, or status output with explicit
  failure/drift fields.
- Release proof requires build/test/install or checksum evidence.

## Validation

Run:

```bash
python scripts/validate_proof_package.py docs/proof-packages/<package>/proof-package.json
```

The validator checks structure and local file references. It intentionally does
not judge whether a claim is true; the package author must still choose honest
claim statements and bounded evidence.
