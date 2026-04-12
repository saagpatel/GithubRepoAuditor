from __future__ import annotations

import logging
import re
import sys
import time
from collections.abc import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from src.cache import ResponseCache
from src.models import RepoMetadata

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
REST_API_VERSION = "2026-03-10"


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
            "X-GitHub-Api-Version": REST_API_VERSION,
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"
        self._authenticated_user: str | None = None
        self._authenticated_user_loaded = False
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            other=0,
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
            status_forcelist={429, 500, 502, 503, 504},
            backoff_factor=1,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

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

    def _request_method(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: dict | list | None = None,
    ) -> requests.Response:
        """Make a non-GET request with the same rate-limit handling."""
        response = self.session.request(method, url, params=params, json=json_body, timeout=30)
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
        if self._authenticated_user_loaded:
            return self._authenticated_user
        self._authenticated_user_loaded = True
        if not self.token:
            return None
        try:
            response = self._request(f"{API_BASE}/user")
            self._authenticated_user = response.json().get("login")
        except requests.HTTPError:
            self._authenticated_user = None
        return self._authenticated_user

    def _repo_list_cache_scope(self, username: str) -> str:
        """Return the effective visibility scope for a repo list request."""
        if not self.token:
            return "public-anonymous"
        authed_user = self.get_authenticated_user()
        if authed_user and authed_user.lower() == username.lower():
            return "owner-private"
        return "public-authenticated"

    def list_repos(self, username: str) -> list[dict]:
        """Fetch all repos for a user. Uses /user/repos for the authenticated user."""
        # Check cache for the complete repo list
        cache_key = f"{API_BASE}/list_repos/{username}/{self._repo_list_cache_scope(username)}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        repos: list[dict] = []
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

    def _http_error_status(self, exc: requests.HTTPError) -> int | None:
        response = getattr(exc, "response", None)
        return response.status_code if response is not None else None

    def get_repo_security_and_analysis(self, owner: str, repo: str) -> dict:
        """Fetch repo-level security_and_analysis metadata when available."""
        try:
            data = self._fetch_json(f"{API_BASE}/repos/{owner}/{repo}")
            return {
                "available": True,
                "http_status": 200,
                "data": data if isinstance(data, dict) else {},
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to fetch repo security metadata for %s/%s: %s", owner, repo, exc)
            return {
                "available": False,
                "http_status": status,
                "data": {},
            }

    def get_secret_scanning_alert_count(self, owner: str, repo: str) -> dict:
        """Fetch count of open secret scanning alerts when accessible."""
        try:
            data = self._fetch_json(
                f"{API_BASE}/repos/{owner}/{repo}/secret-scanning/alerts",
                {"state": "open", "per_page": "100"},
            )
            alerts = data if isinstance(data, list) else []
            return {
                "available": True,
                "http_status": 200,
                "open_alerts": len(alerts),
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to fetch secret scanning alerts for %s/%s: %s", owner, repo, exc)
            return {
                "available": False,
                "http_status": status,
                "open_alerts": None,
            }

    def get_code_scanning_alert_count(self, owner: str, repo: str) -> dict:
        """Fetch count of open code scanning alerts when accessible."""
        try:
            data = self._fetch_json(
                f"{API_BASE}/repos/{owner}/{repo}/code-scanning/alerts",
                {"state": "open", "per_page": "100"},
            )
            alerts = data if isinstance(data, list) else []
            return {
                "available": True,
                "http_status": 200,
                "open_alerts": len(alerts),
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to fetch code scanning alerts for %s/%s: %s", owner, repo, exc)
            return {
                "available": False,
                "http_status": status,
                "open_alerts": None,
            }

    def get_sbom_exportability(self, owner: str, repo: str) -> dict:
        """Check whether the SBOM export endpoint is available for a repo."""
        try:
            data = self._fetch_json(f"{API_BASE}/repos/{owner}/{repo}/dependency-graph/sbom")
            payload = data if isinstance(data, dict) else {}
            packages = payload.get("sbom", {}).get("packages", [])
            return {
                "available": True,
                "http_status": 200,
                "package_count": len(packages) if isinstance(packages, list) else 0,
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to fetch SBOM exportability for %s/%s: %s", owner, repo, exc)
            return {
                "available": False,
                "http_status": status,
                "package_count": None,
            }

    def get_repo_topics(self, owner: str, repo: str) -> dict:
        """Fetch the current topic set for a repository."""
        try:
            data = self._fetch_json(f"{API_BASE}/repos/{owner}/{repo}/topics")
            return {
                "available": True,
                "topics": list(data.get("names", [])) if isinstance(data, dict) else [],
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to fetch topics for %s/%s: %s", owner, repo, exc)
            return {
                "available": False,
                "http_status": status,
                "topics": [],
            }

    def replace_repo_topics(self, owner: str, repo: str, topics: list[str]) -> dict:
        """Replace repository topics with a caller-managed list."""
        try:
            response = self._request_method(
                "PUT",
                f"{API_BASE}/repos/{owner}/{repo}/topics",
                json_body={"names": topics},
            )
            data = response.json()
            return {
                "ok": True,
                "http_status": response.status_code,
                "topics": list(data.get("names", [])),
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to replace topics for %s/%s: %s", owner, repo, exc)
            return {
                "ok": False,
                "http_status": status,
                "topics": topics,
            }

    def update_repo_metadata(
        self,
        owner: str,
        repo: str,
        *,
        description: str | None = None,
        homepage: str | None = None,
    ) -> dict:
        """Update repository description and/or homepage via PATCH /repos/{owner}/{repo}."""
        body: dict = {}
        if description is not None:
            body["description"] = description
        if homepage is not None:
            body["homepage"] = homepage
        try:
            response = self._request_method(
                "PATCH",
                f"{API_BASE}/repos/{owner}/{repo}",
                json_body=body,
            )
            data = response.json()
            return {
                "ok": True,
                "http_status": response.status_code,
                "description": data.get("description", ""),
                "homepage": data.get("homepage", ""),
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to update metadata for %s/%s: %s", owner, repo, exc)
            return {
                "ok": False,
                "http_status": status,
                "description": description or "",
                "homepage": homepage or "",
            }

    def get_file_sha(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> str | None:
        """Get the SHA of a file in a repo, or None if the file doesn't exist."""
        params: dict = {}
        if ref is not None:
            params["ref"] = ref
        try:
            response = self._request(
                f"{API_BASE}/repos/{owner}/{repo}/contents/{path}",
                params=params,
            )
            data = response.json()
            return data.get("sha")
        except requests.HTTPError as exc:
            if self._http_error_status(exc) == 404:
                return None
            raise

    def update_repo_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content_b64: str,
        message: str,
        *,
        sha: str | None = None,
    ) -> dict:
        """Create or update a file via PUT /repos/{owner}/{repo}/contents/{path}."""
        body: dict = {"message": message, "content": content_b64}
        if sha is not None:
            body["sha"] = sha
        try:
            response = self._request_method(
                "PUT",
                f"{API_BASE}/repos/{owner}/{repo}/contents/{path}",
                json_body=body,
            )
            data = response.json()
            return {
                "ok": True,
                "http_status": response.status_code,
                "sha": data.get("content", {}).get("sha", ""),
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to update file %s in %s/%s: %s", path, owner, repo, exc)
            return {
                "ok": False,
                "http_status": status,
                "sha": "",
            }

    def list_repo_issues(self, owner: str, repo: str, state: str = "open") -> list[dict]:
        """List repository issues for managed issue reconciliation."""
        try:
            return self._paginate(
                f"{API_BASE}/repos/{owner}/{repo}/issues",
                {"state": state, "per_page": "100"},
            )
        except requests.HTTPError as exc:
            logger.warning("Failed to list issues for %s/%s: %s", owner, repo, exc)
            return []

    def create_issue(self, owner: str, repo: str, payload: dict) -> dict:
        """Create a managed tracking issue."""
        try:
            response = self._request_method(
                "POST",
                f"{API_BASE}/repos/{owner}/{repo}/issues",
                json_body=payload,
            )
            data = response.json()
            return {
                "ok": True,
                "number": data.get("number"),
                "html_url": data.get("html_url"),
                "http_status": response.status_code,
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to create issue for %s/%s: %s", owner, repo, exc)
            return {
                "ok": False,
                "http_status": status,
            }

    def update_issue(self, owner: str, repo: str, issue_number: int, payload: dict) -> dict:
        """Update an existing managed issue."""
        try:
            response = self._request_method(
                "PATCH",
                f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_number}",
                json_body=payload,
            )
            data = response.json()
            return {
                "ok": True,
                "number": data.get("number", issue_number),
                "html_url": data.get("html_url"),
                "http_status": response.status_code,
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to update issue %s for %s/%s: %s", issue_number, owner, repo, exc)
            return {
                "ok": False,
                "number": issue_number,
                "http_status": status,
            }

    def get_repo_custom_property_values(self, owner: str, repo: str) -> dict:
        """Get current repository custom property values when available."""
        try:
            data = self._fetch_json(f"{API_BASE}/repos/{owner}/{repo}/properties/values")
            values = {}
            if isinstance(data, list):
                for item in data:
                    values[item.get("property_name", "")] = item.get("value")
            return {
                "available": True,
                "values": values,
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to fetch custom properties for %s/%s: %s", owner, repo, exc)
            return {
                "available": False,
                "http_status": status,
                "values": {},
            }

    def list_org_custom_properties(self, owner: str) -> dict:
        """List organization custom property definitions when accessible."""
        try:
            data = self._fetch_json(f"{API_BASE}/orgs/{owner}/properties/schema")
            return {
                "available": True,
                "properties": data if isinstance(data, list) else [],
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to list custom property schema for %s: %s", owner, exc)
            return {
                "available": False,
                "http_status": status,
                "properties": [],
            }

    def update_repo_custom_property_values(self, owner: str, repo: str, properties: dict[str, str]) -> dict:
        """Set org custom property values only when definitions already exist."""
        schema = self.list_org_custom_properties(owner)
        if not schema.get("available"):
            return {
                "ok": False,
                "status": "unavailable",
                "before": {},
                "after": {},
                "updated": {},
            }

        allowed = {
            item.get("property_name")
            for item in schema.get("properties", [])
            if item.get("property_name")
        }
        to_update = {name: value for name, value in properties.items() if name in allowed}
        before = self.get_repo_custom_property_values(owner, repo)
        if not to_update:
            return {
                "ok": False,
                "status": "skipped",
                "before": before.get("values", {}),
                "after": before.get("values", {}),
                "updated": {},
            }

        payload = {
            "properties": [
                {"property_name": name, "value": value}
                for name, value in to_update.items()
            ]
        }
        try:
            response = self._request_method(
                "PATCH",
                f"{API_BASE}/repos/{owner}/{repo}/properties/values",
                json_body=payload,
            )
            after = self.get_repo_custom_property_values(owner, repo)
            return {
                "ok": True,
                "status": "updated",
                "http_status": response.status_code,
                "before": before.get("values", {}),
                "after": after.get("values", {}),
                "updated": to_update,
            }
        except requests.HTTPError as exc:
            status = self._http_error_status(exc)
            logger.warning("Failed to update custom properties for %s/%s: %s", owner, repo, exc)
            return {
                "ok": False,
                "status": "failed",
                "http_status": status,
                "before": before.get("values", {}),
                "after": before.get("values", {}),
                "updated": to_update,
            }

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
        self,
        username: str,
        on_progress: "Callable[[int, int, str], None] | None" = None,
    ) -> tuple[list[RepoMetadata], list[dict]]:
        """Fetch metadata for all repos, including per-repo language breakdowns.

        Returns (metadata_list, errors_list).
        on_progress(current, total, repo_name) — called per repo.
        """
        raw_repos = self.list_repos(username)
        total = len(raw_repos)
        if not on_progress:
            print(f"Found {total} repos for {username}", file=sys.stderr)

        metadata: list[RepoMetadata] = []
        errors: list[dict] = []

        for i, repo_data in enumerate(raw_repos, 1):
            repo_name = repo_data["name"]
            full_name = repo_data["full_name"]
            if on_progress:
                on_progress(i, total, repo_name)
            else:
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
