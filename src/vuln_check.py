"""Dependency vulnerability checking via OSV.dev API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

from src.cache import ResponseCache

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
ECOSYSTEM_MAP = {"npm": "npm", "pypi": "PyPI", "crates": "crates.io"}
BATCH_SIZE = 1000

# Sentinel params used to namespace OSV cache entries separately from GitHub API
_OSV_CACHE_PARAMS = {"__source": "osv"}


def check_vulnerabilities(
    audits: list[dict],
    cache: ResponseCache | None = None,
) -> dict[str, list[dict]]:
    """Query OSV.dev for vulnerabilities across all audited repos.

    Returns {repo_name: [{dep, vuln_id, summary, severity}]}.
    """
    # Collect all (repo, dep_name, version, ecosystem) tuples
    dep_queries: list[tuple[str, str, str, str]] = []
    for audit in audits:
        repo_name = audit.get("metadata", {}).get("name", "")
        if not repo_name:
            continue
        for result in audit.get("analyzer_results", []):
            if result.get("dimension") != "dependencies":
                continue
            details = result.get("details", {})
            dep_versions = details.get("dep_versions", [])
            for dep_name, version, ecosystem in dep_versions:
                mapped_eco = ECOSYSTEM_MAP.get(ecosystem, ecosystem)
                dep_queries.append((repo_name, dep_name, version, mapped_eco))

    if not dep_queries:
        return {}

    # Build a stable cache key from the unique (name, version, ecosystem) set
    unique_deps = tuple(sorted(set((d[1], d[2], d[3]) for d in dep_queries)))
    cache_key = f"osv-batch-{hash(unique_deps)}"

    if cache:
        cached = cache.get(cache_key, _OSV_CACHE_PARAMS)
        if cached is not None:
            return json.loads(cached)  # type: ignore[arg-type]

    # Batch query OSV.dev
    all_vulns: dict[str, list[dict]] = {}

    for i in range(0, len(dep_queries), BATCH_SIZE):
        batch = dep_queries[i : i + BATCH_SIZE]
        queries = [
            {"version": version, "package": {"name": name, "ecosystem": eco}}
            for _, name, version, eco in batch
        ]

        try:
            resp = requests.post(OSV_BATCH_URL, json={"queries": queries}, timeout=30)
            if resp.status_code != 200:
                print(f"  OSV.dev returned {resp.status_code}", file=sys.stderr)
                continue

            results = resp.json().get("results", [])
            for j, result in enumerate(results):
                vulns = result.get("vulns", [])
                if not vulns:
                    continue
                repo_name = batch[j][0]
                dep_name = batch[j][1]
                for vuln in vulns:
                    severity = ""
                    for s in vuln.get("severity", []):
                        if s.get("type") == "CVSS_V3":
                            severity = s.get("score", "")
                            break
                    entry = {
                        "dep": dep_name,
                        "vuln_id": vuln.get("id", ""),
                        "summary": vuln.get("summary", "")[:200],
                        "severity": severity,
                    }
                    all_vulns.setdefault(repo_name, []).append(entry)
        except Exception as e:
            print(f"  OSV.dev query failed: {e}", file=sys.stderr)

    if cache and all_vulns:
        cache.put(cache_key, _OSV_CACHE_PARAMS, json.dumps(all_vulns, default=str))

    return all_vulns


def format_vuln_summary(vulns: dict[str, list[dict]]) -> str:
    """Format vulnerability results for terminal output."""
    if not vulns:
        return "No known vulnerabilities found."

    total = sum(len(v) for v in vulns.values())
    repos = len(vulns)
    lines = [f"Found {total} vulnerabilities across {repos} repos:"]
    for repo, repo_vulns in sorted(vulns.items(), key=lambda x: -len(x[1]))[:10]:
        lines.append(f"  {repo}: {len(repo_vulns)} vulns")
        for v in repo_vulns[:3]:
            lines.append(f"    - {v['vuln_id']}: {v['dep']} — {v['summary'][:80]}")
    return "\n".join(lines)
