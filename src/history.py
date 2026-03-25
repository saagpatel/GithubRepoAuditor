from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


HISTORY_DIR = Path("output/history")


def archive_report(report_path: Path, history_dir: Path = HISTORY_DIR) -> Path:
    """Copy the current audit report to the history directory.

    Returns the path of the archived copy.
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    dest = history_dir / report_path.name
    shutil.copy2(report_path, dest)

    # Update the history index
    _update_index(dest, history_dir)

    return dest


def find_previous(current_name: str, history_dir: Path = HISTORY_DIR) -> Path | None:
    """Find the most recent archived report that isn't the current one.

    Returns the path, or None if no previous report exists.
    """
    if not history_dir.exists():
        return None

    reports = sorted(
        [
            f for f in history_dir.glob("audit-report-*.json")
            if f.name != current_name
        ],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    return reports[0] if reports else None


def load_history_index(history_dir: Path = HISTORY_DIR) -> list[dict]:
    """Load the history index, or return empty list if none exists."""
    index_path = history_dir / "index.json"
    if not index_path.is_file():
        return []
    try:
        return json.loads(index_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _update_index(report_path: Path, history_dir: Path) -> None:
    """Add an entry to the history index."""
    index_path = history_dir / "index.json"
    index = load_history_index(history_dir)

    try:
        data = json.loads(report_path.read_text())
        entry = {
            "filename": report_path.name,
            "generated_at": data.get("generated_at", ""),
            "repos_audited": data.get("repos_audited", 0),
            "average_score": data.get("average_score", 0),
            "tier_distribution": data.get("tier_distribution", {}),
        }
    except (json.JSONDecodeError, OSError):
        entry = {
            "filename": report_path.name,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }

    # Avoid duplicates
    index = [e for e in index if e.get("filename") != report_path.name]
    index.append(entry)

    # Keep sorted by date, most recent first
    index.sort(key=lambda e: e.get("generated_at", ""), reverse=True)

    index_path.write_text(json.dumps(index, indent=2))
