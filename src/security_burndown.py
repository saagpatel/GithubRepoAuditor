"""Security burndown builder — turns per-alert Dependabot detail into an
actionable, ranked list of advisories to fix.

Filters to: runtime-scope, fixable (first_patched_version present),
critical or high severity only.  Groups alerts by advisory (ghsa_id or
ecosystem+package+version key) so clone-repos collapse into one entry.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class BurndownEntry:
    """One advisory that should be fixed — may span multiple repos."""

    package: str
    ecosystem: str
    severity: str  # "critical" | "high"
    ghsa_id: str | None
    first_patched_version: str
    affected_repos: tuple[str, ...]  # sorted unique repo names
    affected_repo_count: int

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class BurndownReport:
    """Aggregated burndown result for a full portfolio snapshot."""

    entries: tuple[BurndownEntry, ...]
    distinct_advisories: int
    total_repo_instances: int  # sum of affected_repo_count across entries
    repos_touched: int  # distinct repos that appear in at least one entry

    def to_dict(self) -> dict:
        return {
            "distinct_advisories": self.distinct_advisories,
            "total_repo_instances": self.total_repo_instances,
            "repos_touched": self.repos_touched,
            "entries": [e.to_dict() for e in self.entries],
        }


# ── Severity ordering for ranking ──────────────────────────────────────────
_SEVERITY_RANK: dict[str, int] = {"critical": 0, "high": 1}


def _advisory_key(detail: dict) -> str | tuple:
    """Stable group key for deduplicating the same advisory across repos."""
    ghsa = detail.get("ghsa_id")
    if ghsa:
        return ghsa
    return (
        detail.get("ecosystem") or "",
        detail.get("package") or "",
        detail.get("first_patched_version") or "",
    )


def build_security_burndown(ghas_data: dict[str, dict]) -> BurndownReport:
    """Build a ranked burndown report from per-repo GHAS alert detail.

    Args:
        ghas_data: mapping of repo_name → GHAS entry dict, as produced by
                   ``fetch_ghas_alerts``.  Each entry may carry a
                   ``dependabot_details`` list; entries without it are skipped.

    Returns:
        BurndownReport with entries ranked: critical before high,
        then affected-repo-count descending, then package name ascending.
    """
    # advisory_key → {severity_set, repos_set, representative_detail}
    groups: dict[str | tuple, dict] = {}

    for repo_name, repo_data in ghas_data.items():
        details = repo_data.get("dependabot_details")
        if not isinstance(details, list):
            continue

        for detail in details:
            scope = detail.get("scope")
            severity = (detail.get("severity") or "").lower()
            first_patched = detail.get("first_patched_version")

            # Filter: runtime scope only (exclude "development" and None)
            if scope != "runtime":
                continue
            # Filter: fixable only
            if not first_patched:
                continue
            # Filter: critical or high severity only
            if severity not in _SEVERITY_RANK:
                continue

            key = _advisory_key(detail)
            if key not in groups:
                groups[key] = {
                    "severities": set(),
                    "repos": set(),
                    "detail": detail,
                }
            groups[key]["severities"].add(severity)
            groups[key]["repos"].add(repo_name)

    # Build BurndownEntry list
    entries: list[BurndownEntry] = []
    for group in groups.values():
        det = group["detail"]
        # Highest severity in the group (critical > high)
        best_severity = min(group["severities"], key=lambda s: _SEVERITY_RANK[s])
        sorted_repos = tuple(sorted(group["repos"]))
        entries.append(
            BurndownEntry(
                package=det.get("package") or "",
                ecosystem=det.get("ecosystem") or "",
                severity=best_severity,
                ghsa_id=det.get("ghsa_id"),
                first_patched_version=det.get("first_patched_version") or "",
                affected_repos=sorted_repos,
                affected_repo_count=len(sorted_repos),
            )
        )

    # Rank: critical before high → repo count desc → package asc
    entries.sort(
        key=lambda e: (
            _SEVERITY_RANK.get(e.severity, 99),
            -e.affected_repo_count,
            e.package.lower(),
        )
    )

    all_repos_touched: set[str] = set()
    total_instances = 0
    for e in entries:
        all_repos_touched.update(e.affected_repos)
        total_instances += e.affected_repo_count

    return BurndownReport(
        entries=tuple(entries),
        distinct_advisories=len(entries),
        total_repo_instances=total_instances,
        repos_touched=len(all_repos_touched),
    )


def render_burndown_markdown(report: BurndownReport) -> str:
    """Render the burndown report as a Markdown document.

    Produces a ``# Security Burndown`` heading, a summary line, and a ranked
    table of advisories.  When the report is empty, emits a clean-bill line.
    """
    lines: list[str] = ["# Security Burndown", ""]

    if not report.entries:
        lines.append("No fixable prod-reachable high/critical advisories — clear.")
        return "\n".join(lines)

    lines.append(
        f"{report.distinct_advisories} fixable runtime advisories "
        f"across {report.repos_touched} repo(s) "
        f"({report.total_repo_instances} total repo-instances)."
    )
    lines.append("")
    lines.append("| Advisory | Severity | Fix → version | Affected repos |")
    lines.append("|---|---|---|---|")

    for entry in report.entries:
        advisory_label = entry.ghsa_id or f"{entry.ecosystem}/{entry.package}"
        severity_label = entry.severity.upper()
        fix_version = entry.first_patched_version

        if entry.affected_repo_count <= 4:
            repos_label = ", ".join(entry.affected_repos)
        else:
            # Inline first 4, then note the remainder
            shown = ", ".join(entry.affected_repos[:4])
            extra = entry.affected_repo_count - 4
            repos_label = f"{shown} (+{extra} more)"

        lines.append(f"| {advisory_label} | {severity_label} | {fix_version} | {repos_label} |")

    return "\n".join(lines)
