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
- **Output files**: reports written to local  directory only
