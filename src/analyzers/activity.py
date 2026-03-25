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
