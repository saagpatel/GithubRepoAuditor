# Distribution

GitHub Repo Auditor is public and distributed through PyPI and GitHub Releases.

## Current Public Path

Use PyPI for the normal CLI install:

```bash
uv tool install github-repo-auditor
pipx install github-repo-auditor
```

Use the latest release binary when you want the fastest no-clone install:

```bash
curl -LO https://github.com/saagpatel/GithubRepoAuditor/releases/latest/download/audit.pyz
chmod +x audit.pyz
./audit.pyz --help
```

Use the public GitHub source when you want the latest unreleased code:

```bash
uv tool install 'git+https://github.com/saagpatel/GithubRepoAuditor.git'
pipx install 'git+https://github.com/saagpatel/GithubRepoAuditor.git'
```

## PyPI Status

PyPI publishing is active for `github-repo-auditor`.

The repository uses GitHub Actions Trusted Publishing:

- package metadata lives in `pyproject.toml`
- `make build` creates the wheel and source distribution
- `make dist-check` runs `twine check`
- `scripts/release.sh` builds and checks artifacts by default
- `scripts/release.sh --publish-pypi` remains an explicit local fallback only
- `.github/workflows/pypi.yml` is a manual Trusted Publishing workflow for a
  release tag, using the `pypi` environment and short-lived OIDC credentials

## Release Checklist

For a normal public release:

1. Run the standard and distribution gates from [release-gates.md](release-gates.md).
2. Create a PEP 440-compatible `v*` tag from the verified `main` commit.
3. Wait for the GitHub Release workflow to publish the wheel, source distribution,
   and `audit.pyz` assets.
4. Smoke-test the GitHub Release `audit.pyz`.
5. Open **Actions -> Publish to PyPI -> Run workflow** and enter the same release
   tag, for example `v0.1.3`.
6. Approve the protected `pypi` environment.
7. Smoke-test `pipx install github-repo-auditor` or `uv tool install github-repo-auditor`.

GitHub Releases and PyPI should always publish the same tag.
