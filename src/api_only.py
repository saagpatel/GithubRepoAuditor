"""Clone-free portfolio scoring from the GitHub API alone.

Lists a user's repos, materializes a sparse API-sourced skeleton for each
(``api_checkout``), runs the *existing, unmodified* analyzer engine against the
skeleton, and scores with ``scorer.score_repo`` — producing a portfolio report
without cloning any repository.

This is the engine behind the hosted "paste your GitHub username" report. The
result is honestly labelled API-only: structure / testing / CI / docs / README /
dependency presence are recovered from the API, but deep code-quality,
secret-scanning, and dependency-age signals require the full local scan (the OSS
CLI). Security scoring runs offline by default because GitHub Advanced Security
endpoints are not readable on other users' repositories.
"""

from __future__ import annotations

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import requests

from src.analyzers import run_all_analyzers
from src.api_checkout import materialize_api_checkout
from src.graphql_client import bulk_fetch_repos
from src.models import RepoAudit, RepoMetadata
from src.scorer import score_repo

if TYPE_CHECKING:
    from src.github_client import GitHubClient

logger = logging.getLogger(__name__)

# The hosted scan is authenticated (high rate limit) and uses no shared response
# cache, so per-repo work (materialize + analyze + score) runs concurrently. Each
# repo writes to its own temp subdir and the requests.Session is thread-safe.
DEFAULT_SCAN_WORKERS = 8

API_ONLY_MODE = "api_only"
API_ONLY_FIDELITY_NOTE = (
    "API-only scan: scored from GitHub API metadata and repository structure "
    "without cloning. Deep code-quality, secret-scanning, and dependency-age "
    "signals require the full local scan (OSS CLI)."
)


class _InteractiveClient:
    """Wrap a GitHubClient to skip GitHub's async-computed ``stats/*`` endpoints.

    ``stats/contributors``, ``stats/commit_activity`` and ``stats/participation``
    return ``202 Accepted`` while GitHub computes them, and the client retries
    with multi-second backoff — fine for a batch CLI run, far too slow for an
    interactive hosted report (it dominated a 5-repo live scan at ~100s). The
    analyzers already treat these as "unavailable" (empty list / dict), so scores
    degrade gracefully rather than break. Every other method delegates unchanged.
    """

    def __init__(self, inner: GitHubClient) -> None:
        self._inner = inner

    def get_contributor_stats(self, *args, **kwargs) -> list:
        return []

    def get_commit_activity(self, *args, **kwargs) -> list:
        return []

    def get_participation_stats(self, *args, **kwargs) -> dict:
        return {}

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def _portfolio_lang_freq(repos: list[RepoMetadata]) -> dict[str, float]:
    """Fraction of repos using each primary language (for novelty discounting)."""
    counts: dict[str, int] = {}
    for repo in repos:
        if repo.language:
            counts[repo.language] = counts.get(repo.language, 0) + 1
    total = sum(counts.values())
    if not total:
        return {}
    return {lang: n / total for lang, n in counts.items()}


