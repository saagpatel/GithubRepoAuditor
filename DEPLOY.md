# Deploying the hosted report

Two deployables:

- **API** (FastAPI engine) → a container host. This guide uses **Fly.io**
  (`Dockerfile` + `fly.toml` are ready); Railway works from the same Dockerfile.
- **Frontend** (`web/`, Next.js) → **Vercel**.

Optional but recommended for production:

- **Upstash Redis** — shared cache + per-IP throttle across instances.
- A **GitHub token** (PAT or GitHub App installation token) so the API runs on
  the 5 000 req/hr authenticated limit instead of 60 req/hr.

---

## 1. API → Fly.io

```bash
# One-time
fly launch --no-deploy            # or `fly apps create ghra-report-api`
fly volumes create ghra_data --region iad --size 1   # persists the waitlist DB

# Secrets (never commit these; set them on Fly)
fly secrets set GHRA_GITHUB_TOKEN=ghp_xxx
fly secrets set GHRA_CORS_ORIGINS=https://your-frontend.vercel.app
# If using Upstash (see §3):
fly secrets set GHRA_REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379

fly deploy
```

`fly.toml` already wires the health check (`GET /api/health`), the `/data`
volume mount, and the non-secret config (`GHRA_REPORT_TTL_SECONDS`,
`GHRA_RATE_LIMIT`, `GHRA_RATE_WINDOW_SECONDS`, `GHRA_WAITLIST_DB=/data/waitlist.db`).

The container runs uvicorn with `--forwarded-allow-ips=*`, so behind Fly's proxy
the per-IP throttle keys on the real client address (no `GHRA_TRUST_FORWARDED_FOR`
needed).

Verify: `curl https://ghra-report-api.fly.dev/api/health` →
`{"status":"ok","github_token":true}`.

---

## 2. Frontend → Vercel

```bash
cd web
vercel link
vercel env add NEXT_PUBLIC_API_BASE production   # → https://ghra-report-api.fly.dev
vercel --prod
```

Set the project **Root Directory** to `web/` in Vercel (the repo root is the
Python engine). After the frontend URL is known, set it as `GHRA_CORS_ORIGINS`
on the API (§1) so the browser's cross-origin calls are allowed.

> Vercel commit-author gotcha: if `vercel --prod` is blocked on the commit
> author, deploy from a git-free copy of `web/` and `vercel alias set`.

---

## 3. Upstash Redis (production cache + throttle)

Without `GHRA_REDIS_URL` the API uses an in-process store — correct, but
per-instance (cache and throttle don't share across machines). For more than one
instance, create an Upstash Redis database and set its `rediss://` URL as
`GHRA_REDIS_URL` (§1). The `hosting` extra (`redis`) is already installed in the
image. Any Redis server version works (the throttle uses plain `EXPIRE`).

---

## 4. Environment reference

| Variable                   | Where     | Default            | Purpose                                            |
| -------------------------- | --------- | ------------------ | -------------------------------------------------- |
| `GHRA_GITHUB_TOKEN`        | API       | _(none)_           | Server token → 5 000 req/hr + GraphQL repo lists.  |
| `GHRA_CORS_ORIGINS`        | API       | localhost:3000     | Comma-separated allowed browser origins.           |
| `GHRA_REDIS_URL`           | API       | _(in-memory)_      | Upstash/Redis URL for shared cache + throttle.     |
| `GHRA_REPORT_TTL_SECONDS`  | API       | `3600`             | Report cache TTL.                                  |
| `GHRA_RATE_LIMIT`          | API       | `20`               | Requests per window per IP.                        |
| `GHRA_RATE_WINDOW_SECONDS` | API       | `3600`             | Throttle window.                                   |
| `GHRA_WAITLIST_DB`         | API       | `<output>/waitlist.db` | SQLite path (point at the mounted volume).     |
| `GHRA_TRUST_FORWARDED_FOR` | API       | off                | Only if not using uvicorn `--forwarded-allow-ips`. |
| `NEXT_PUBLIC_API_BASE`     | Frontend  | localhost:8080     | API base URL the browser calls.                    |

---

## 5. Notes & follow-ups

- **Waitlist durability:** SQLite on the mounted Fly volume survives restarts.
  For multi-instance writes, migrate the waitlist to Postgres (Neon) — only
  `SqliteWaitlistStore` needs a sibling implementation behind the existing
  `WaitlistStore` protocol.
- **Local parity:** run the API with
  `uv run --extra serve python -m uvicorn --factory src.serve.app:create_app --port 8080`
  and the frontend with `pnpm dev` in `web/`.
