"""Notion signal event export — generates normalized audit events for Notion's external signal pipeline.

Produces a JSON file matching the NormalizedSignalEvent schema from the
Notion Operating System's external-signal-sync.ts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _severity_from_grade(grade: str) -> str:
    """Map letter grade to Notion signal severity."""
    if grade in ("A", "B"):
        return "Info"
    if grade in ("C", "D"):
        return "Watch"
    return "Risk"


def _build_event_key(repo_name: str, date: str, grade: str) -> str:
    """Build a deduplication key matching Notion's buildEventKey convention."""
    return f"audit::report::{repo_name.lower()}::{date}::{grade.lower()}"


def _find_biggest_drag(audit: dict) -> tuple[str, float]:
    """Find the lowest-scoring completeness dimension."""
    dim_scores = {
        r["dimension"]: r["score"]
        for r in audit.get("analyzer_results", [])
        if r["dimension"] != "interest"
    }
    if not dim_scores:
        return ("none", 0.0)
    worst = min(dim_scores, key=dim_scores.get)
    return (worst, dim_scores[worst])


def _normalize_audit_event(
    audit: dict,
    date: str,
    mapping: dict[str, dict],
) -> dict | None:
    """Convert a single audit dict to a normalized signal event."""
    meta = audit.get("metadata", {})
    name = meta.get("name", "")
    if not name:
        return None

    project = mapping.get(name)
    if not project:
        return None

    grade = audit.get("grade", "F")
    tier = audit.get("completeness_tier", "abandoned")
    score = audit.get("overall_score", 0)
    badges = audit.get("badges", [])
    drag_dim, drag_score = _find_biggest_drag(audit)

    # Build raw excerpt with dimension scores
    dim_scores = {
        r["dimension"]: round(r["score"], 2)
        for r in audit.get("analyzer_results", [])
    }
    raw = json.dumps({
        "dimensions": dim_scores,
        "badges": badges,
        "flags": audit.get("flags", []),
        "interest_score": audit.get("interest_score", 0),
    })
    # Notion rich_text limit is 2000 chars
    if len(raw) > 2000:
        raw = raw[:1997] + "..."

    return {
        "title": f"Audit: {name} — Grade {grade}, Tier {tier}",
        "localProjectId": project["localProjectId"],
        "sourceId": project.get("sourceId", ""),
        "provider": "Audit",
        "signalType": "Audit Report",
        "occurredAt": date,
        "status": grade,
        "environment": "N/A",
        "severity": _severity_from_grade(grade),
        "sourceIdValue": f"audit-{date}-{name}",
        "sourceUrl": meta.get("html_url", ""),
        "eventKey": _build_event_key(name, date, grade),
        "summary": (
            f"Score {score:.2f}, tier {tier}, {len(badges)} badges. "
            f"Drag: {drag_dim} ({drag_score:.1f})"
        ),
        "rawExcerpt": raw,
    }


def _load_project_map(config_dir: Path) -> dict[str, dict]:
    """Load repo name → Notion project mapping."""
    path = config_dir / "notion-project-map.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def generate_project_map(notion_sources_path: Path, output_path: Path) -> int:
    """Extract repo→UUID mapping from Notion signal sources config."""
    data = json.loads(notion_sources_path.read_text())
    seeds = data.get("manualSeeds", [])
    mapping = {}
    for s in seeds:
        if s.get("provider") == "GitHub" and s.get("identifier"):
            repo_name = s["identifier"].split("/")[-1]
            mapping[repo_name] = {"localProjectId": s["localProjectId"]}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(mapping, indent=2))
    return len(mapping)


def export_notion_events(
    report_data: dict,
    output_dir: Path,
    config_dir: Path = Path("config"),
) -> dict:
    """Generate Notion audit event JSON. Returns {events_path, event_count, unmapped}."""
    mapping = _load_project_map(config_dir)
    date = report_data.get("generated_at", "")[:10]
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    events = []
    unmapped = []

    for audit in report_data.get("audits", []):
        name = audit.get("metadata", {}).get("name", "")
        if not name:
            continue
        event = _normalize_audit_event(audit, date, mapping)
        if event:
            events.append(event)
        else:
            unmapped.append(name)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "events": events,
        "unmapped_repos": unmapped,
        "stats": {
            "total_repos": len(report_data.get("audits", [])),
            "mapped_repos": len(events),
            "unmapped_repos": len(unmapped),
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / f"notion-audit-events-{date}.json"
    events_path.write_text(json.dumps(output, indent=2))

    return {
        "events_path": events_path,
        "event_count": len(events),
        "unmapped": unmapped,
    }
