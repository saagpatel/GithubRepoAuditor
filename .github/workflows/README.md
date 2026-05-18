# GitHub Actions Workflows

## `ci.yml` — Continuous Integration

Runs on code-bearing pushes and pull requests to `main`. Documentation-only changes are ignored to avoid spending private Actions minutes on non-code updates. Superseded runs are canceled automatically.

While this repository remains private during the GitHub Actions billing mitigation period, CI runs the canonical Python 3.11 lane only. Restore the broader Python version matrix after either making the repository public or explicitly accepting the private-runner cost.

Steps:
1. Install dependencies via `pip install -e ".[dev]"`
2. Run the full test suite with `pytest tests/ -v --tb=short`
3. Lint with `ruff check src/ tests/`
4. Type-check the extracted operator trend seams with scoped `mypy`

No secrets are required for CI.

## `audit.yml` — Manual Automated Audit

Runs manually via `workflow_dispatch`. The automatic weekly schedule is disabled while the repository remains private to avoid recurring GitHub Actions billing.

Steps:
1. Install the package with config support.
2. Restore cached audit history and incremental fingerprints.
3. Run the audit in `standard` workbook mode, using incremental mode when a trustworthy cached baseline already exists.
4. Run `audit <username> --control-center` to generate the read-only operator triage artifact.
5. Inspect the canonical scheduled handoff issue state, then run `python3 -m src.scheduled_handoff --output-dir output ...` to build the scheduled handoff JSON + Markdown summary with the right lifecycle action.
6. Upload `output/` as the primary artifact output.
7. Open, update, close, or reopen one canonical `scheduled-audit-handoff` issue depending on whether the latest handoff is noisy or quiet.

The workflow does not commit generated runtime artifacts back into the repository.

### Required secrets

- `AUDIT_TOKEN`: GitHub Personal Access Token used by the audit itself when private-repo access or higher rate limits are needed.
- `GITHUB_TOKEN`: GitHub Actions token used to create or update the optional scheduled handoff issue.

### Manual trigger

Go to **Actions → Scheduled Audit → Run workflow** and optionally override the username.
