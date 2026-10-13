from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from github_repo_auditor.notion_client import NotionOutcomeUnknownError, notion_request


def test_read_only_post_query_retries_server_error() -> None:
    failed = MagicMock(status_code=503)
    succeeded = MagicMock(status_code=200)
    with (
        patch(
            "github_repo_auditor.notion_client.requests.request",
            side_effect=[failed, succeeded],
        ) as request,
        patch("github_repo_auditor.notion_client.time.sleep"),
    ):
        result = notion_request("POST", "/databases/db/query", "token")

    assert result is succeeded
    assert request.call_count == 2


def test_ambiguous_create_server_error_is_not_retried() -> None:
    failed = MagicMock(status_code=503)
    with patch(
        "github_repo_auditor.notion_client.requests.request", return_value=failed
    ) as request:
        with pytest.raises(NotionOutcomeUnknownError, match="outcome unknown"):
            notion_request("POST", "/pages", "token", body={"properties": {}})

    assert request.call_count == 1


def test_ambiguous_append_transport_error_is_not_retried() -> None:
    with patch(
        "github_repo_auditor.notion_client.requests.request",
        side_effect=requests.Timeout("response lost"),
    ) as request:
        with pytest.raises(NotionOutcomeUnknownError, match="outcome unknown"):
            notion_request(
                "PATCH", "/blocks/page/children", "token", body={"children": []}
            )

    assert request.call_count == 1


def test_write_rate_limit_response_is_returned_without_retry() -> None:
    limited = MagicMock(status_code=429)
    with patch(
        "github_repo_auditor.notion_client.requests.request", return_value=limited
    ) as request:
        result = notion_request("POST", "/pages", "token", body={"properties": {}})

    assert result is limited
    assert request.call_count == 1
