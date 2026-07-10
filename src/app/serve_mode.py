from __future__ import annotations

import sys
from pathlib import Path


def run_serve_mode(args: object) -> None:
    """Launch the local FastAPI + HTMX web UI (requires [serve] extra)."""
    try:
        from src.serve.app import run_serve
    except ImportError:
        sys.exit("audit serve requires the [serve] extra.\nInstall with: pip install -e '.[serve]'")
    output_dir = Path(getattr(args, "output_dir", "output"))
    run_serve(
        port=getattr(args, "port", 8080),
        host=getattr(args, "host", "127.0.0.1"),
        output_dir=output_dir,
    )
