"""Archive candidate detection — finds repos consistently scoring below threshold."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def find_archive_candidates(
    score_history: dict[str, list[float]],
    threshold: float = 0.15,
    min_consecutive: int = 3,
) -> list[dict]:
    """Find repos below threshold for min_consecutive runs.

    Returns [{name, last_scores, current_score}] sorted by current score ascending.
    """
    candidates = []
    for name, scores in score_history.items():
        if len(scores) < min_consecutive:
            continue
        last_n = scores[-min_consecutive:]
        if all(s < threshold for s in last_n):
            candidates.append({
                "name": name,
                "last_scores": [round(s, 3) for s in last_n],
                "current_score": round(scores[-1], 3),
            })

    candidates.sort(key=lambda c: c["current_score"])
    return candidates


def export_archive_report(
    candidates: list[dict],
    username: str,
    output_dir: Path,
) -> dict:
    """Generate archive-candidates markdown. Returns {report_path, count}."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Archive Candidates",
        "",
        f"Generated: {date} | {len(candidates)} repos identified",
        "",
    ]

    if not candidates:
        lines.append("No repos meet the archive criteria (scored below 0.15 for 3+ consecutive runs).")
    else:
        lines.append("| Repo | Last Scores | Command |")
        lines.append("|------|-------------|---------|")
        for c in candidates:
            scores_str = ", ".join(f"{s:.3f}" for s in c["last_scores"])
            cmd = f"`gh repo edit {username}/{c['name']} --visibility=private`"
            lines.append(f"| {c['name']} | {scores_str} | {cmd} |")

    lines.append("")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"archive-candidates-{date}.md"
    path.write_text("\n".join(lines))
    return {"report_path": path, "count": len(candidates)}
