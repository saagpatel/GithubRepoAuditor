# audit serve — Local Web UI

`audit serve` starts a local FastAPI + HTMX web interface over your latest audit output.
It is a read-mostly operator tool: you can browse portfolio state, per-repo history, run
history, and the approval queue, and you can trigger new audit runs through a form.
It binds to `127.0.0.1` only and requires no authentication — treat it as a local-only
tool for solo operator use.

## Installation

The web UI dependencies are in the `[serve]` extra and are not installed by default.

```bash
# editable / dev install
pip install -e '.[serve]'

# or via uv tool from the public GitHub source
uv tool install 'git+https://github.com/saagpatel/GithubRepoAuditor.git#egg=github-repo-auditor[serve]'

# or via pipx from the public GitHub source
pipx install 'git+https://github.com/saagpatel/GithubRepoAuditor.git#egg=github-repo-auditor[serve]'
```

If you try to run `audit serve` without the extra installed, the CLI will exit with a
clear error asking you to install `[serve]`.

## How to launch

```bash
audit serve                        # default: port 8080, bind 127.0.0.1
audit serve --port 9090            # custom port
audit serve --output-dir /path/to/output   # if your output/ is elsewhere
```

Full flag reference (`audit serve --help`):

| Flag | Default | Description |
|------|---------|-------------|
| `--port PORT` | `8080` | Port to listen on |
| `--host HOST` | `127.0.0.1` | Interface to bind (do not change to `0.0.0.0`) |
| `--output-dir DIR` | `./output` | Directory where audit output files live |
| `--config PATH` | `./audit-config.yaml` | Path to audit config file |
| `--verbose` | off | Print detailed output |
| `--token TOKEN` | `$GITHUB_TOKEN` | GitHub token forwarded to triggered runs |

Once started, open `http://127.0.0.1:8080/` in your browser. The server runs until you
press Ctrl-C.

## Routes

### `GET /`

Portfolio dashboard. Reads `output/portfolio-truth-latest.json` (if present) and renders
a summary: top-5 risk repos, top-5 completeness-gap repos, tier distribution, and an
HTMX auto-refresh indicator.

If `portfolio-truth-latest.json` is absent, the page shows a prompt to run
`audit report <username> --portfolio-truth` first.

### `GET /repos/{name}`

Per-repo drill-down. Shows the warehouse history for the named repo (score trend,
dimension scores, alert history) pulled from `portfolio-warehouse.db`.

Returns 404 if the repo name is not found in the warehouse.

### `GET /runs`

Paginated run history from the `audit_runs` table in `portfolio-warehouse.db`. Shows
run timestamp, username, repo count, portfolio grade, and any run-level notes.

### `GET /approvals`

Approval queue. Reads the latest approval-center state and renders open items grouped by
status (`needs-reapproval`, `ready-for-review`, `approved-manual`, `blocked`). Approve
and reject buttons submit via HTMX and record intent locally — they do not trigger
writeback automatically.

### `GET /runs/new` and `POST /runs/new`

New-run form. Select audit flags from the safe allowlist and submit to trigger an
`audit run` subprocess. Live output streams back to the browser via Server-Sent Events
at `GET /runs/new/stream/{run_id}`.

### `POST /approvals/{id}/approve` and `POST /approvals/{id}/reject`

HTMX endpoints for the approval queue. Record a local approval or rejection intent.
These are intent-log only — they do not call `--writeback-apply`.

## Subprocess safety

All flags accepted through the `/runs/new` form are validated against a strict allowlist
(`SAFE_FLAG_NAMES` in `src/serve/runner.py`). Any flag name not in the allowlist is
rejected before the subprocess is spawned.

Flag values are additionally checked against a shell-metacharacter blocklist. The
characters `;`, `|`, `&`, `$`, `` ` ``, `\`, `<`, `>`, and `!` are never permitted in
any flag value. The subprocess is always spawned with `shell=False`.

These two controls together prevent shell-injection from the web form.

## Known limitations

- **No authentication.** The UI is designed for single-user local use only. Do not
  expose it on a non-loopback interface or behind a shared reverse proxy without adding
  your own auth layer.
- **Binds to `127.0.0.1` only.** The default host is intentionally loopback. Changing
  `--host` to `0.0.0.0` is unsupported and not recommended.
- **Not for multi-user environments.** The approval intent log and run session registry
  are in-memory or local-file only; there is no multi-user isolation.
- **`[serve]` extra required.** FastAPI and uvicorn are not installed by default to keep
  the base install lightweight.
- **Approval buttons are intent-log only.** Clicking approve/reject in the UI records
  local state. It does not apply any writeback. To apply approved campaign packets, run
  `audit triage <username> --auto-apply-approved` from the CLI after confirming the
  trust bar is green.