def score_repos_api_only(
    repos: list[RepoMetadata],
    client: GitHubClient,
    *,
    portfolio_lang_freq: dict[str, float] | None = None,
    security_offline: bool = True,
    fast: bool = True,
    max_workers: int = DEFAULT_SCAN_WORKERS,
) -> list[RepoAudit]:
    """Score a list of repos from the API alone, returning one audit per repo.

    ``fast`` (default) skips GitHub's slow async ``stats/*`` endpoints so the
    scan stays interactive; pass ``fast=False`` for a thorough scan that includes
    contributor/commit-activity stats. Per-repo work runs concurrently across
    ``max_workers`` threads (see ``DEFAULT_SCAN_WORKERS``). A repo that fails to
    materialize or score is skipped with a warning so one bad repo never aborts
    the portfolio scan; result order follows the input order.
    """
    if not repos:
        return []
    if portfolio_lang_freq is None:
        portfolio_lang_freq = _portfolio_lang_freq(repos)

    scan_client = cast("GitHubClient", _InteractiveClient(client)) if fast else client

    def _score_one(repo: RepoMetadata, root: Path) -> RepoAudit | None:
        try:
            repo_path = materialize_api_checkout(repo, scan_client, root / repo.name)
            results = run_all_analyzers(repo_path, repo, scan_client)
            return score_repo(
                repo,
                results,
                repo_path=repo_path,
                portfolio_lang_freq=portfolio_lang_freq,
                github_client=scan_client,
                security_offline=security_offline,
            )
        except Exception as exc:  # noqa: BLE001 — one bad repo must not abort the scan
            logger.warning("API-only scoring failed for %s: %s", repo.name, exc)
            return None

    workers = max(1, min(max_workers, len(repos)))
    with tempfile.TemporaryDirectory(prefix="audit-api-") as tmpdir:
        root = Path(tmpdir)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            audits = list(pool.map(lambda repo: _score_one(repo, root), repos))
    return [audit for audit in audits if audit is not None]


@dataclass
class ApiOnlyReport:
    """A clone-free portfolio report, ready for JSON serialization."""

    username: str
    audits: list[RepoAudit]
    mode: str = API_ONLY_MODE
    fidelity_note: str = API_ONLY_FIDELITY_NOTE

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "mode": self.mode,
            "fidelity_note": self.fidelity_note,
            "repo_count": len(self.audits),
            "repos": [audit.to_dict() for audit in self.audits],
        }


def _list_user_repos(username: str, client: GitHubClient) -> list[dict]:
    """List a user's repos, preferring GraphQL when a token is available.

    GraphQL fetches the whole repo list (and per-repo language byte breakdowns)
    in one paginated query, so it's both cheaper on the rate limit and higher
    fidelity than REST. It requires auth, so without a token — or if the query
    fails / returns no user — we fall back to REST ``list_repos``, which also
    yields a clean 404 for an unknown user (GraphQL returns ``user: null``).
    """
    token = getattr(client, "token", None)
    if token:
        try:
            repos = bulk_fetch_repos(username, token, on_progress=lambda *_: None)
        except (requests.RequestException, KeyError, TypeError) as exc:
            logger.warning(
                "GraphQL repo-list failed for %s (%s); falling back to REST",
                username,
                exc,
            )
        else:
            if repos:
                return repos
    return client.list_repos(username)


def _select_repos(repos: list[RepoMetadata], limit: int | None) -> list[RepoMetadata]:
    """Pick the most report-worthy repos when a user has more than ``limit``.

    Ranks original, active work ahead of forks and archives, then by recency and
    stars — so a prolific account's report showcases their best/current repos
    rather than an arbitrary slice, and the scan stays bounded.
    """
    if limit is None or len(repos) <= limit:
        return repos

    def rank(repo: RepoMetadata) -> tuple[bool, bool, float, int]:
        pushed = repo.pushed_at.timestamp() if repo.pushed_at else 0.0
        return (not repo.fork, not repo.archived, pushed, repo.stars)

    return sorted(repos, key=rank, reverse=True)[:limit]


def audit_user_api_only(
    username: str,
    client: GitHubClient,
    *,
    max_repos: int | None = None,
    fast: bool = True,
) -> ApiOnlyReport:
    """List a user's repos and score them clone-free via the GitHub API."""
    raw = _list_user_repos(username, client)

    # GraphQL supplies a `_languages` byte breakdown per repo; REST does not, so
    # `metadata.languages` is populated only on the GraphQL path. Either way the
    # primary `language` field drives scoring; the breakdown sharpens it.
    repos = [
        RepoMetadata.from_api_response(data, data.get("_languages")) for data in raw
    ]
    repos = _select_repos(repos, max_repos)
    audits = score_repos_api_only(repos, client, fast=fast)
    return ApiOnlyReport(username=username, audits=audits)
