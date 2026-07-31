from __future__ import annotations

from dataclasses import dataclass

import pytest

from src import notion_sync


@dataclass
class Response:
    status_code: int
    payload: dict

    def json(self) -> dict:
        return self.payload


def test_existing_event_enumeration_fails_after_partial_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            Response(
                200,
                {
                    "results": [
                        {
                            "properties": {
                                "Event Key": {
                                    "rich_text": [{"text": {"content": "audit::report::one"}}]
                                }
                            }
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "page-2",
                },
            ),
            Response(503, {}),
        ]
    )
    monkeypatch.setattr(notion_sync, "_notion_request", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(notion_sync.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="before completion"):
        notion_sync._query_existing_event_keys("events", "token", "version")
