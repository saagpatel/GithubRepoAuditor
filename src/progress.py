"""Audit progress persistence — save/resume partial audit runs."""
from __future__ import annotations

import json
import os
from pathlib import Path

PROGRESS_FILE = ".audit-progress.json"


def save_progress(output_dir: Path, completed_audits: list[dict], run_metadata: dict) -> None:
    """Atomically save completed repo audits to progress file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / PROGRESS_FILE
    tmp_path = progress_path.with_suffix(".tmp")

    data = {
        "run_metadata": run_metadata,
        "completed": completed_audits,
    }
    tmp_path.write_text(json.dumps(data, default=str))
    os.replace(str(tmp_path), str(progress_path))


def load_progress(output_dir: Path) -> tuple[list[dict], dict] | None:
    """Load saved progress. Returns (completed_audits, run_metadata) or None."""
    progress_path = output_dir / PROGRESS_FILE
    if not progress_path.is_file():
        return None
    try:
        data = json.loads(progress_path.read_text())
        return data.get("completed", []), data.get("run_metadata", {})
    except (json.JSONDecodeError, KeyError):
        return None


def clear_progress(output_dir: Path) -> None:
    """Remove progress file after successful completion."""
    progress_path = output_dir / PROGRESS_FILE
    if progress_path.is_file():
        progress_path.unlink()
