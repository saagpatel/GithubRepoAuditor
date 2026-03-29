from __future__ import annotations

from typing import TYPE_CHECKING

import requests

from src.models import AnalyzerResult, RepoAudit, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

SCORECARD_API_BASE = "https://api.securityscorecards.dev/projects/"
SCORECARD_CHECKS = {
    "Code-Review",
    "CI-Tests",
    "Dependency-Update-Tool",
    "Pinned-Dependencies",
    "Dangerous-Workflow",
    "Security-Policy",
    "Branch-Protection",
}


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _label_for_score(score: float) -> str:
    if score >= 0.85:
        return "healthy"
    if score >= 0.65:
        return "watch"
    if score >= 0.40:
        return "at-risk"
    return "critical"


def summarize_local_security_posture(results: list[AnalyzerResult]) -> dict:
    security_result = next((result for result in results if result.dimension == "security"), None)
    if not security_result:
        return {
            "available": False,
            "score": 0.5,
            "secrets_found": 0,
            "dangerous_files": [],
            "has_security_md": False,
            "has_dependabot": False,
            "evidence": [],
        }

    details = security_result.details
    return {
        "available": True,
        "score": round(security_result.score, 3),
        "secrets_found": details.get("secrets_found", 0),
        "dangerous_files": details.get("dangerous_files", []),
        "has_security_md": details.get("has_security_md", False),
        "has_dependabot": details.get("has_dependabot", False),
        "evidence": security_result.findings[:5],
    }


def _scorecard_repo_path(metadata: RepoMetadata) -> str:
    return f"github.com/{metadata.full_name}"


def load_scorecard_security(metadata: RepoMetadata) -> dict:
    if metadata.private:
        return {
            "available": False,
            "enabled": False,
            "score": None,
            "checks": {},
            "reason": "private-repo",
            "repo": _scorecard_repo_path(metadata),
        }

    url = f"{SCORECARD_API_BASE}{_scorecard_repo_path(metadata)}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return {
            "available": False,
            "enabled": True,
            "score": None,
            "checks": {},
            "reason": str(exc),
            "repo": _scorecard_repo_path(metadata),
        }

    checks = {
        check["name"]: {
            "score": check.get("score"),
            "reason": check.get("reason", ""),
            "documentation_url": (check.get("documentation") or {}).get("url", ""),
        }
        for check in payload.get("checks", [])
        if check.get("name") in SCORECARD_CHECKS
    }
    return {
        "available": True,
        "enabled": True,
        "score": payload.get("score"),
        "checks": checks,
        "reason": "",
        "repo": _scorecard_repo_path(metadata),
    }


def _normalize_security_and_analysis(data: dict | None) -> dict:
    analysis = (data or {}).get("security_and_analysis", {}) if isinstance(data, dict) else {}
    return analysis if isinstance(analysis, dict) else {}


def load_github_security(metadata: RepoMetadata, github_client: GitHubClient | None) -> dict:
    if github_client is None:
        return {
            "available": False,
            "provider_available": False,
            "security_and_analysis_available": False,
            "dependency_graph_enabled": None,
            "dependency_graph_status": "unavailable",
            "sbom_exportable": None,
            "sbom_status": "unavailable",
            "code_scanning_status": "unavailable",
            "code_scanning_alerts": None,
            "secret_scanning_status": "unavailable",
            "secret_scanning_alerts": None,
            "evidence": [],
        }

    owner, repo = metadata.full_name.split("/", 1)
    repo_security = github_client.get_repo_security_and_analysis(owner, repo)
    analysis = _normalize_security_and_analysis(repo_security.get("data"))
    secret_scan = github_client.get_secret_scanning_alert_count(owner, repo)
    code_scan = github_client.get_code_scanning_alert_count(owner, repo)
    sbom = github_client.get_sbom_exportability(owner, repo)

    dependency_graph_enabled: bool | None = None
    dependency_graph_status = "unavailable"
    if sbom.get("available"):
        dependency_graph_enabled = True
        dependency_graph_status = "enabled"
    elif sbom.get("http_status") == 404:
        dependency_graph_enabled = False
        dependency_graph_status = "not-configured"

    secret_scanning_status = "unavailable"
    if analysis.get("secret_scanning", {}).get("status") == "enabled":
        secret_scanning_status = "enabled"
    elif secret_scan.get("available"):
        secret_scanning_status = "alerts-open" if (secret_scan.get("open_alerts") or 0) > 0 else "enabled"
    elif analysis.get("secret_scanning", {}).get("status"):
        secret_scanning_status = analysis["secret_scanning"]["status"]

    code_scanning_status = "unavailable"
    if code_scan.get("available"):
        code_scanning_status = "alerts-open" if (code_scan.get("open_alerts") or 0) > 0 else "enabled"
    elif code_scan.get("http_status") == 404:
        code_scanning_status = "not-configured"

    evidence: list[str] = []
    if dependency_graph_status != "unavailable":
        evidence.append(f"Dependency graph: {dependency_graph_status}")
    if sbom.get("available"):
        evidence.append("SBOM export available")
    elif sbom.get("http_status") == 404:
        evidence.append("SBOM export unavailable")
    if code_scanning_status != "unavailable":
        evidence.append(
            "Code scanning: "
            + (f"{code_scanning_status} ({code_scan.get('open_alerts', 0)} alerts)" if code_scan.get("available") else code_scanning_status)
        )
    if secret_scanning_status != "unavailable":
        evidence.append(
            "Secret scanning: "
            + (f"{secret_scanning_status} ({secret_scan.get('open_alerts', 0)} alerts)" if secret_scan.get("available") else secret_scanning_status)
        )

    provider_available = bool(repo_security.get("available") or secret_scan.get("available") or code_scan.get("available") or sbom.get("available"))
    return {
        "available": provider_available,
        "provider_available": provider_available,
        "security_and_analysis_available": repo_security.get("available", False),
        "dependency_graph_enabled": dependency_graph_enabled,
        "dependency_graph_status": dependency_graph_status,
        "sbom_exportable": True if sbom.get("available") else (False if sbom.get("http_status") == 404 else None),
        "sbom_status": "enabled" if sbom.get("available") else ("not-configured" if sbom.get("http_status") == 404 else "unavailable"),
        "code_scanning_status": code_scanning_status,
        "code_scanning_alerts": code_scan.get("open_alerts"),
        "secret_scanning_status": secret_scanning_status,
        "secret_scanning_alerts": secret_scan.get("open_alerts"),
        "security_and_analysis": analysis,
        "evidence": evidence,
    }


