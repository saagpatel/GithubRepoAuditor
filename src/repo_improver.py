"""Improvement campaign workflow for GitHub repos.

Generates a manifest of what needs fixing across repos from audit data,
and batch-applies improvements (descriptions, topics, READMEs) via the GitHub API.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TIER_PRIORITY = {"shipped": 0, "functional": 1, "wip": 2, "skeleton": 3, "abandoned": 4}


def generate_manifest(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate a per-repo improvement manifest from an audit report.

    Returns a list of dicts sorted by priority (shipped first, then by score desc).
    Each entry contains:
    - repo: full_name (owner/name)
    - name: repo name
    - tier: completeness tier
    - score: overall score
    - language: primary language
    - current_description: str or None
    - current_topics: list[str]
    - readme_score: float
    - actions: dict of needed improvements
    - context: dict of project metadata for agent consumption
    """
    manifest: list[dict[str, Any]] = []
    for audit in report_data.get("audits", []):
        meta = audit.get("metadata", {})

        # Extract analyzer results by dimension
        analyzer_results = audit.get("analyzer_results", [])

        readme_result = next(
            (r for r in analyzer_results if r.get("dimension") == "readme"),
            {},
        )
        readme_details = readme_result.get("details", {})
        readme_score = readme_result.get("score", 0.0)

        code_quality = next(
            (r for r in analyzer_results if r.get("dimension") == "code_quality"),
            {},
        )
        cicd = next(
            (r for r in analyzer_results if r.get("dimension") == "cicd"),
            {},
        )
        structure = next(
            (r for r in analyzer_results if r.get("dimension") == "structure"),
            {},
        )
        deps = next(
            (r for r in analyzer_results if r.get("dimension") == "dependencies"),
            {},
        )

        # Build actions dict
        current_desc = meta.get("description") or None
        current_topics = meta.get("topics", []) or []

        actions = {
            "needs_description": current_desc is None,
            "needs_topics": len(current_topics) == 0,
            "needs_readme_badges": not readme_details.get("has_badges", False),
            "needs_readme_install": not readme_details.get("has_install_instructions", False),
            "needs_readme_examples": not readme_details.get("has_code_examples", False),
            "needs_readme_overhaul": readme_score < 0.5,
        }

        # Build context for agent consumption
        context = {
            "config_files": structure.get("details", {}).get("config_files", []),
            "has_tests": any(
                r.get("dimension") == "testing" and r.get("score", 0) > 0.2
                for r in analyzer_results
            ),
            "has_cicd": cicd.get("score", 0) > 0.2,
            "has_license": structure.get("details", {}).get("has_license", False),
            "entry_point": code_quality.get("details", {}).get("entry_point", ""),
            "badges_earned": audit.get("badges", []) if isinstance(audit.get("badges"), list) else audit.get("badges", {}).get("earned", []),
            "interest_tier": audit.get("interest_tier", ""),
            "dep_count": deps.get("details", {}).get("dep_count", 0),
        }

        entry: dict[str, Any] = {
            "repo": meta.get("full_name", ""),
            "name": meta.get("name", ""),
            "tier": audit.get("completeness_tier", ""),
            "score": audit.get("overall_score", 0.0),
            "language": meta.get("language", ""),
            "languages": meta.get("languages", {}),
            "current_description": current_desc,
            "current_topics": current_topics,
            "readme_score": readme_score,
            "actions": actions,
            "context": context,
        }
        manifest.append(entry)

    # Sort: shipped first (tier priority), then by score descending
    manifest.sort(key=lambda e: (TIER_PRIORITY.get(e["tier"], 99), -e["score"]))

    return manifest


