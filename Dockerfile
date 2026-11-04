# API server image for the hosted clone-free report (FastAPI engine).
# The Next.js frontend deploys separately to Vercel — see DEPLOY.md.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

# uv for fast, reproducible, lockfile-pinned installs.
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Install dependencies only (the app runs from the source tree via `github_repo_auditor.*`
# imports, so the project itself isn't packaged). Cached unless deps change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev --extra serve --extra hosting

COPY src ./src

EXPOSE 8080
# Do not trust spoofable forwarded headers by default. Deployments behind a
# known proxy can opt in with GHRA_TRUST_FORWARDED_FOR and a platform-specific
# Uvicorn forwarded-allow-ips override.
CMD ["uv", "run", "--no-sync", "python", "-m", "uvicorn", \
     "--factory", "github_repo_auditor.serve.app:create_app", \
     "--host", "0.0.0.0", "--port", "8080"]
