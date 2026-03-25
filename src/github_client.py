from __future__ import annotations

import logging
import re
import sys
import time

import requests

from src.cache import ResponseCache
from src.models import RepoMetadata

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubClientError(Exception):
    """Raised for non-recoverable GitHub API errors."""


class GitHubClient:
    """Minimal GitHub REST API v3 client with pagination and rate-limit handling."""

    def __init__(
        self,
        token: str | None = None,
        cache: ResponseCache | None = None,
    ) -> None:
        self.token = token
        self.cache = cache
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "github-repo-auditor/0.1",
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"

    # ── internal helpers ──────────────────────────────────────────────

    def _check_rate_limit(self, response: requests.Response) -> None:
        """Sleep if rate limit is nearly exhausted."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is None:
            return
        remaining_int = int(remaining)
        if remaining_int < 10:
            reset_epoch = int(response.headers.get("X-RateLimit-Reset", "0"))
            sleep_seconds = max(reset_epoch - int(time.time()), 1)
            logger.warning(
                "Rate limit low (%d remaining). Sleeping %ds until reset.",
                remaining_int,
                sleep_seconds,
            )
            print(
                f"  ⏳ Rate limit low ({remaining_int} remaining). "
                f"Sleeping {sleep_seconds}s...",
                file=sys.stderr,
            )
            time.sleep(sleep_seconds)

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        """Make an authenticated request with rate-limit awareness."""
        response = self.session.get(url, params=params, timeout=30)
        self._check_rate_limit(response)
        response.raise_for_status()
        return response

    def _paginate(self, url: str, params: dict | None = None) -> list[dict]:
        """Follow pagination via Link headers, collecting all results."""
        results: list[dict] = []
        params = dict(params or {})

        while url:
            response = self._request(url, params)
            results.extend(response.json())

            # After the first request, params are baked into the next URL
            params = {}

            # Parse next link — prefer response.links, fall back to regex
            next_link = response.links.get("next", {}).get("url")
            if not next_link:
                link_header = response.headers.get("Link", "")
                match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
                next_link = match.group(1) if match else None
            url = next_link  # type: ignore[assignment]

        return results

    def _request_with_202_retry(
        self,
        url: str,
        params: dict | None = None,
        max_retries: int = 3,
    ) -> requests.Response:
        """Request with retry for 202 (stats computing) responses."""
        backoff = 2
        for attempt in range(max_retries + 1):
            response = self.session.get(url, params=params, timeout=30)
            self._check_rate_limit(response)

            if response.status_code == 202 and attempt < max_retries:
                sleep_time = backoff * (2 ** attempt)
                logger.info("Stats computing (202), retrying in %ds...", sleep_time)
                time.sleep(sleep_time)
                continue

            response.raise_for_status()
            return response

        return response  # type: ignore[possibly-undefined]

    def _fetch_json(self, url: str, params: dict | None = None) -> object:
        """Fetch JSON from a URL, checking cache first.

        Used for leaf endpoints (languages, commits). NOT for paginated list endpoints.
        """
        if self.cache:
            cached = self.cache.get(url, params)
            if cached is not None:
                return cached

        response = self._request(url, params)
        data = response.json()

        if self.cache:
            self.cache.put(url, params, data)

        return data

    def _fetch_json_with_202_retry(self, url: str, params: dict | None = None) -> object:
        """Fetch JSON with 202 retry, checking cache first."""
        if self.cache:
            cached = self.cache.get(url, params)
            if cached is not None:
                return cached

        response = self._request_with_202_retry(url, params)
        data = response.json()

        if self.cache:
            self.cache.put(url, params, data)

        return data

    # ── public API ────────────────────────────────────────────────────

    def get_community_profile(self, owner: str, repo: str) -> dict:
        """Fetch community health profile (README, LICENSE, CODE_OF_CONDUCT, etc).

        Single API call returns presence of all health files.
        """
        try:
            return self._fetch_json(f"{API_BASE}/repos/{owner}/{repo}/community/profile")
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch community profile for %s/%s: %s", owner, repo, exc)
            return {}

    def get_participation_stats(self, owner: str, repo: str) -> dict:
        """Fetch weekly commit counts split by owner vs all contributors.

        Returns {all: [52 weeks], owner: [52 weeks]}.
        """
        try:
            return self._fetch_json_with_202_retry(
                f"{API_BASE}/repos/{owner}/{repo}/stats/participation"
            )
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch participation for %s/%s: %s", owner, repo, exc)
            return {}

    def get_authenticated_user(self) -> str | None:
        """Return the login of the authenticated user, or None."""
        if not self.token:
            return None
        try:
            response = self._request(f"{API_BASE}/user")
            return response.json().get("login")
        except requests.HTTPError:
            return None

    def list_repos(self, username: str) -> list[dict]:
        """Fetch all repos for a user. Uses /user/repos for the authenticated user."""
        # Check cache for the complete repo list
        cache_key = f"{API_BASE}/list_repos/{username}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        repos: list[dict] = []
        if self.token:
            authed_user = self.get_authenticated_user()
            if authed_user and authed_user.lower() == username.lower():
                # Authenticated as this user — get private repos too
                repos = self._paginate(
                    f"{API_BASE}/user/repos",
                    {"per_page": "100", "type": "owner"},
                )

        if not repos:
            # Public-only or token belongs to a different user
            repos = self._paginate(
                f"{API_BASE}/users/{username}/repos",
                {"per_page": "100"},
            )

        if self.cache:
            self.cache.put(cache_key, None, repos)
        return repos

    def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Fetch language byte counts for a repo."""
        try:
            return self._fetch_json(f"{API_BASE}/repos/{owner}/{repo}/languages")
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch languages for %s/%s: %s", owner, repo, exc)
            return {}

    def get_releases(self, owner: str, repo: str, count: int = 20) -> list[dict]:
        """Fetch releases for a repo."""
        try:
            data = self._fetch_json(
                f"{API_BASE}/repos/{owner}/{repo}/releases",
                {"per_page": str(count)},
            )
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch releases for %s/%s: %s", owner, repo, exc)
            return []

    def get_pull_requests(
        self, owner: str, repo: str, state: str = "all", count: int = 50
    ) -> list[dict]:
        """Fetch pull requests for a repo."""
        try:
            data = self._fetch_json(
                f"{API_BASE}/repos/{owner}/{repo}/pulls",
                {"state": state, "per_page": str(count)},
            )
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch PRs for %s/%s: %s", owner, repo, exc)
            return []

    def get_recent_commits(
        self, owner: str, repo: str, count: int = 10
    ) -> list[dict]:
        """Fetch the most recent commits for a repo."""
        try:
            data = self._fetch_json(
                f"{API_BASE}/repos/{owner}/{repo}/commits",
                {"per_page": str(count)},
            )
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch commits for %s/%s: %s", owner, repo, exc)
            return []

    def get_commit_activity(self, owner: str, repo: str) -> list[dict]:
        """Fetch weekly commit counts for the last year (52 weeks).

        Returns list of {total, week, days} objects.
        Stats endpoints return 202 on first call — retries with backoff.
        """
        try:
            data = self._fetch_json_with_202_retry(
                f"{API_BASE}/repos/{owner}/{repo}/stats/commit_activity"
            )
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch commit activity for %s/%s: %s", owner, repo, exc)
            return []

    def get_contributor_stats(self, owner: str, repo: str) -> list[dict]:
        """Fetch per-contributor commit counts.

        Stats endpoints return 202 on first call — retries with backoff.
        """
        try:
            data = self._fetch_json_with_202_retry(
                f"{API_BASE}/repos/{owner}/{repo}/stats/contributors"
            )
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch contributor stats for %s/%s: %s", owner, repo, exc)
            return []

    def get_repo_metadata(
        self, username: str
    ) -> tuple[list[RepoMetadata], list[dict]]:
        """Fetch metadata for all repos, including per-repo language breakdowns.

        Returns (metadata_list, errors_list).
        """
        raw_repos = self.list_repos(username)
        total = len(raw_repos)
        print(f"Found {total} repos for {username}", file=sys.stderr)

        metadata: list[RepoMetadata] = []
        errors: list[dict] = []

        for i, repo_data in enumerate(raw_repos, 1):
            repo_name = repo_data["name"]
            full_name = repo_data["full_name"]
            print(
                f"  [{i}/{total}] Fetching {full_name}...",
                file=sys.stderr,
            )

            try:
                owner = repo_data["owner"]["login"]
                languages = self.get_languages(owner, repo_name)
                meta = RepoMetadata.from_api_response(repo_data, languages=languages)
                metadata.append(meta)
            except Exception as exc:
                logger.warning("Error processing %s: %s", full_name, exc)
                errors.append({"repo": full_name, "error": str(exc)})

        return metadata, errors