def _github_provider_score(github: dict) -> float | None:
    if not github.get("provider_available"):
        return None

    score = 0.55
    dependency_graph_enabled = github.get("dependency_graph_enabled")
    if dependency_graph_enabled is True:
        score += 0.10
    elif dependency_graph_enabled is False:
        score -= 0.08

    sbom_exportable = github.get("sbom_exportable")
    if sbom_exportable is True:
        score += 0.08
    elif sbom_exportable is False:
        score -= 0.05

    code_status = github.get("code_scanning_status")
    code_alerts = github.get("code_scanning_alerts") or 0
    if code_status == "enabled":
        score += 0.10
    elif code_status == "alerts-open":
        score -= min(0.18, code_alerts * 0.03)
    elif code_status == "not-configured":
        score -= 0.08

    secret_status = github.get("secret_scanning_status")
    secret_alerts = github.get("secret_scanning_alerts") or 0
    if secret_status == "enabled":
        score += 0.10
    elif secret_status == "alerts-open":
        score -= min(0.20, secret_alerts * 0.05)
    elif secret_status not in {"enabled", "alerts-open", "unavailable"}:
        score -= 0.08

    return _clamp(score)


def _scorecard_provider_score(scorecard: dict) -> float | None:
    raw = scorecard.get("score")
    if raw is None:
        return None
    return _clamp(float(raw) / 10.0)


