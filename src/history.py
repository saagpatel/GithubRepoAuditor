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


def load_trend_data(history_dir: Path = HISTORY_DIR, max_runs: int = 10) -> list[dict]:
    """Load trend data from the last N archived reports.

    Returns list of {date, average_score, tier_distribution, top_repos: {name: score}}.
    """
    if not history_dir.exists():
        return []

    reports = sorted(
        history_dir.glob("audit-report-*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:max_runs]

    trends: list[dict] = []
    for report_path in reversed(reports):  # chronological order
        try:
            data = json.loads(report_path.read_text())
            # Extract per-repo scores for top 20
            top_repos: dict[str, float] = {}
            for audit in sorted(
                data.get("audits", []),
                key=lambda a: a.get("overall_score", 0),
                reverse=True,
            )[:20]:
                top_repos[audit["metadata"]["name"]] = audit["overall_score"]

            trends.append({
                "date": data.get("generated_at", "")[:10],
                "average_score": data.get("average_score", 0),
                "repos_audited": data.get("repos_audited", 0),
                "tier_distribution": data.get("tier_distribution", {}),
                "top_repos": top_repos,
            })
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return trends


def load_repo_score_history(
    history_dir: Path = HISTORY_DIR,
    max_runs: int = 10,
) -> dict[str, list[float]]:
    """Load per-repo score history across archived reports.

    Returns {repo_name: [score_run1, score_run2, ...]} in chronological order.
    """
    if not history_dir.exists():
        return {}

    reports = sorted(
        history_dir.glob("audit-report-*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:max_runs]

    history: dict[str, list[float]] = {}
    for report_path in reversed(reports):  # chronological order
        try:
            data = json.loads(report_path.read_text())
            for audit in data.get("audits", []):
                name = audit.get("metadata", {}).get("name", "")
                if name:
                    history.setdefault(name, []).append(audit.get("overall_score", 0))
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return history


def load_language_trends(
    history_dir: Path = HISTORY_DIR,
    max_runs: int = 10,
) -> list[dict]:
    """Compute per-language adoption trends across audit history.

    Returns [{language, repos_per_run: [int], current_count, category}]
    sorted by current_count descending.
    Category: "Adopt" (growing >20%), "Trial" (new), "Hold" (stable), "Decline" (shrinking >20%).
    """
    if not history_dir.exists():
        return []

    reports = sorted(
        history_dir.glob("audit-report-*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:max_runs]

    # Collect language counts per run (chronological)
    all_languages: set[str] = set()
    runs: list[dict[str, int]] = []
    for report_path in reversed(reports):
        try:
            data = json.loads(report_path.read_text())
            lang_counts: dict[str, int] = {}
            for audit in data.get("audits", []):
                lang = audit.get("metadata", {}).get("language")
                if lang:
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                    all_languages.add(lang)
            runs.append(lang_counts)
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    if not runs:
        return []

    # Build per-language trend
    trends: list[dict] = []
    for lang in all_languages:
        repos_per_run = [run.get(lang, 0) for run in runs]
        current = repos_per_run[-1] if repos_per_run else 0

        # Categorize
        if len(repos_per_run) < 2:
            category = "Hold"
        elif repos_per_run[0] == 0 and current > 0:
            category = "Trial"
        elif current == 0:
            category = "Decline"
        else:
            first_nonzero = next((v for v in repos_per_run if v > 0), current)
            change = (current - first_nonzero) / first_nonzero if first_nonzero else 0
            if change > 0.2:
                category = "Adopt"
            elif change < -0.2:
                category = "Decline"
            else:
                category = "Hold"

        trends.append({
            "language": lang,
            "repos_per_run": repos_per_run,
            "current_count": current,
            "category": category,
        })

    trends.sort(key=lambda t: t["current_count"], reverse=True)
    return trends


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


# ── Fingerprints for incremental audits ──────────────────────────────

FINGERPRINT_PATH = Path("output/.audit-fingerprints.json")


def save_fingerprints(
    audits: list[dict],
    path: Path = FINGERPRINT_PATH,
) -> Path:
    """Save per-repo fingerprints for incremental audit detection."""
    fingerprints: dict[str, dict] = {}
    for audit in audits:
        meta = audit.get("metadata", {})
        name = meta.get("name", "")
        if name:
            fingerprints[name] = {
                "pushed_at": meta.get("pushed_at"),
                "overall_score": audit.get("overall_score", 0),
                "completeness_tier": audit.get("completeness_tier", ""),
            }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fingerprints, indent=2))
    return path


def load_fingerprints(path: Path = FINGERPRINT_PATH) -> dict[str, dict]:
    """Load previously saved fingerprints."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
