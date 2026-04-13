from __future__ import annotations

from pathlib import Path

from src.github_projects import (
    build_project_field_values,
    build_project_preview_summary,
    load_github_projects_config,
)


def test_load_github_projects_config_handles_missing_file(tmp_path):
    result = load_github_projects_config(tmp_path / "missing.yaml")

    assert result["exists"] is False
    assert result["errors"] == []


def test_load_github_projects_config_validates_supported_keys(tmp_path):
    path = tmp_path / "github-projects.yaml"
    path.write_text(
        """
owner: octo-org
project_number: 7
fields:
  repo: Repository
  mystery: Unknown
"""
    )

    result = load_github_projects_config(path)

    assert result["exists"] is True
    assert any("unsupported key" in message for message in result["errors"])


def test_build_project_field_values_uses_operator_and_catalog_context():
    action = {
        "repo_full_name": "user/repo-a",
        "portfolio_catalog": {"team": "Platform"},
        "priority": "high",
    }
    operator_item = {
        "lane": "urgent",
        "confidence_label": "high",
        "operator_focus": "Act Now",
        "follow_through_status": "In Progress",
        "follow_through_checkpoint_status": "Overdue",
        "follow_through_reacquisition_revalidation_recovery_status": "under-revalidation",
    }

    result = build_project_field_values(
        [action],
        {"label": "Security Review"},
        operator_item=operator_item,
    )

    assert result["campaign"] == "Security Review"
    assert result["owner"] == "Platform"
    assert result["lane"] == "urgent"
    assert result["confidence"] == "high"


def test_build_project_preview_summary_reports_configured_items():
    config = {
        "exists": True,
        "errors": [],
        "warnings": [],
        "owner": "octo-org",
        "project_number": 7,
        "fields": {"repo": "Repository", "priority": "Priority"},
    }
    grouped_actions = {
        "user/repo-a": [
            {
                "repo": "repo-a",
                "repo_full_name": "user/repo-a",
                "priority": "high",
                "campaign_type": "security-review",
                "managed_issue_title": "[Repo Auditor] Security Review",
                "portfolio_catalog": {},
            }
        ]
    }

    result = build_project_preview_summary(config, {"label": "Security Review"}, grouped_actions)

    assert result["status"] == "configured"
    assert result["item_count"] == 1
    assert result["repos"][0]["fields"]["Repository"] == "user/repo-a"
