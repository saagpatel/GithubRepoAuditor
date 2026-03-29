"""Cross-repo dependency graph — identifies shared libraries across the portfolio."""

from __future__ import annotations


def build_dependency_graph(audits: list[dict]) -> dict:
    """Build a shared dependency map from audit results.

    Returns {shared_deps: [{name, repos, count}], repo_dep_counts: {repo: count}}.
    """
    repo_deps: dict[str, set[str]] = {}

    for audit in audits:
        repo_name = audit.get("metadata", {}).get("name", "")
        if not repo_name:
            continue
        dep_details = next(
            (r.get("details", {}) for r in audit.get("analyzer_results", [])
             if r.get("dimension") == "dependencies"),
            {},
        )
        dep_names = dep_details.get("dependency_names", [])
        if dep_names:
            repo_deps[repo_name] = set(dep_names)

    # Invert: dep -> repos
    dep_repos: dict[str, list[str]] = {}
    for repo, deps in repo_deps.items():
        for dep in deps:
            dep_repos.setdefault(dep, []).append(repo)

    # Only keep deps shared by 2+ repos
    shared = [
        {"name": name, "repos": sorted(repos), "count": len(repos)}
        for name, repos in dep_repos.items()
        if len(repos) >= 2
    ]
    shared.sort(key=lambda x: (-x["count"], x["name"]))

    return {
        "shared_deps": shared[:50],
        "repo_dep_counts": {r: len(d) for r, d in repo_deps.items()},
    }


def find_vulnerability_impact(audits: list[dict], dep_name: str) -> list[str]:
    """Return list of repo names that use the given dependency."""
    graph = build_dependency_graph(audits)
    for dep in graph["shared_deps"]:
        if dep["name"] == dep_name:
            return dep["repos"]
    # Check non-shared deps too
    for audit in audits:
        repo_name = audit.get("metadata", {}).get("name", "")
        dep_details = next(
            (r.get("details", {}) for r in audit.get("analyzer_results", [])
             if r.get("dimension") == "dependencies"),
            {},
        )
        if dep_name in dep_details.get("dependency_names", []):
            return [repo_name]
    return []
