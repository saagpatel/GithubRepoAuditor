from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

MONTHS_6 = 180  # days
MONTHS_12 = 365
MONTHS_3_WEEKS = 13  # ~13 weeks in 3 months


class ActivityAnalyzer(BaseAnalyzer):
    name = "activity"
    weight = 0.15

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}
        now = datetime.now(timezone.utc)

        # Pushed within 6 months / 1 year
        if metadata.pushed_at:
            days_since = (now - metadata.pushed_at).days
            details["days_since_push"] = days_since

            if days_since <= MONTHS_6:
                score += 0.3
                findings.append(f"Active: pushed {days_since}d ago")
            elif days_since <= MONTHS_12:
                score += 0.2
                findings.append(f"Recent: pushed {days_since}d ago (within 1yr)")
            else:
                findings.append(f"Stale: last push {days_since}d ago")
        else:
            findings.append("No push date available")

        # Not archived
        details["archived"] = metadata.archived
        if not metadata.archived:
            score += 0.1
            findings.append("Not archived")
        else:
            findings.append("Repo is archived")

        # API-based checks
        if github_client:
            owner = metadata.full_name.split("/")[0]

            # Total commits >10
            contributor_stats = github_client.get_contributor_stats(
                owner, metadata.name
            )
            total_commits = sum(
                c.get("total", 0) for c in contributor_stats
            )
            details["total_commits"] = total_commits

            if total_commits > 10:
                score += 0.2
                findings.append(f"Total commits: {total_commits}")
            elif total_commits > 0:
                score += 0.1
                findings.append(f"Few commits: {total_commits}")
            else:
                findings.append("Zero or unknown commit count")

            # Commits in last 3 months
            commit_activity = github_client.get_commit_activity(
                owner, metadata.name
            )
            recent_commits = _recent_commit_count(commit_activity)
            details["recent_3mo_commits"] = recent_commits

            if recent_commits > 0:
                score += 0.2
                findings.append(f"Recent commits (3mo): {recent_commits}")
            else:
                findings.append("No commits in last 3 months")

            # Commit pattern classification
            pattern = _classify_commit_pattern(commit_activity)
            details["commit_pattern"] = pattern
            findings.append(f"Commit pattern: {pattern}")

            # Bus factor
            bus_factor = _compute_bus_factor(contributor_stats)
            details["bus_factor"] = bus_factor
            if bus_factor > 0:
                findings.append(f"Bus factor: {bus_factor}")
        else:
            findings.append("Skipped API-based activity checks")

        return self._result(score, findings, details)


def _recent_commit_count(weekly_activity: list[dict]) -> int:
    """Sum commits from the last ~13 weeks of activity data."""
    if not weekly_activity:
        return 0

    # commit_activity returns 52 weeks, most recent last
    recent_weeks = weekly_activity[-MONTHS_3_WEEKS:]
    return sum(week.get("total", 0) for week in recent_weeks)


def _classify_commit_pattern(weekly_activity: list[dict]) -> str:
    """Classify the commit pattern from 52 weeks of data."""
    if not weekly_activity:
        return "unknown"

    totals = [week.get("total", 0) for week in weekly_activity]
    total = sum(totals)

    if total == 0:
        return "dormant"

    active_weeks = sum(1 for t in totals if t > 0)
    last_26 = totals[-26:]
    last_13 = totals[-13:]
    first_39 = totals[:39]

    last_26_total = sum(last_26)
    last_13_total = sum(last_13)
    first_39_total = sum(first_39)

    # Dormant: 0 commits in last 26 weeks
    if last_26_total == 0:
        return "dormant"

    # New: all commits in last 13 weeks
    if last_13_total == total and first_39_total == 0:
        return "new"

    # Steady: commits spread across 20+ weeks
    if active_weeks >= 20:
        return "steady"

    # Winding down: last 13 weeks < 25% of total
    if total > 0 and last_13_total < total * 0.25 and first_39_total > total * 0.5:
        return "winding-down"

    # Burst: >80% of commits in <8 weeks
    sorted_weeks = sorted(totals, reverse=True)
    top_8 = sum(sorted_weeks[:8])
    if top_8 >= total * 0.8 and active_weeks < 15:
        return "burst"

    # Seasonal: 2+ distinct clusters
    clusters = _count_clusters(totals)
    if clusters >= 2:
        return "seasonal"

    return "burst"  # default for concentrated activity


def _count_clusters(totals: list[int], min_gap: int = 4) -> int:
    """Count distinct clusters of consecutive active weeks."""
    clusters = 0
    in_cluster = False
    gap = 0

    for t in totals:
        if t > 0:
            if not in_cluster:
                clusters += 1
                in_cluster = True
            gap = 0
        else:
            gap += 1
            if gap >= min_gap:
                in_cluster = False

    return clusters


def _compute_bus_factor(contributor_stats: list[dict]) -> int:
    """Minimum contributors whose commits account for >= 50% of total."""
    if not contributor_stats:
        return 0

    totals = sorted(
        [c.get("total", 0) for c in contributor_stats],
        reverse=True,
    )
    total_commits = sum(totals)
    if total_commits == 0:
        return 0

    running = 0
    for i, count in enumerate(totals, 1):
        running += count
        if running >= total_commits * 0.5:
            return i

    return len(totals)
