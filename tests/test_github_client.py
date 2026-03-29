from __future__ import annotations

from src.github_client import GitHubClient, REST_API_VERSION


class _MemoryCache:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str | None], object] = {}
        self.get_calls: list[tuple[str, str | None]] = []
        self.put_calls: list[tuple[str, str | None]] = []

    def get(self, url: str, params: dict | None = None):
        key = (url, repr(params) if params is not None else None)
        self.get_calls.append(key)
        return self.data.get(key)

    def put(self, url: str, params: dict | None, value: object) -> None:
        key = (url, repr(params) if params is not None else None)
        self.put_calls.append(key)
        self.data[key] = value


class TestGitHubClientHardening:
    def test_rest_session_sets_explicit_api_version(self):
        client = GitHubClient()
        assert client.session.headers["X-GitHub-Api-Version"] == REST_API_VERSION

    def test_repo_list_cache_key_includes_owner_private_scope(self, monkeypatch):
        cache = _MemoryCache()
        client = GitHubClient(token="secret", cache=cache)

        monkeypatch.setattr(client, "get_authenticated_user", lambda: "octocat")
        monkeypatch.setattr(
            client,
            "_paginate",
            lambda url, params=None: [{"name": "private-repo", "private": True}],
        )

        repos = client.list_repos("octocat")

        assert repos == [{"name": "private-repo", "private": True}]
        assert any("/list_repos/octocat/owner-private" in call[0] for call in cache.get_calls)
        assert any("/list_repos/octocat/owner-private" in call[0] for call in cache.put_calls)

    def test_public_and_private_repo_list_cache_entries_do_not_collide(self, monkeypatch):
        cache = _MemoryCache()

        owner_client = GitHubClient(token="secret", cache=cache)
        monkeypatch.setattr(owner_client, "get_authenticated_user", lambda: "octocat")
        monkeypatch.setattr(
            owner_client,
            "_paginate",
            lambda url, params=None: [{"name": "private-repo", "private": True}],
        )
        owner_result = owner_client.list_repos("octocat")

        anonymous_client = GitHubClient(token=None, cache=cache)
        monkeypatch.setattr(
            anonymous_client,
            "_paginate",
            lambda url, params=None: [{"name": "public-repo", "private": False}],
        )
        anon_result = anonymous_client.list_repos("octocat")

        assert owner_result == [{"name": "private-repo", "private": True}]
        assert anon_result == [{"name": "public-repo", "private": False}]
        assert any("/list_repos/octocat/owner-private" in call[0] for call in cache.put_calls)
        assert any("/list_repos/octocat/public-anonymous" in call[0] for call in cache.put_calls)
