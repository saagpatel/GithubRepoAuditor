# Distribution

GitHub Repo Auditor is public and currently distributed through GitHub Releases.

## Current Public Path

Use the latest release binary when you want the fastest no-clone install:

```bash
curl -LO https://github.com/saagpatel/GithubRepoAuditor/releases/latest/download/audit.pyz
chmod +x audit.pyz
./audit.pyz --help
```

Use the public GitHub source when you want an isolated tool install:

```bash
uv tool install 'git+https://github.com/saagpatel/GithubRepoAuditor.git'
pipx install 'git+https://github.com/saagpatel/GithubRepoAuditor.git'
```

## PyPI Status

PyPI publishing is not active yet. The package name `github-repo-auditor` was
available when checked during the public-readiness pass on 2026-05-18, but that
can change and should be rechecked immediately before first publication.

The repository is prepared for a future PyPI release:

- package metadata lives in `pyproject.toml`
- `make build` creates the wheel and source distribution
- `make dist-check` runs `twine check`
- `scripts/release.sh` builds and checks artifacts by default
- `scripts/release.sh --publish-pypi` is the only script path that uploads to PyPI
- `.github/workflows/pypi.yml` is a manual Trusted Publishing workflow for a
  release tag, using the `pypi` environment and short-lived OIDC credentials

## Activation Checklist

Before the first PyPI release:

1. Recheck that the `github-repo-auditor` PyPI name is still available.
2. Configure PyPI Trusted Publishing for owner `saagpatel`, repository
   `GithubRepoAuditor`, workflow `pypi.yml`, and environment `pypi`.
3. Protect the GitHub `pypi` environment so publishing requires intentional
   approval.
4. Run the standard and distribution gates from [release-gates.md](release-gates.md).
5. Open **Actions -> Publish to PyPI -> Run workflow** and enter the release tag,
   for example `v0.1.1`.
6. Smoke-test `pipx install github-repo-auditor` or `uv tool install github-repo-auditor`.

Until that checklist is complete, GitHub Releases remain the supported public
distribution channel.
