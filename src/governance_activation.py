from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.models import AuditReport
from src.warehouse import (
    load_audit_report_path,
    load_campaign_run,
    load_governance_approval,
    load_governance_history,
)

SUPPORTED_CONTROL_KEYS = {
    "enable-code-security",
    "enable-secret-scanning",
    "enable-push-protection",
    "configure-codeql-default-setup",
}

SCOPE_TO_KEYS = {
    "all": SUPPORTED_CONTROL_KEYS,
    "codeql": {"configure-codeql-default-setup"},
    "secret-scanning": {"enable-secret-scanning"},
    "push-protection": {"enable-push-protection"},
    "code-security": {"enable-code-security"},
}


def _action_id(repo_full_name: str, control_key: str) -> str:
    digest = hashlib.sha1(f"{repo_full_name}|{control_key}".encode("utf-8")).hexdigest()[:12]
    return f"governance-{digest}"


def _approval_fingerprint(actions: list[dict]) -> str:
    material = [
        {
            "action_id": action["action_id"],
            "control_key": action["control_key"],
            "repo_full_name": action["repo_full_name"],
            "applyable": action["applyable"],
            "prerequisites": action["prerequisites"],
        }
        for action in sorted(actions, key=lambda item: item["action_id"])
    ]
    return hashlib.sha1(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def _repo_filter_from_campaign_run(source_run: dict) -> set[str]:
    return {
        row.get("repo_id", "")
        for row in source_run.get("action_runs", [])
        if row.get("repo_id")
    }


def _find_repo_audit(report_data: dict, repo_full_name: str) -> dict | None:
    for audit in report_data.get("audits", []):
        if audit.get("metadata", {}).get("full_name") == repo_full_name:
            return audit
    return None


def _status_from_analysis(analysis: dict, key: str) -> str | None:
    value = analysis.get(key, {})
    if isinstance(value, dict):
        return value.get("status")
    return None


def build_governance_actions(report_data: dict, source_run: dict, *, scope: str = "all") -> dict:
    repo_filter = _repo_filter_from_campaign_run(source_run)
    eligible_keys = SCOPE_TO_KEYS.get(scope, SUPPORTED_CONTROL_KEYS)
    actions: list[dict] = []

    for repo_full_name in sorted(repo_filter):
        audit = _find_repo_audit(report_data, repo_full_name)
        if audit is None:
            continue
        metadata = audit.get("metadata", {})
        posture = audit.get("security_posture", {})
        github = posture.get("github", {})
        analysis = github.get("security_and_analysis", {})
        provider_available = github.get("provider_available", False)
        if not provider_available:
            continue

        code_security_status = _status_from_analysis(analysis, "code_security")
        secret_scanning_status = github.get("secret_scanning_status")
        push_protection_status = (
            _status_from_analysis(analysis, "secret_scanning_push_protection")
            or _status_from_analysis(analysis, "secret_scanning_non_provider_patterns_push_protection")
        )
        codeql_status = github.get("code_scanning_status")

        derived = [
            {
                "control_key": "enable-code-security",
                "title": "Enable GitHub Code Security",
                "why": "Repository-level code security is not enabled where GitHub exposes the control.",
                "expected_posture_lift": 0.06,
                "prerequisites": [],
                "applyable": code_security_status not in {"enabled"},
                "preview_only": False,
                "required_permission_level": "admin",
            },
            {
                "control_key": "enable-secret-scanning",
                "title": "Enable secret scanning",
                "why": "Secret scanning is available but not enabled on this repository.",
                "expected_posture_lift": 0.10,
                "prerequisites": [],
                "applyable": secret_scanning_status not in {"enabled", "alerts-open", "unavailable"},
                "preview_only": False,
                "required_permission_level": "admin",
            },
            {
                "control_key": "enable-push-protection",
                "title": "Enable push protection",
                "why": "Push protection is not enabled for secret scanning.",
                "expected_posture_lift": 0.08,
                "prerequisites": ["enable-secret-scanning"] if secret_scanning_status not in {"enabled", "alerts-open"} else [],
                "applyable": push_protection_status not in {"enabled", None},
                "preview_only": False,
                "required_permission_level": "admin",
            },
            {
                "control_key": "configure-codeql-default-setup",
                "title": "Configure CodeQL default setup",
                "why": "Code scanning default setup is not configured.",
                "expected_posture_lift": 0.12,
                "prerequisites": ["enable-code-security"] if code_security_status not in {"enabled"} else [],
                "applyable": codeql_status == "not-configured",
                "preview_only": False,
                "required_permission_level": "admin",
            },
        ]

        for item in derived:
            if item["control_key"] not in eligible_keys:
                continue
            item = {
                **item,
                "action_id": _action_id(repo_full_name, item["control_key"]),
                "repo_full_name": repo_full_name,
                "repo": metadata.get("name", repo_full_name),
                "archived": bool(metadata.get("archived", False)),
                "applyable": bool(item["applyable"]) and not metadata.get("archived", False),
                "rollback_feasible": item["control_key"] in {"enable-code-security", "enable-secret-scanning", "enable-push-protection", "configure-codeql-default-setup"},
                "source": "github",
                "status": "preview",
            }
            if metadata.get("archived", False):
                item["preview_only"] = True
                item["applyable"] = False
                item["skip_reason"] = "archived-repo"
            actions.append(item)

        for item in posture.get("recommendations", []):
            key = item.get("key")
            if key in SUPPORTED_CONTROL_KEYS or key == "enable-codeql-default-setup":
                continue
            actions.append(
                {
                    "action_id": _action_id(repo_full_name, key or item.get("title", "preview-only")),
                    "repo_full_name": repo_full_name,
                    "repo": metadata.get("name", repo_full_name),
                    "control_key": key,
                    "title": item.get("title", "Governance recommendation"),
                    "why": item.get("why", ""),
                    "expected_posture_lift": item.get("expected_posture_lift", 0.0),
                    "prerequisites": [],
                    "required_permission_level": "repo-content",
                    "applyable": False,
                    "preview_only": True,
                    "rollback_feasible": False,
                    "source": item.get("source", "merged"),
                    "status": "preview",
                    "skip_reason": "preview-only-in-this-slice",
                    "archived": bool(metadata.get("archived", False)),
                }
            )

    actions.sort(key=lambda item: (not item["applyable"], -item.get("expected_posture_lift", 0.0), item["repo_full_name"], item["control_key"]))
    return {
        "source_run_id": source_run.get("run_id"),
        "campaign_type": source_run.get("campaign_type"),
        "scope": scope,
        "action_count": len(actions),
        "applyable_count": sum(1 for item in actions if item["applyable"]),
        "actions": actions,
        "fingerprint": _approval_fingerprint(actions),
    }


def build_governance_approval(source_run: dict, governance_preview: dict, *, scope: str) -> dict:
    return {
        "source_run_id": source_run.get("run_id"),
        "campaign_type": source_run.get("campaign_type"),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "fingerprint": governance_preview.get("fingerprint"),
        "action_count": governance_preview.get("action_count", 0),
        "applyable_count": governance_preview.get("applyable_count", 0),
        "status": "approved",
    }


def _make_result(action: dict, *, target: str, status: str, before: dict | None = None, after: dict | None = None, reason: str | None = None, drift_type: str | None = None) -> dict:
    return {
        "action_id": action["action_id"],
        "repo_full_name": action["repo_full_name"],
        "repo": action["repo"],
        "control_key": action["control_key"],
        "target": target,
        "status": status,
        "before": before or {},
        "after": after or {},
        "reason": reason,
        "drift_type": drift_type,
        "rollback_available": action.get("rollback_feasible", False) and status in {"updated", "applied"},
    }


def apply_governance_actions(client, governance_preview: dict, approval: dict, *, scope: str) -> tuple[dict, list[dict]]:
    allowed_keys = SCOPE_TO_KEYS.get(scope, SUPPORTED_CONTROL_KEYS)
    results: list[dict] = []
    drift: list[dict] = []
    completed_keys_by_repo: dict[str, set[str]] = {}

    for action in governance_preview.get("actions", []):
        if action["control_key"] not in allowed_keys:
            continue
        if not action.get("applyable"):
            results.append(_make_result(action, target="governance", status="skipped", reason=action.get("skip_reason", "not-applyable")))
            continue

        repo_full_name = action["repo_full_name"]
        owner, repo = repo_full_name.split("/", 1)
        completed = completed_keys_by_repo.setdefault(repo_full_name, set())
        missing_prereqs = [item for item in action.get("prerequisites", []) if item not in completed]
        if missing_prereqs:
            results.append(_make_result(action, target="governance", status="skipped", reason=f"missing-prerequisites:{','.join(missing_prereqs)}"))
            continue

        repo_security = client.get_repo_security_and_analysis(owner, repo)
        analysis = (repo_security.get("data", {}) or {}).get("security_and_analysis", {}) if repo_security.get("available") else {}
        default_setup = client.get_code_scanning_default_setup(owner, repo)

        if action["control_key"] == "enable-code-security":
            current = (analysis.get("code_security") or {}).get("status")
            if current == "enabled":
                drift.append({"repo_full_name": repo_full_name, "target": "governance-code-security", "drift_type": "already-enabled", "severity": "low"})
                results.append(_make_result(action, target="governance-code-security", status="drifted", before=repo_security.get("data", {}), after=repo_security.get("data", {}), drift_type="already-enabled"))
                completed.add(action["control_key"])
                continue
            update = client.update_repo_security_and_analysis(owner, repo, {"code_security": {"status": "enabled"}})
            status = "applied" if update.get("ok") else ("skipped" if update.get("http_status") in {403, 404, 409, 422} else "failed")
            results.append(_make_result(action, target="governance-code-security", status=status, before=update.get("before", {}), after=update.get("after", {}), reason=None if update.get("ok") else str(update.get("http_status"))))
        elif action["control_key"] == "enable-secret-scanning":
            current = (analysis.get("secret_scanning") or {}).get("status")
            if current == "enabled":
                drift.append({"repo_full_name": repo_full_name, "target": "governance-secret-scanning", "drift_type": "already-enabled", "severity": "low"})
                results.append(_make_result(action, target="governance-secret-scanning", status="drifted", before=repo_security.get("data", {}), after=repo_security.get("data", {}), drift_type="already-enabled"))
                completed.add(action["control_key"])
                continue
            update = client.update_repo_security_and_analysis(owner, repo, {"secret_scanning": {"status": "enabled"}})
            status = "applied" if update.get("ok") else ("skipped" if update.get("http_status") in {403, 404, 409, 422} else "failed")
            results.append(_make_result(action, target="governance-secret-scanning", status=status, before=update.get("before", {}), after=update.get("after", {}), reason=None if update.get("ok") else str(update.get("http_status"))))
        elif action["control_key"] == "enable-push-protection":
            current = (analysis.get("secret_scanning_push_protection") or {}).get("status") or (analysis.get("secret_scanning_non_provider_patterns_push_protection") or {}).get("status")
            secret_current = (analysis.get("secret_scanning") or {}).get("status")
            if secret_current != "enabled" and "enable-secret-scanning" not in completed:
                results.append(_make_result(action, target="governance-push-protection", status="skipped", reason="secret-scanning-not-enabled"))
                continue
            if current == "enabled":
                drift.append({"repo_full_name": repo_full_name, "target": "governance-push-protection", "drift_type": "already-enabled", "severity": "low"})
                results.append(_make_result(action, target="governance-push-protection", status="drifted", before=repo_security.get("data", {}), after=repo_security.get("data", {}), drift_type="already-enabled"))
                completed.add(action["control_key"])
                continue
            update = client.update_repo_security_and_analysis(owner, repo, {"secret_scanning_push_protection": {"status": "enabled"}})
            status = "applied" if update.get("ok") else ("skipped" if update.get("http_status") in {403, 404, 409, 422} else "failed")
            results.append(_make_result(action, target="governance-push-protection", status=status, before=update.get("before", {}), after=update.get("after", {}), reason=None if update.get("ok") else str(update.get("http_status"))))
        else:
            current = default_setup.get("data", {})
            if current.get("state") == "configured":
                drift.append({"repo_full_name": repo_full_name, "target": "governance-codeql", "drift_type": "already-configured", "severity": "low"})
                results.append(_make_result(action, target="governance-codeql", status="drifted", before=current, after=current, drift_type="already-configured"))
                completed.add(action["control_key"])
                continue
            if action.get("prerequisites") and any(prereq not in completed for prereq in action["prerequisites"]):
                results.append(_make_result(action, target="governance-codeql", status="skipped", reason="missing-prerequisites"))
                continue
            update = client.update_code_scanning_default_setup(owner, repo, {"state": "configured", "query_suite": "default"})
            status = "applied" if update.get("ok") else ("skipped" if update.get("http_status") in {403, 404, 409, 422} else "failed")
            results.append(_make_result(action, target="governance-codeql", status=status, before=update.get("before", {}), after=update.get("after", {}), reason=None if update.get("ok") else str(update.get("http_status"))))

        if results[-1]["status"] in {"applied", "drifted"}:
            completed.add(action["control_key"])

    summary = {
        "source_run_id": approval.get("source_run_id"),
        "scope": scope,
        "mode": "apply",
        "counts": {
            "applied": sum(1 for item in results if item["status"] == "applied"),
            "skipped": sum(1 for item in results if item["status"] == "skipped"),
            "failed": sum(1 for item in results if item["status"] == "failed"),
            "drifted": sum(1 for item in results if item["status"] == "drifted"),
        },
        "results": results,
        "fingerprint": governance_preview.get("fingerprint"),
    }
    return summary, drift


def load_report_data_for_run(output_dir: Path, run_id: str) -> dict | None:
    report_path = load_audit_report_path(output_dir, run_id)
    if not report_path or not report_path.is_file():
        return None
    return json.loads(report_path.read_text())


def populate_report_with_governance_context(
    report: AuditReport,
    *,
    output_dir: Path,
    source_run_id: str | None,
) -> None:
    if not source_run_id:
        return
    report.governance_history = load_governance_history(output_dir, source_run_id=source_run_id, limit=10)
    approval = load_governance_approval(output_dir, source_run_id)
    if approval:
        report.governance_approval = approval
