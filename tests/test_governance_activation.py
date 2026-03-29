from __future__ import annotations

from src.governance_activation import (
    apply_governance_actions,
    build_governance_actions,
    build_governance_approval,
)


def _report_data() -> dict:
    return {
        "audits": [
            {
                "metadata": {
                    "name": "RepoA",
                    "full_name": "user/RepoA",
                    "archived": False,
                },
                "security_posture": {
                    "github": {
                        "provider_available": True,
                        "code_scanning_status": "not-configured",
                        "secret_scanning_status": "not-configured",
                        "security_and_analysis": {
                            "code_security": {"status": "disabled"},
                            "secret_scanning": {"status": "disabled"},
                            "secret_scanning_push_protection": {"status": "disabled"},
                        },
                    },
                    "recommendations": [
                        {"key": "enable-codeql-default-setup", "title": "Enable CodeQL default setup", "expected_posture_lift": 0.12},
                        {"key": "add-security-md", "title": "Add SECURITY.md", "expected_posture_lift": 0.08},
                    ],
                },
            }
        ]
    }


def _source_run() -> dict:
    return {
        "run_id": "user:run",
        "campaign_type": "security-review",
        "action_runs": [
            {"repo_id": "user/RepoA"},
        ],
    }


class _FakeClient:
    def get_repo_security_and_analysis(self, owner: str, repo: str) -> dict:
        return {
            "available": True,
            "data": {
                "security_and_analysis": {
                    "code_security": {"status": "disabled"},
                    "secret_scanning": {"status": "disabled"},
                    "secret_scanning_push_protection": {"status": "disabled"},
                }
            },
        }

    def update_repo_security_and_analysis(self, owner: str, repo: str, security_and_analysis: dict) -> dict:
        return {"ok": True, "before": {"security_and_analysis": {}}, "after": {"security_and_analysis": security_and_analysis}}

    def get_code_scanning_default_setup(self, owner: str, repo: str) -> dict:
        return {"available": True, "data": {"state": "not-configured"}}

    def update_code_scanning_default_setup(self, owner: str, repo: str, payload: dict) -> dict:
        return {"ok": True, "before": {"state": "not-configured"}, "after": payload}


def test_build_governance_actions_marks_supported_and_preview_only_items():
    preview = build_governance_actions(_report_data(), _source_run(), scope="all")
    keys = {item["control_key"] for item in preview["actions"]}
    assert "enable-code-security" in keys
    assert "enable-secret-scanning" in keys
    assert "enable-push-protection" in keys
    assert "configure-codeql-default-setup" in keys
    assert "add-security-md" in keys
    preview_only = next(item for item in preview["actions"] if item["control_key"] == "add-security-md")
    assert preview_only["applyable"] is False
    assert preview_only["preview_only"] is True


def test_governance_approval_and_apply_flow():
    preview = build_governance_actions(_report_data(), _source_run(), scope="all")
    approval = build_governance_approval(_source_run(), preview, scope="all")
    results, drift = apply_governance_actions(_FakeClient(), preview, approval, scope="all")
    assert approval["fingerprint"] == preview["fingerprint"]
    assert results["counts"]["applied"] >= 1
    assert isinstance(drift, list)
