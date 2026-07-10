"""Leaf report-discovery and artifact-time helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def load_latest_report(output_dir: Path) -> tuple[Path | None, dict | None]:
    reports = sorted(
        output_dir.glob("audit-report-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None, None
    latest = reports[0]
    return latest, json.loads(latest.read_text())


def report_artifact_datetime(report_path: Path | None, fallback: datetime) -> datetime:
    if report_path:
        stem = report_path.stem
        if len(stem) >= 10:
            parsed = datetime.fromisoformat(f"{stem[-10:]}T00:00:00+00:00")
            return parsed
    return fallback
