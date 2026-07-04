"""Portfolio-level security drift gate.

The gate reads the canonical portfolio-truth snapshot and answers one narrow
operator question: did any scanned repo regain open high/critical Dependabot
alerts?  Missing security overlay data is treated as unknown, not healthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecurityGateItem:
    repo: str
    critical: int
    high: int
    risk_tier: str

    @property
    def total(self) -> int:
        return self.critical + self.high

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "critical": self.critical,
            "high": self.high,
            "risk_tier": self.risk_tier,
        }


@dataclass(frozen=True)
class SecurityGateReport:
    generated_at: str
    scanned_count: int
    total_open_critical: int
    total_open_high: int
    flagged_repos: tuple[SecurityGateItem, ...]

    @property
    def repos_with_open_high_critical(self) -> int:
        return len(self.flagged_repos)

    @property
    def passed(self) -> bool:
        return self.scanned_count > 0 and self.repos_with_open_high_critical == 0

    @property
    def status(self) -> str:
        if self.scanned_count <= 0:
            return "unknown"
        if self.repos_with_open_high_critical > 0:
            return "fail"
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "passed": self.passed,
            "scanned_count": self.scanned_count,
            "repos_with_open_high_critical": self.repos_with_open_high_critical,
            "total_open_critical": self.total_open_critical,
            "total_open_high": self.total_open_high,
            "flagged_repos": [item.to_dict() for item in self.flagged_repos],
        }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_security_gate_report(portfolio_truth: dict[str, Any]) -> SecurityGateReport:
    projects = portfolio_truth.get("projects") or []
    scanned_count = 0
    total_critical = 0
    total_high = 0
    flagged: list[SecurityGateItem] = []

    for project in projects:
        if not isinstance(project, dict):
            continue
        security = _mapping(project.get("security"))
        if not security.get("alerts_available"):
            continue

        scanned_count += 1
        critical = _int(security.get("dependabot_critical"))
        high = _int(security.get("dependabot_high"))
        total_critical += critical
        total_high += high
        if critical <= 0 and high <= 0:
            continue

        identity = _mapping(project.get("identity"))
        risk = _mapping(project.get("risk"))
        flagged.append(
            SecurityGateItem(
                repo=(
                    _text(identity.get("display_name"))
                    or _text(identity.get("repo_full_name"))
                    or _text(identity.get("path"))
                    or "Repo"
                ),
                critical=critical,
                high=high,
                risk_tier=_text(risk.get("risk_tier")) or "baseline",
            )
        )

    flagged.sort(key=lambda item: (-item.critical, -item.high, item.repo.lower()))
    return SecurityGateReport(
        generated_at=_text(portfolio_truth.get("generated_at")) or "unknown",
        scanned_count=scanned_count,
        total_open_critical=total_critical,
        total_open_high=total_high,
        flagged_repos=tuple(flagged),
    )


def render_security_gate_markdown(report: SecurityGateReport) -> str:
    lines = [
        "# Portfolio Security Gate",
        "",
        (
            f"Status: {report.status.upper()} | scanned {report.scanned_count} | "
            f"repos with open high/critical {report.repos_with_open_high_critical} | "
            f"critical {report.total_open_critical} | high {report.total_open_high}"
        ),
        f"Source freshness: {report.generated_at}",
        "",
    ]

    if report.status == "unknown":
        lines.append(
            "Security overlay was not present in the snapshot. Re-run portfolio truth with "
            "`--portfolio-truth-include-security` before treating the portfolio as clear."
        )
    elif report.passed:
        lines.append("All scanned repos are clear of open high/critical Dependabot alerts.")
    else:
        lines.append("| Repo | Risk | Critical | High |")
        lines.append("|---|---:|---:|---:|")
        for item in report.flagged_repos:
            lines.append(f"| {item.repo} | {item.risk_tier} | {item.critical} | {item.high} |")

    return "\n".join(lines)
