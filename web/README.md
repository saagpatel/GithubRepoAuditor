# Portfolio Health — web frontend

Next.js (App Router) paste-a-username frontend for the clone-free portfolio
report. The form calls the FastAPI engine's `GET /api/report/{username}`
endpoint (from `src/serve/api.py`) and renders the result with a "top fixes"
framing: grades, repo health, and the highest-leverage actions per repo.

## Develop

Run the Python API and the web app side by side.

**1. Start the report API** (from the repo root):

```bash
uv run --extra serve python -m uvicorn --factory src.serve.app:create_app --port 8080
```

**2. Start the frontend** (from `web/`):

```bash
pnpm install
pnpm dev   # http://localhost:3000
```

## Configuration

| Env var                | Default                 | Purpose                                  |
| ---------------------- | ----------------------- | ---------------------------------------- |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8080` | Base URL of the FastAPI report API.      |

The API must allow the frontend origin via CORS (`GHRA_CORS_ORIGINS` on the API
side; defaults already include `http://localhost:3000`).

## Build

```bash
pnpm typecheck
pnpm build
```
