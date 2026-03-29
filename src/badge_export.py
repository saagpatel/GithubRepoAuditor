"""Shields.io badge export — generates badge JSON, static URLs, and badges.md.

Produces per-repo grade/tier badges for shipped+functional repos,
portfolio-level badges, and an optional Gist upload for endpoint badges.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from src.scorer import letter_grade

# ── Color mappings ──────────────────────────────────────────────────

GRADE_COLORS = {
    "A": "brightgreen",
    "B": "green",
    "C": "yellow",
    "D": "orange",
    "F": "red",
}

TIER_COLORS = {
    "shipped": "brightgreen",
    "functional": "blue",
    "wip": "yellow",
    "skeleton": "orange",
    "abandoned": "lightgrey",
}

ELIGIBLE_TIERS = {"shipped", "functional"}

# ── Shield helpers ──────────────────────────────────────────────────


def _make_shield_json(label: str, message: str, color: str) -> dict:
    """Build a shields.io endpoint badge JSON object."""
    return {
        "schemaVersion": 1,
        "label": label,
        "message": str(message),
        "color": color,
    }


def _shields_escape(text: str) -> str:
    """Escape text for shields.io static badge URLs.

    Shields.io uses - as separator, so literal dashes become --,
    underscores become __, and spaces become %20.
    """
    return text.replace("-", "--").replace("_", "__").replace(" ", "%20")


def _static_badge_url(label: str, message: str, color: str) -> str:
    """Build a shields.io static badge URL."""
    return (
        f"https://img.shields.io/badge/"
        f"{_shields_escape(label)}-{_shields_escape(message)}-{color}"
    )


def _endpoint_badge_url(raw_url: str) -> str:
    """Build a shields.io endpoint badge URL from a JSON raw URL."""
    return f"https://img.shields.io/endpoint?url={quote(raw_url, safe='')}"


# ── File writers ────────────────────────────────────────────────────


def _write_portfolio_badges(report_data: dict, badges_dir: Path) -> list[Path]:
    """Write portfolio-level shield JSON files."""
    grade = report_data.get("portfolio_grade", "F")
    grade_color = GRADE_COLORS.get(grade, "red")
    repos_audited = report_data.get("repos_audited", 0)
    avg_score = report_data.get("average_score", 0)
    avg_grade = letter_grade(avg_score)
    shipped = report_data.get("tier_distribution", {}).get("shipped", 0)

    badges = [
        ("portfolio-grade", _make_shield_json("portfolio", grade, grade_color)),
        ("portfolio-repos", _make_shield_json("repos audited", str(repos_audited), "blue")),
        ("portfolio-shipped", _make_shield_json("shipped", str(shipped), "brightgreen")),
        ("portfolio-avg-score", _make_shield_json("avg score", f"{avg_score:.2f}", GRADE_COLORS.get(avg_grade, "yellow"))),
    ]

    paths = []
    for name, data in badges:
        path = badges_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2))
        paths.append(path)
    return paths


def _write_repo_badges(audit_dict: dict, repos_dir: Path) -> list[Path]:
    """Write grade + tier shield JSON for a single repo."""
    name = audit_dict["metadata"]["name"]
    grade = audit_dict.get("grade", "F")
    tier = audit_dict.get("completeness_tier", "abandoned")

    paths = []
    for suffix, label, message, color in [
        ("grade", "grade", grade, GRADE_COLORS.get(grade, "red")),
        ("tier", "tier", tier, TIER_COLORS.get(tier, "lightgrey")),
    ]:
        path = repos_dir / f"{name}-{suffix}.json"
        path.write_text(json.dumps(_make_shield_json(label, message, color), indent=2))
        paths.append(path)
    return paths


def _write_badges_markdown(
    report_data: dict,
    badges_dir: Path,
    gist_urls: dict[str, str] | None = None,
) -> Path:
    """Generate badges.md with copy-pasteable shield markdown."""
    username = report_data.get("username", "unknown")
    grade = report_data.get("portfolio_grade", "F")
    repos_audited = report_data.get("repos_audited", 0)
    avg_score = report_data.get("average_score", 0)
    shipped = report_data.get("tier_distribution", {}).get("shipped", 0)
    avg_grade = letter_grade(avg_score)

    lines = [
        f"# Shields.io Badges for {username}",
        "",
        f"Generated: {report_data.get('generated_at', '')[:10]}",
        "",
        "## Portfolio Badges",
        "",
        f"![portfolio]({_static_badge_url('portfolio', grade, GRADE_COLORS.get(grade, 'red'))})",
        f"![repos audited]({_static_badge_url('repos audited', str(repos_audited), 'blue')})",
        f"![shipped]({_static_badge_url('shipped', str(shipped), 'brightgreen')})",
        f"![avg score]({_static_badge_url('avg score', f'{avg_score:.2f}', GRADE_COLORS.get(avg_grade, 'yellow'))})",
        "",
    ]

    # Per-repo badges grouped by tier
    lines.append("## Per-Repo Badges")
    lines.append("")

    audits = report_data.get("audits", [])
    for tier in ["shipped", "functional"]:
        tier_repos = [
            a for a in audits if a.get("completeness_tier") == tier
        ]
        if not tier_repos:
            continue
        tier_repos.sort(key=lambda a: a.get("overall_score", 0), reverse=True)
        lines.append(f"### {tier.capitalize()} ({len(tier_repos)})")
        lines.append("")
        for a in tier_repos:
            name = a["metadata"]["name"]
            g = a.get("grade", "F")
            t = a.get("completeness_tier", "abandoned")
            grade_url = _static_badge_url(name, g, GRADE_COLORS.get(g, "red"))
            tier_url = _static_badge_url(name, t, TIER_COLORS.get(t, "lightgrey"))
            lines.append(f"**{name}** ![grade]({grade_url}) ![tier]({tier_url})")
        lines.append("")

    # Endpoint badges section (if gist uploaded)
    if gist_urls:
        lines.append("## Endpoint Badges (auto-updating)")
        lines.append("")
        lines.append("These badges update automatically when you re-run with `--upload-badges`.")
        lines.append("")
        for filename, raw_url in sorted(gist_urls.items()):
            label = filename.replace(".json", "")
            lines.append(f"![{label}]({_endpoint_badge_url(raw_url)})")
        lines.append("")

    # Usage section
    lines.append("## Usage")
    lines.append("")
    lines.append("Copy any badge markdown above into your GitHub README.")
    lines.append("")
    lines.append("```markdown")
    lines.append(f"![portfolio]({_static_badge_url('portfolio', grade, GRADE_COLORS.get(grade, 'red'))})")
    lines.append("```")
    lines.append("")

    path = badges_dir / "badges.md"
    path.write_text("\n".join(lines))
    return path


# ── Main entry point ────────────────────────────────────────────────


def export_badges(report_data: dict, output_dir: Path) -> dict:
    """Generate all badge files. Returns {badges_dir, files_written, badges_md}."""
    badges_dir = output_dir / "badges"
    repos_dir = badges_dir / "repos"
    badges_dir.mkdir(parents=True, exist_ok=True)
    repos_dir.mkdir(parents=True, exist_ok=True)

    files_written = 0

    # Portfolio badges
    portfolio_paths = _write_portfolio_badges(report_data, badges_dir)
    files_written += len(portfolio_paths)

    # Per-repo badges (shipped + functional only)
    for audit in report_data.get("audits", []):
        if audit.get("completeness_tier") in ELIGIBLE_TIERS:
            repo_paths = _write_repo_badges(audit, repos_dir)
            files_written += len(repo_paths)

    # Badges markdown
    badges_md = _write_badges_markdown(report_data, badges_dir)
    files_written += 1

    return {
        "badges_dir": badges_dir,
        "files_written": files_written,
        "badges_md": badges_md,
    }


# ── Gist upload ─────────────────────────────────────────────────────


def _load_gist_id(output_dir: Path) -> str | None:
    """Load previously saved gist ID."""
    path = output_dir / ".badge-gist-id"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text()).get("gist_id")
    except (json.JSONDecodeError, OSError):
        return None


def _save_gist_id(output_dir: Path, gist_id: str) -> None:
    """Save gist ID for future updates."""
    path = output_dir / ".badge-gist-id"
    path.write_text(json.dumps({"gist_id": gist_id}))


def upload_badge_gist(
    badges_dir: Path,
    username: str,
) -> dict[str, str] | None:
    """Upload badge JSON files to a GitHub Gist. Returns {filename: raw_url} or None."""
    output_dir = badges_dir.parent

    # Collect all JSON files
    json_files: dict[str, str] = {}
    for path in sorted(badges_dir.glob("*.json")):
        json_files[path.name] = path.read_text()
    repos_dir = badges_dir / "repos"
    if repos_dir.is_dir():
        for path in sorted(repos_dir.glob("*.json")):
            json_files[path.name] = path.read_text()

    if not json_files:
        print("  No badge files to upload.", file=sys.stderr)
        return None

    # Build gist payload
    gist_files = {name: {"content": content} for name, content in json_files.items()}
    payload = json.dumps({
        "description": f"GitHub Portfolio Badges for {username}",
        "public": True,
        "files": gist_files,
    })

    gist_id = _load_gist_id(output_dir)

    try:
        if gist_id:
            # Update existing gist
            result = subprocess.run(
                ["gh", "api", "-X", "PATCH", f"gists/{gist_id}", "--input", "-"],
                input=payload, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                # Gist may have been deleted — fall back to create
                gist_id = None

        if not gist_id:
            # Create new gist
            result = subprocess.run(
                ["gh", "api", "gists", "--input", "-"],
                input=payload, capture_output=True, text=True, timeout=30,
            )

        if result.returncode != 0:
            print(f"  Gist upload failed: {result.stderr.strip()}", file=sys.stderr)
            return None

        response = json.loads(result.stdout)
        new_gist_id = response.get("id", "")
        if not new_gist_id:
            print("  Gist upload: no ID in response.", file=sys.stderr)
            return None

        _save_gist_id(output_dir, new_gist_id)

        # Build raw URLs (unversioned for auto-updating)
        owner = response.get("owner", {}).get("login", username)
        raw_urls = {
            name: f"https://gist.githubusercontent.com/{owner}/{new_gist_id}/raw/{name}"
            for name in json_files
        }

        print(f"  Gist: https://gist.github.com/{new_gist_id}", file=sys.stderr)
        return raw_urls

    except FileNotFoundError:
        print("  gh CLI not found. Install gh to upload badges.", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("  Gist upload timed out.", file=sys.stderr)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Gist upload error: {exc}", file=sys.stderr)
        return None
