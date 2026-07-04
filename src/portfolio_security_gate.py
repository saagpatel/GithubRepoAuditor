"""Portfolio-level security drift gate.

The gate reads the canonical portfolio-truth snapshot and answers one narrow
operator question: did any scanned repo regain open high/critical Dependabot
alerts?  Missing security overlay data is treated as unknown, not healthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    max_age_hours: int | None = None
    source_age_hours: float | None = None
    freshness_error: str | None = None

    @property
    def repos_with_open_high_critical(self) -> int:
        return len(self.flagged_repos)

    @property
    def passed(self) -> bool:
        return (
            self.scanned_count > 0
            and self.repos_with_open_high_critical == 0
            and not self.is_stale
        )

    @property
    def is_stale(self) -> bool:
        if self.max_age_hours is None:
            return False
        if self.freshness_error:
            return True
        if self.source_age_hours is None:
            return True
        return self.source_age_hours > self.max_age_hours

    @property
    def status(self) -> str:
        if self.scanned_count <= 0:
            return "unknown"
        if self.is_stale:
            return "stale"
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
            "max_age_hours": self.max_age_hours,
            "source_age_hours": self.source_age_hours,
            "freshness_error": self.freshness_error,
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


def _source_age_hours(generated_at: str, now: datetime) -> tuple[float | None, str | None]:
    if not generated_at or generated_at == "unknown":
        return None, "missing generated_at"
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None, f"invalid generated_at: {generated_at}"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_hours = (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    return round(age_hours / 3600, 3), None


def build_security_gate_report(
    portfolio_truth: dict[str, Any],
    *,
    max_age_hours: int | None = None,
    now: datetime | None = None,
) -> SecurityGateReport:
    projects = portfolio_truth.get("projects") or []
    scanned_count = 0
    total_critical = 0
    total_high = 0
    flagged: list[SecurityGateItem] = []
    generated_at = _text(portfolio_truth.get("generated_at")) or "unknown"
    source_age_hours = freshness_error = None
    if max_age_hours is not None:
        source_age_hours, freshness_error = _source_age_hours(
            generated_at,
            now or datetime.now(timezone.utc),
        )

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
        generated_at=generated_at,
        scanned_count=scanned_count,
        total_open_critical=total_critical,
        total_open_high=total_high,
        flagged_repos=tuple(flagged),
        max_age_hours=max_age_hours,
        source_age_hours=source_age_hours,
        freshness_error=freshness_error,
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
    elif report.status == "stale":
        if report.freshness_error:
            lines.append(f"Portfolio truth freshness could not be verified: {report.freshness_error}.")
        else:
            lines.append(
                f"Portfolio truth is {report.source_age_hours:.1f}h old, beyond the "
                f"{report.max_age_hours}h freshness threshold."
            )
    elif report.passed:
        lines.append("All scanned repos are clear of open high/critical Dependabot alerts.")
    else:
        lines.append("| Repo | Risk | Critical | High |")
        lines.append("|---|---:|---:|---:|")
        for item in report.flagged_repos:
            lines.append(f"| {item.repo} | {item.risk_tier} | {item.critical} | {item.high} |")

    return "\n".join(lines)
