# GitHub Actions Workflows

## ci.yml — Continuous Integration

Runs on every push and pull request to `main`. Tests against Python 3.11, 3.12, and 3.13.

**Steps:**
1. Install dependencies via `pip install -e ".[dev]"`
2. Run the full test suite with `pytest tests/ -v --tb=short`
3. Lint with `ruff check src/ tests/`

No secrets required for CI.

## scheduled-audit.yml — Weekly Automated Audit

Runs every Sunday at 06:00 UTC, or manually via `workflow_dispatch`.

**Steps:**
1. Installs the package
2. Runs `python -m src <username> --incremental --html --badges --diff`
3. Uploads the `output/` directory as a build artifact (retained 90 days)
4. On scheduled runs only: commits the updated output back to the repo

### Required secret

Add `AUDIT_GITHUB_TOKEN` to your repository secrets:

1. Go to **Settings → Secrets and variables → Actions → New repository secret**
2. Name: `AUDIT_GITHUB_TOKEN`
3. Value: A GitHub Personal Access Token with `repo` scope (needed to read private repos and push results back)

The token must have at least `public_repo` scope for public-only audits, or `repo` for private repos.

### Manual trigger

Go to **Actions → Scheduled Audit → Run workflow** and optionally override the username.
