# API server image for the hosted clone-free report (FastAPI engine).
# The Next.js frontend deploys separately to Vercel — see DEPLOY.md.
FROM python:3.12-slim

# uv for fast, reproducible, lockfile-pinned installs.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install dependencies only (the app runs from the source tree via `src.*`
# imports, so the project itself isn't packaged). Cached unless deps change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra serve --extra hosting

COPY src ./src

EXPOSE 8080
# --forwarded-allow-ips=* so uvicorn rewrites the client address from the
# platform proxy's X-Forwarded-For, making the per-IP throttle see real clients.
CMD ["uv", "run", "--no-sync", "python", "-m", "uvicorn", \
     "--factory", "src.serve.app:create_app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--forwarded-allow-ips", "*"]