def partition_by_tier(manifest: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Partition manifest entries by tier for wave-based execution."""
    tiers: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest:
        tier = entry["tier"]
        tiers.setdefault(tier, []).append(entry)
    return tiers


def partition_into_batches(
    entries: list[dict[str, Any]], batch_size: int = 10
) -> list[list[dict[str, Any]]]:
    """Split a list of manifest entries into batches for parallel agent execution."""
    return [entries[i : i + batch_size] for i in range(0, len(entries), batch_size)]


def write_manifest(manifest: list[dict[str, Any]], output_dir: Path) -> Path:
    """Write the improvement manifest to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "improvement-manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    logger.info("Wrote improvement manifest: %s (%d repos)", path, len(manifest))
    return path


def load_improvements(path: Path) -> dict[str, dict[str, Any]]:
    """Load pre-generated improvements from a JSON file.

    Expected format: {"repo_full_name": {"description": "...", "topics": [...], "readme": "..."}, ...}
    Also accepts list format: [{"repo": "owner/name", ...}, ...] which is converted to dict.
    """
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return {entry["repo"]: entry for entry in data if "repo" in entry}
    return data


def apply_metadata_updates(
    client: "GitHubClient",
    owner: str,
    updates: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Batch-apply description and topics updates via the GitHub API.

    Each update dict should have: repo (name), description (str), topics (list[str]).
    Returns a list of result dicts with ok/error status per repo.
    """
    results: list[dict[str, Any]] = []
    for update in updates:
        repo_name = update.get("name") or update.get("repo", "").split("/")[-1]
        result: dict[str, Any] = {"repo": repo_name, "actions": []}

        # Update description if provided
        desc = update.get("description")
        if desc:
            if dry_run:
                result["actions"].append({"type": "description", "dry_run": True, "value": desc})
            else:
                resp = client.update_repo_metadata(owner, repo_name, description=desc)
                result["actions"].append(
                    {"type": "description", "ok": resp.get("ok", False), "value": desc}
                )

        # Update topics if provided
        topics = update.get("topics")
        if topics:
            if dry_run:
                result["actions"].append({"type": "topics", "dry_run": True, "value": topics})
            else:
                resp = client.replace_repo_topics(owner, repo_name, topics)
                result["actions"].append(
                    {"type": "topics", "ok": resp.get("ok", False), "value": topics}
                )

        results.append(result)

    return results


def apply_readme_updates(
    client: "GitHubClient",
    owner: str,
    updates: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Batch-push README.md files via the GitHub Contents API.

    Each update dict should have: repo (name), readme (str content).
    Returns a list of result dicts with ok/error status per repo.
    """
    results: list[dict[str, Any]] = []
    for update in updates:
        repo_name = update.get("name") or update.get("repo", "").split("/")[-1]
        readme_content = update.get("readme", "")
        if not readme_content:
            continue

        result: dict[str, Any] = {"repo": repo_name}

        if dry_run:
            result["dry_run"] = True
            result["readme_length"] = len(readme_content)
            results.append(result)
            continue

        # Get current README SHA (needed for updates, None for new files)
        sha = client.get_file_sha(owner, repo_name, "README.md")

        # Encode content to base64
        content_b64 = base64.b64encode(readme_content.encode("utf-8")).decode("ascii")

        # Push the file
        resp = client.update_repo_file(
            owner,
            repo_name,
            "README.md",
            content_b64,
            "docs: update README with comprehensive project documentation",
            sha=sha,
        )
        result["ok"] = resp.get("ok", False)
        result["sha"] = resp.get("sha", "")
        results.append(result)

    return results


def apply_file_updates(
    client: "GitHubClient",
    owner: str,
    updates: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Batch-push arbitrary files to repos via the GitHub Contents API.

    Each update dict should have: name (repo name), path (file path), content (str), message (commit msg).
    Returns a list of result dicts with ok/error status per repo.
    """
    results: list[dict[str, Any]] = []
    for update in updates:
        repo_name = update.get("name") or update.get("repo", "").split("/")[-1]
        file_path = update["path"]
        content = update["content"]
        message = update.get("message", f"chore: add {file_path}")

        result: dict[str, Any] = {"repo": repo_name, "path": file_path}

        if dry_run:
            result["dry_run"] = True
            results.append(result)
            continue

        sha = client.get_file_sha(owner, repo_name, file_path)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        resp = client.update_repo_file(owner, repo_name, file_path, content_b64, message, sha=sha)
        result["ok"] = resp.get("ok", False)
        results.append(result)

    return results


def generate_execution_report(results: list[dict[str, Any]], output_dir: Path) -> Path:
    """Write execution results to a JSON file for review."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "improvement-results.json"

    summary = {
        "total": len(results),
        "successful": sum(1 for r in results if r.get("ok", True) and not r.get("dry_run")),
        "dry_run": sum(1 for r in results if r.get("dry_run")),
        "failed": sum(1 for r in results if not r.get("ok", True) and not r.get("dry_run")),
        "results": results,
    }
    path.write_text(json.dumps(summary, indent=2))
    return path
