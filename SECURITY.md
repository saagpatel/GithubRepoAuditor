# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| latest  | ✅ |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub private vulnerability reporting:
1. Go to the **Security** tab of this repository
2. Click **Report a vulnerability**
3. Provide details about the issue

We aim to acknowledge reports within 48 hours and resolve confirmed vulnerabilities within 14 days.

## Scope

- **GitHub token handling**: tokens are passed via env var, never logged or stored on disk
- **Notion API token**: same handling as above
- **Subprocess git clone**: uses authenticated URLs that are cleaned from env after use
- **Output files**: reports are written to the local `output/` directory only

## Generated Artifact Privacy Model

GitHub Repo Auditor writes local reports, workbooks, dashboards, history databases,
and operator summaries from the repositories you ask it to inspect. Those artifacts
may include repository names, local paths, scores, findings, summaries, and GitHub
Advanced Security alert counts such as Dependabot, code-scanning, and
secret-scanning totals.

The tool does not need to persist raw GitHub, Notion, or AI provider tokens, and it
does not intentionally persist raw secret values from GitHub secret scanning. Treat
generated artifacts as operator data, especially when auditing private repositories,
and keep `output/` out of version control. The default `.gitignore` excludes the
standard generated output files and cache/database folders.
