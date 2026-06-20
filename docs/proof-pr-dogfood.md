# proof-pr Dogfood

GithubRepoAuditor uses `proof-pr` as an advisory proof receipt lane for PRs that
change workflow, proof, public evidence, release, or review surfaces. The
committed `proof-pr.json` is the dogfood receipt for the original workflow
adoption; keep it historical unless a PR is intentionally refreshing that
receipt.

For local author checks, install the current public tag in a temporary
environment and render the proof block from a generated receipt:

```bash
python3 -m venv /tmp/gra-proof-pr-venv
/tmp/gra-proof-pr-venv/bin/python -m pip install \
  git+https://github.com/saagpatel/proof-pr.git@v0.2.7
/tmp/gra-proof-pr-venv/bin/proof-pr init \
  --cwd . \
  --tier T1 \
  --summary "Short PR summary" \
  --output /tmp/gra-proof-pr.json
/tmp/gra-proof-pr-venv/bin/proof-pr collect \
  /tmp/gra-proof-pr.json \
  --cwd .
/tmp/gra-proof-pr-venv/bin/proof-pr render \
  /tmp/gra-proof-pr.json
/tmp/gra-proof-pr-venv/bin/proof-pr receipt-hygiene \
  /tmp/gra-proof-pr.json \
  --explain
```

`receipt-hygiene --explain` is the author-facing nudge for incomplete receipts.
It keeps hygiene read-only, but adds copyable commands and compact receipt patch
examples for missing evidence such as public git metadata, secrets posture,
permission posture, or rollback specificity.

For GithubRepoAuditor, keep the risk tier honest:

- `T0`: documentation-only changes with no runtime effect.
- `T1`: narrow code changes covered by focused tests or a targeted verifier.
- `T2`: user-visible CLI, output, workbook, schema, or API behavior changes.
- `T3`: GitHub Actions, workflow permissions, public evidence, writeback,
  generated truth surfaces, or agent/operator access changes.
- `T4`: releases, migrations, security-sensitive changes, or irreversible
  external writes.

The receipt is review evidence, not supply-chain provenance. Release/build tiers
should link separate attestations or artifact digests when those are relevant.
