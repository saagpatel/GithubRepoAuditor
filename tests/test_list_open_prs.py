from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.github_client import GitHubClient


class TestListOpenPullRequests:
    def test_returns_all_open_prs_via_pagination(self, monkeypatch):
        client = GitHubClient()
        fake_prs = [
            {"number": 1, "title": "Fix login bug", "state": "open"},
            {"number": 2, "title": "Add dark mode", "state": "open"},
        ]
        monkeypatch.setattr(client, "_paginate", lambda url, params=None: fake_prs)

        result = client.list_open_pull_requests("octocat", "hello-world")

        assert result == fake_prs

    def test_passes_open_state_to_paginate(self, monkeypatch):
        client = GitHubClient()
        captured: list[dict] = []

        def capture_paginate(url, params=None):
            captured.append({"url": url, "params": params})
            return []

        monkeypatch.setattr(client, "_paginate", capture_paginate)

        client.list_open_pull_requests("octocat", "hello-world")

        assert captured[0]["params"] == {"state": "open", "per_page": "100"}
        assert "octocat/hello-world/pulls" in captured[0]["url"]

    def test_returns_empty_list_on_http_error(self, monkeypatch):
        import requests

        client = GitHubClient()

        def raise_http(url, params=None):
            raise requests.HTTPError("403")

        monkeypatch.setattr(client, "_paginate", raise_http)

        result = client.list_open_pull_requests("octocat", "private-repo")

        assert result == []


class TestListOpenPrsCLI:
    def _make_args(self, repo: str, token: str | None = "tok", output_dir: str = "output"):
        args = MagicMock()
        args.list_open_prs = repo
        args.token = token
        args.verbose = False
        return args

    def test_prints_pr_lines_to_stdout(self, capsys):
        from src.cli import _run_list_open_prs_mode

        args = self._make_args("octocat/hello-world")

        with patch("src.cli.GitHubClient") as MockClient:
            instance = MockClient.return_value
            instance.list_open_pull_requests.return_value = [
                {"number": 3, "title": "Refactor auth"},
                {"number": 7, "title": "Update README"},
            ]
            _run_list_open_prs_mode(args)

        out = capsys.readouterr().out
        assert "#3: Refactor auth\n" in out
        assert "#7: Update README\n" in out

    def test_output_order_matches_api_order(self, capsys):
        from src.cli import _run_list_open_prs_mode

        args = self._make_args("owner/repo")

        with patch("src.cli.GitHubClient") as MockClient:
            instance = MockClient.return_value
            instance.list_open_pull_requests.return_value = [
                {"number": 10, "title": "First"},
                {"number": 2, "title": "Second"},
                {"number": 99, "title": "Third"},
            ]
            _run_list_open_prs_mode(args)

        lines = capsys.readouterr().out.splitlines()
        assert lines == ["#10: First", "#2: Second", "#99: Third"]

    def test_empty_repo_prints_nothing(self, capsys):
        from src.cli import _run_list_open_prs_mode

        args = self._make_args("owner/empty")

        with patch("src.cli.GitHubClient") as MockClient:
            instance = MockClient.return_value
            instance.list_open_pull_requests.return_value = []
            _run_list_open_prs_mode(args)

        out = capsys.readouterr().out
        assert out == ""

    def test_passes_token_to_client(self, capsys):
        from src.cli import _run_list_open_prs_mode

        args = self._make_args("owner/repo", token="my-secret-token")

        with patch("src.cli.GitHubClient") as MockClient:
            instance = MockClient.return_value
            instance.list_open_pull_requests.return_value = []
            _run_list_open_prs_mode(args)

        MockClient.assert_called_once_with(token="my-secret-token")

    def test_calls_list_open_pull_requests_with_owner_and_repo(self, capsys):
        from src.cli import _run_list_open_prs_mode

        args = self._make_args("myorg/my-repo")

        with patch("src.cli.GitHubClient") as MockClient:
            instance = MockClient.return_value
            instance.list_open_pull_requests.return_value = []
            _run_list_open_prs_mode(args)

        instance.list_open_pull_requests.assert_called_once_with("myorg", "my-repo")
