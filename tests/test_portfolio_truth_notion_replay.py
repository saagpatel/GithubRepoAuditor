from __future__ import annotations

import json
from pathlib import Path

import pytest

from github_repo_auditor.portfolio_truth_reconcile import (
    build_portfolio_truth_snapshot,
    load_prior_notion_context,
)


def test_headless_notion_replay_uses_exact_published_project_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    original = workspace / "one" / "Widget"
    original.mkdir(parents=True)
    (original / "README.md").write_text("# Fixture\n")
    ambiguous = workspace / "two" / "WIDGET"
    ambiguous.mkdir(parents=True)
    (ambiguous / "README.md").write_text("# Fixture\n")

    notion_loader = (
        "github_repo_auditor.portfolio_truth_sources.load_notion_project_context"
    )
    monkeypatch.setattr(
        notion_loader,
        lambda _: {
            "Widget": {"portfolio_call": "Maintain"},
            "widget": {"portfolio_call": "Archive"},
        },
    )
    live = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "absent.yaml",
        include_notion=True,
    ).snapshot
    live_calls = {
        row.identity.project_key: row.advisory.notion_portfolio_call
        for row in live.projects
    }
    assert live_calls == {"one/Widget": "Maintain", "two/WIDGET": ""}

    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps(live.to_dict()))
    (workspace / "moved").mkdir()
    original.rename(workspace / "moved" / "Widget")
    new_spelling = workspace / "new" / "widget"
    new_spelling.mkdir(parents=True)
    (new_spelling / "README.md").write_text("# Fixture\n")
    monkeypatch.setattr(notion_loader, lambda _: {})
    refreshed = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "absent.yaml",
        include_notion=True,
        notion_context_fallback=load_prior_notion_context(prior),
    ).snapshot

    assert {
        row.identity.project_key: row.advisory.notion_portfolio_call
        for row in refreshed.projects
    } == {"moved/Widget": "", "new/widget": "", "two/WIDGET": ""}
