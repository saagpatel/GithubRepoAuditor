from __future__ import annotations

import logging
import re
import sys
import time

import requests

from src.models import RepoMetadata

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubClientError(Exception):
    """Raised for non-recoverable GitHub API errors."""


class GitHubClient:
    """Minimal GitHub REST API v3 client with pagination and rate-limit handling."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token
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

    # ── public API ────────────────────────────────────────────────────

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
        if self.token:
            authed_user = self.get_authenticated_user()
            if authed_user and authed_user.lower() == username.lower():
                # Authenticated as this user — get private repos too
                return self._paginate(
                    f"{API_BASE}/user/repos",
                    {"per_page": "100", "type": "owner"},
                )

        # Public-only or token belongs to a different user
        return self._paginate(
            f"{API_BASE}/users/{username}/repos",
            {"per_page": "100"},
        )

    def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Fetch language byte counts for a repo."""
        try:
            response = self._request(f"{API_BASE}/repos/{owner}/{repo}/languages")
            return response.json()
        except requests.HTTPError as exc:
            logger.warning("Failed to fetch languages for %s/%s: %s", owner, repo, exc)
            return {}

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
