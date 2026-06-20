"""FastAPI application factory and uvicorn launcher for audit serve."""

from __future__ import annotations

from pathlib import Path


def create_app(output_dir: Path | None = None) -> "FastAPI":  # noqa: F821
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles

    from src.serve.api import cors_origins
    from src.serve.api import router as api_router
    from src.serve.hosting import (
        build_kv_store,
        build_rate_limiter,
        build_report_cache,
    )
    from src.serve.routes import router

    app = FastAPI(
        title="Audit Serve",
        description="Local portfolio dashboard for GitHub Repo Auditor",
        version="1.0.0",
    )

    # CORS so the Next.js frontend can call /api/report from the browser. Only
    # GET is exposed; no credentials (the endpoint is public + unauthenticated).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Resolve output dir — default to ./output relative to cwd
    app.state.output_dir = output_dir or (Path.cwd() / "output")

    # Hosting guards for the public report endpoint: one shared KV store backs
    # both the report cache and the per-IP throttle (in-memory unless a Redis
    # URL is configured). Built once per app so state is shared across requests.
    kv_store = build_kv_store()
    app.state.report_cache = build_report_cache(kv_store)
    app.state.rate_limiter = build_rate_limiter(kv_store)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(api_router)
    app.include_router(router)
    return app


def run_serve(
    port: int = 8080, host: str = "127.0.0.1", output_dir: Path | None = None
) -> None:
    """Launch uvicorn with the audit serve app."""
    import uvicorn

    app = create_app(output_dir=output_dir)
    print(f"audit serve → http://{host}:{port}/")
    uvicorn.run(app, host=host, port=port)