def _build_security_recommendations(local: dict, github: dict, scorecard: dict, metadata: RepoMetadata) -> list[dict]:
    recommendations: list[dict] = []

    if local.get("secrets_found", 0) > 0:
        recommendations.append({
            "key": "remove-exposed-secrets",
            "title": "Remove exposed secrets",
            "why": "Potential secrets were detected in the repository and should be rotated and removed before promotion.",
            "expected_posture_lift": 0.18,
            "effort": "high",
            "priority": "high",
            "source": "local",
        })
    if not local.get("has_security_md", False):
        recommendations.append({
            "key": "add-security-md",
            "title": "Add SECURITY.md",
            "why": "The repo is missing a published security policy and disclosure path.",
            "expected_posture_lift": 0.08,
            "effort": "small",
            "priority": "medium",
            "source": "local",
        })
    if not local.get("has_dependabot", False):
        recommendations.append({
            "key": "add-dependabot-config",
            "title": "Add Dependabot config",
            "why": "Automated dependency updates are missing, which weakens supply-chain hygiene.",
            "expected_posture_lift": 0.1,
            "effort": "small",
            "priority": "medium",
            "source": "local",
        })

    if github.get("provider_available"):
        if github.get("code_scanning_status") == "not-configured":
            recommendations.append({
                "key": "enable-codeql-default-setup",
                "title": "Enable CodeQL default setup",
                "why": "GitHub code scanning is not configured, so code-level findings are not being surfaced.",
                "expected_posture_lift": 0.12,
                "effort": "medium",
                "priority": "high",
                "source": "github",
            })
        elif github.get("code_scanning_status") == "alerts-open":
            recommendations.append({
                "key": "review-code-scanning-alerts",
                "title": "Review open code scanning alerts",
                "why": "GitHub reports open code scanning alerts that should be triaged before promotion.",
                "expected_posture_lift": 0.14,
                "effort": "medium",
                "priority": "high",
                "source": "github",
            })

        if github.get("secret_scanning_status") not in {"enabled", "alerts-open", "unavailable"}:
            recommendations.append({
                "key": "enable-secret-scanning",
                "title": "Enable secret scanning",
                "why": "GitHub secret scanning is not enabled where it appears available.",
                "expected_posture_lift": 0.1,
                "effort": "small",
                "priority": "high",
                "source": "github",
            })
        elif github.get("secret_scanning_status") == "alerts-open":
            recommendations.append({
                "key": "review-secret-scanning-alerts",
                "title": "Review open secret scanning alerts",
                "why": "Open secret scanning alerts indicate credentials or tokens may need rotation and cleanup.",
                "expected_posture_lift": 0.2,
                "effort": "high",
                "priority": "high",
                "source": "github",
            })

        if github.get("sbom_exportable") is False or github.get("dependency_graph_enabled") is False:
            recommendations.append({
                "key": "export-sbom",
                "title": "Ensure dependency graph coverage and SBOM export",
                "why": "Dependency graph or SBOM coverage looks unavailable, which limits supply-chain visibility.",
                "expected_posture_lift": 0.08,
                "effort": "medium",
                "priority": "medium",
                "source": "github",
            })

    if not metadata.private:
        scorecard_score = scorecard.get("score")
        if scorecard_score is None:
            recommendations.append({
                "key": "add-scorecard-action",
                "title": "Add OpenSSF Scorecard action",
                "why": "A Scorecard workflow would provide continuous external security hygiene signals for this public repo.",
                "expected_posture_lift": 0.06,
                "effort": "small",
                "priority": "low",
                "source": "scorecard",
            })
        elif float(scorecard_score) < 7.5:
            recommendations.append({
                "key": "improve-scorecard-checks",
                "title": "Improve low Scorecard checks",
                "why": "External Scorecard checks indicate notable security hygiene gaps on this public repo.",
                "expected_posture_lift": 0.08,
                "effort": "medium",
                "priority": "medium",
                "source": "scorecard",
            })

    recommendations.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["priority"], 3),
            -item["expected_posture_lift"],
            item["title"],
        )
    )
    return recommendations[:6]


def build_security_posture(
    metadata: RepoMetadata,
    results: list[AnalyzerResult],
    github_client: GitHubClient | None = None,
    *,
    scorecard_enabled: bool = False,
    security_offline: bool = False,
) -> dict:
    local = summarize_local_security_posture(results)
    github = load_github_security(metadata, None if security_offline else github_client)
    scorecard = (
        load_scorecard_security(metadata)
        if scorecard_enabled and not security_offline
        else {
            "available": False,
            "enabled": bool(scorecard_enabled and not metadata.private and not security_offline),
            "score": None,
            "checks": {},
            "reason": "disabled" if not scorecard_enabled else ("offline" if security_offline else "private-repo"),
            "repo": _scorecard_repo_path(metadata),
        }
    )

    github_score = _github_provider_score(github)
    scorecard_score = _scorecard_provider_score(scorecard)

    weighted_total = local.get("score", 0.0) * 0.7
    weight_total = 0.7
    if github_score is not None:
        weighted_total += github_score * 0.2
        weight_total += 0.2
    if scorecard_score is not None:
        weighted_total += scorecard_score * 0.1
        weight_total += 0.1
    merged_score = _clamp(weighted_total / weight_total if weight_total else 0.0)

    recommendations = _build_security_recommendations(local, github, scorecard, metadata)
    evidence = list(local.get("evidence", []))
    evidence.extend(github.get("evidence", []))
    if scorecard.get("available"):
        evidence.append(f"Scorecard score: {scorecard.get('score')}")

    providers = {
        "local": {
            "available": local.get("available", False),
            "score": local.get("score", 0.0),
        },
        "github": {
            "available": github.get("provider_available", False),
            "score": github_score,
        },
        "scorecard": {
            "available": scorecard.get("available", False),
            "score": scorecard_score,
        },
    }

    return {
        "label": _label_for_score(merged_score),
        "score": merged_score,
        "secrets_found": local.get("secrets_found", 0),
        "dangerous_files": local.get("dangerous_files", []),
        "has_security_md": local.get("has_security_md", False),
        "has_dependabot": local.get("has_dependabot", False),
        "evidence": evidence[:8],
        "local": local,
        "github": github,
        "scorecard": scorecard,
        "providers": providers,
        "recommendations": recommendations,
    }


def build_security_governance_preview(audits: list[RepoAudit]) -> list[dict]:
    preview: list[dict] = []
    for audit in audits:
        for item in audit.security_posture.get("recommendations", []):
            preview.append({
                "repo": audit.metadata.name,
                "target_repo": audit.metadata.full_name,
                **item,
            })
    preview.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item.get("priority", "low"), 3),
            -(item.get("expected_posture_lift", 0.0)),
            item.get("repo", ""),
        )
    )
    return preview[:20]
