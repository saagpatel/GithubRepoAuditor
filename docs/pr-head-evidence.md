# Pull Request Evidence-to-Head Binding

`audit pr-evidence` is a local-only operator command that answers one narrow
question:

> Is the evidence required by the supplied rules current for the supplied pull
> request head?

It reads a `PRHeadEvidenceV1` JSON snapshot, writes a deterministic
`PRHeadEvidenceVerdictV1` JSON document to standard output, and performs no
GitHub requests or file writes.

```bash
audit pr-evidence tests/fixtures/pr_head_evidence/current.json
```

The command is intentionally separate from portfolio scoring and generated
portfolio truth. It does not regenerate or modify either contract.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All required evidence is current and successful for the supplied head. |
| `1` | The valid snapshot is stale, blocked, pending, missing, neutral, or skipped. |
| `2` | Coverage is unknown, the snapshot is inaccessible, or the input is malformed. |

JSON is emitted for every evaluable command result, including malformed input.

## `PRHeadEvidenceV1` input

All fields below are required unless they are explicitly nullable. Unknown
fields are rejected so misspellings cannot silently weaken the contract.
Unknown rule *types* are preserved as coverage gaps and force an `unknown`
verdict.

```json
{
  "schema_version": "PRHeadEvidenceV1",
  "pull_request": {
    "repository": "owner/repository",
    "number": 42,
    "author": "pull-request-author",
    "head_sha": "40-or-64-character-full-sha",
    "base_sha": "40-or-64-character-full-sha"
  },
  "latest_reviewable_push": {
    "pushed_at": "2026-07-28T10:00:00Z",
    "actor": "pusher-login"
  },
  "reviews": [
    {
      "id": 1001,
      "actor": {
        "login": "reviewer-login",
        "can_count": true
      },
      "state": "APPROVED",
      "commit_id": "full-reviewed-commit-sha",
      "submitted_at": "2026-07-28T10:05:00Z",
      "dismissal": {
        "dismissed": false,
        "dismissed_at": null,
        "prior_state": null
      }
    }
  ],
  "checks": [
    {
      "id": 2001,
      "kind": "check_run",
      "name": "ci/test",
      "head_sha": "full-checked-commit-sha",
      "status": "completed",
      "conclusion": "success",
      "integration_id": 99
    }
  ],
  "rules": {
    "source": "branch_protection",
    "availability": "available",
    "items": [
      {
        "type": "pull_request",
        "required_approving_review_count": 1,
        "dismiss_stale_reviews": true,
        "require_last_push_approval": true,
        "require_code_owner_reviews": false
      },
      {
        "type": "required_status_checks",
        "strict_required_status_checks_policy": false,
        "checks": [
          {
            "context": "ci/test",
            "integration_id": 99
          }
        ]
      }
    ]
  },
  "coverage": {
    "reviews": {
      "permission": "granted",
      "complete": true,
      "truncated": false,
      "pages_fetched": 1
    },
    "checks": {
      "permission": "granted",
      "complete": true,
      "truncated": false,
      "pages_fetched": 1
    },
    "rules": {
      "permission": "granted",
      "complete": true,
      "truncated": false,
      "pages_fetched": 1
    }
  },
  "provenance": {
    "source": "synthetic_fixture",
    "captured_at": "2026-07-28T10:10:00Z",
    "freshness": "current"
  }
}
```

`actor.can_count` is a normalized collector assertion that the reviewer is
eligible to count under the supplied repository policy. Use `null` when the
permission or actor eligibility could not be established; that keeps approval
coverage `unknown`. Actor logins are compared case-insensitively, matching
GitHub identity semantics. An approval from `pull_request.author` never counts,
even if a malformed collector assertion sets `can_count` to `true`.

`review.submitted_at` may be `null` only for a `PENDING` review, matching
GitHub's response shape for an unsubmitted review. Submitted reviews require a
timezone-qualified timestamp.

`latest_reviewable_push.pushed_at` and `.actor` are nullable only so a collector
can preserve missing data. If `require_last_push_approval` is true and either is
missing, the verdict is `unknown`.

`rules.source` is `branch_protection`, `ruleset`, or `combined`.
`rules.availability` is `available`, `missing`, or `inaccessible`. A complete,
available, empty rules array means that the supplied rules snapshot establishes
no approval or status-check requirements. Missing rules never receive invented
defaults.

The initial evaluator supports normalized pull-request approval counts,
stale-approval dismissal, latest-push approval, and required status-check
contexts. A code-owner requirement is accepted but yields `unknown` because a
head snapshot alone cannot prove every changed path's ownership groups.

## Binding and outcome are separate

Every review keeps its original `state`, actor, dismissal fields, and
`commit_id`. Every check keeps its kind, status, conclusion, and `head_sha`.
The verdict adds:

- `binding_state`: `current` when the evidence SHA matches the supplied head,
  otherwise `stale`;
- a review `decision_state`, including `commented` and `dismissed`;
- a check `result_state`, including `success`, `pending`, `neutral`, `skipped`,
  `cancelled`, `blocked`, `stale`, and `unknown`.

GitHub documents that `neutral` and `skipped` can satisfy a required status
check. The verdict exposes that narrow fact as
`github_requirement_satisfied=true`, but its top-level state remains `neutral`
or `skipped`; it is not collapsed into current successful evidence.

Check suites are SHA-bound and classified, but they do not masquerade as a
required status-check context. GitHub branch rules select checks or commit
statuses, not suite summaries.

When stale-review dismissal is disabled, GitHub can retain an approval after a
push. The verdict records that as a counted retained approval while keeping its
binding `stale`. If a requirement depends on retained stale approval, the
top-level evidence verdict is `stale`, not green.

## Coverage rules

The following conditions force `coverage.state=unknown`:

- review, check, or rule permission is `missing`, `inaccessible`, or `unknown`;
- pagination is incomplete or truncated;
- protection/ruleset data is missing or inaccessible;
- a rule type is unknown;
- reviewer counting eligibility is unknown and can change the result;
- a code-owner review requirement is present;
- provenance freshness is unknown.

A stale provenance assertion yields a `stale` verdict. No implicit freshness
window is invented.

## Supported sources

The first implementation is fixture-first. A snapshot may be produced by a
synthetic fixture, an operator export, or a separate read-only GitHub collector,
but the collector must normalize the same fields and state completeness
honestly.

The semantics track GitHub's primary documentation:

- [REST pull request reviews](https://docs.github.com/en/rest/pulls/reviews)
  exposes review `state` and `commit_id`.
- [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
  defines stale approval dismissal and approval of the most recent reviewable
  push.
- [REST check runs](https://docs.github.com/en/rest/checks/runs) and
  [REST check suites](https://docs.github.com/en/rest/checks/suites) bind check
  evidence to `head_sha`.
- [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)
  states that required checks apply to the latest commit SHA and describes
  successful, neutral, and skipped conclusions.
- [REST repository rules](https://docs.github.com/en/rest/repos/rules) describes
  normalized pull-request and required-status-check rule parameters.

## Claim ceiling

The command does **not** claim that GitHub would merge the pull request, that
the code is correct, that reviews were effective, that CI is trustworthy, or
that the branch is safe. Its top-level state evaluates required evidence under
the supplied rules. It still classifies every supplied review and check against
the supplied head so historical or non-required evidence cannot masquerade as
current evidence.

Synthetic fixture triplets live in
`tests/fixtures/pr_head_evidence/semantic_triplets.json`. Direct CLI smoke
snapshots for current, stale, comment-only, dismissed, incomplete, and malformed
cases live beside it.
