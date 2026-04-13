from __future__ import annotations

import requests

from src.github_client import REST_API_VERSION, GitHubClient


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

    def test_security_endpoints_return_counts_when_available(self, monkeypatch):
        client = GitHubClient()

        def _fake_fetch(url, params=None):
            if url.endswith("/secret-scanning/alerts"):
                return [{"number": 1}, {"number": 2}]
            if url.endswith("/code-scanning/alerts"):
                return [{"number": 1}]
            if url.endswith("/dependency-graph/sbom"):
                return {"sbom": {"packages": [{"name": "a"}, {"name": "b"}]}}
            return {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}

        monkeypatch.setattr(client, "_fetch_json", _fake_fetch)

        assert client.get_secret_scanning_alert_count("o", "r")["open_alerts"] == 2
        assert client.get_code_scanning_alert_count("o", "r")["open_alerts"] == 1
        assert client.get_sbom_exportability("o", "r")["package_count"] == 2
        assert client.get_repo_security_and_analysis("o", "r")["available"] is True

    def test_security_endpoints_fail_soft_on_http_error(self, monkeypatch):
        client = GitHubClient()
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError(response=response)

        monkeypatch.setattr(client, "_fetch_json", lambda *a, **k: (_ for _ in ()).throw(error))

        assert client.get_secret_scanning_alert_count("o", "r")["available"] is False
        assert client.get_code_scanning_alert_count("o", "r")["http_status"] == 404
        assert client.get_sbom_exportability("o", "r")["available"] is False

    def test_get_repo_topics_reads_names_payload(self, monkeypatch):
        client = GitHubClient()
        monkeypatch.setattr(client, "_fetch_json", lambda *a, **k: {"names": ["python", "ghra-showcase"]})
        topics = client.get_repo_topics("o", "r")
        assert topics["available"] is True
        assert topics["topics"] == ["python", "ghra-showcase"]

    def test_update_repo_custom_property_values_skips_missing_definitions(self, monkeypatch):
        client = GitHubClient()
        monkeypatch.setattr(client, "list_org_custom_properties", lambda owner: {"available": True, "properties": []})
        monkeypatch.setattr(client, "get_repo_custom_property_values", lambda owner, repo: {"available": True, "values": {"portfolio_call": "old"}})
        result = client.update_repo_custom_property_values("o", "r", {"portfolio_call": "new"})
        assert result["status"] == "skipped"
        assert result["before"] == {"portfolio_call": "old"}

    def test_get_project_v2_returns_field_schema(self, monkeypatch):
        client = GitHubClient()
        monkeypatch.setattr(
            client,
            "_graphql_query",
            lambda *_a, **_k: {
                "organization": {
                    "projectV2": {
                        "id": "PVT_1",
                        "title": "Ops Board",
                        "url": "https://github.com/orgs/o/projects/7",
                        "fields": {
                            "nodes": [
                                {
                                    "id": "field-1",
                                    "name": "Priority",
                                    "dataType": "SINGLE_SELECT",
                                    "options": [{"id": "opt-1", "name": "high"}],
                                },
                                {
                                    "id": "field-2",
                                    "name": "Repository",
                                    "dataType": "TEXT",
                                },
                            ]
                        },
                    }
                }
            },
        )

        result = client.get_project_v2("o", 7)

        assert result["available"] is True
        assert result["fields"]["Priority"]["options"]["high"] == "opt-1"
        assert result["fields"]["Repository"]["data_type"] == "TEXT"

    def test_find_project_v2_item_by_issue_reads_linked_issue(self, monkeypatch):
        client = GitHubClient()
        monkeypatch.setattr(
            client,
            "_graphql_query",
            lambda *_a, **_k: {
                "node": {
                    "items": {
                        "nodes": [
                            {
                                "id": "PVTI_1",
                                "isArchived": False,
                                "content": {"id": "ISSUE_1", "number": 12, "url": "https://github.com/o/r/issues/12"},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            },
        )

        result = client.find_project_v2_item_by_issue("PVT_1", "ISSUE_1")

        assert result["available"] is True
        assert result["item"]["id"] == "PVTI_1"

    def test_add_and_archive_project_v2_item_return_normalized_payloads(self, monkeypatch):
        client = GitHubClient()
        responses = iter(
            [
                {"addProjectV2ItemById": {"item": {"id": "PVTI_1"}}},
                {"archiveProjectV2Item": {"item": {"id": "PVTI_1", "isArchived": True}}},
            ]
        )
        monkeypatch.setattr(client, "_graphql_query", lambda *_a, **_k: next(responses))

        created = client.add_issue_to_project_v2("PVT_1", "ISSUE_1")
        archived = client.archive_project_v2_item("PVTI_1")

        assert created["ok"] is True
        assert created["item_id"] == "PVTI_1"
        assert archived["status"] == "archived"
