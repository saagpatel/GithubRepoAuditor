from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.portfolio_truth_render import GENERATED_MARKDOWN_PROVENANCE_MARKER
from src.portfolio_truth_types import SCHEMA_VERSION, truth_latest_path

DEFAULT_MAX_STALENESS_HOURS = 30
WORKLIST_SCHEMA_VERSION = "operator_os_seam_linter_worklist.v1"

# v0.1: identity-resolution check - blocked on dialect census.
IDENTITY_RESOLUTION_EXTENSION_POINT = (
    "v0.1: identity-resolution check - blocked on dialect census"
)


@dataclass(frozen=True)
class SeamLintFinding:
    check: str
    artifact: str
    violation: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "check": self.check,
            "artifact": self.artifact,
            "violation": self.violation,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SeamLintResult:
    generated_at: datetime
    expected_schema_version: str
    max_staleness_hours: int
    findings: tuple[SeamLintFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "operator_os_seam_linter.v0",
            "generated_at": self.generated_at.isoformat(),
            "state": "pass" if self.passed else "fail",
            "expected_schema_version": self.expected_schema_version,
            "max_staleness_hours": self.max_staleness_hours,
            "extension_points": [IDENTITY_RESOLUTION_EXTENSION_POINT],
            "findings": [finding.to_dict() for finding in self.findings],
        }


def lint_operator_os_seams(
    *,
    truth_path: Path,
    markdown_paths: list[Path],
    expected_schema_version: str = SCHEMA_VERSION,
    max_staleness_hours: int = DEFAULT_MAX_STALENESS_HOURS,
    now: datetime | None = None,
) -> SeamLintResult:
    generated_at = _aware(now or datetime.now(UTC))
    findings: list[SeamLintFinding] = []
    truth = _load_truth_artifact(truth_path, findings)
    if truth is not None:
        findings.extend(
            _check_artifact_freshness(
                truth,
                truth_path=truth_path,
                now=generated_at,
                max_staleness_hours=max_staleness_hours,
            )
        )
        findings.extend(
            _check_schema_pin(
                truth,
                truth_path=truth_path,
                expected_schema_version=expected_schema_version,
            )
        )
    findings.extend(_check_generated_markdown(markdown_paths))
    return SeamLintResult(
        generated_at=generated_at,
        expected_schema_version=expected_schema_version,
        max_staleness_hours=max_staleness_hours,
        findings=tuple(findings),
    )


def build_worklist_payload(result: SeamLintResult) -> dict[str, Any]:
    items = []
    for finding in result.findings:
        items.append(
            {
                "item_id": f"ghra_seam_linter:{finding.check}:{Path(finding.artifact).name}",
                "kind": "operator_os_seam_linter",
                "severity": "critical",
                "title": f"Operator-OS seam-linter failed: {finding.check}",
                "summary": f"{finding.artifact}: {finding.violation}. {finding.detail}",
                "target_type": "artifact",
                "target_id": finding.artifact,
                "created_at": result.generated_at.isoformat(),
                "suggested_command": (
                    "uv run python -m src.operator_os_seam_linter "
                    "--truth output/portfolio-truth-latest.json"
                ),
                "metadata_json": json.dumps(finding.to_dict(), sort_keys=True),
            }
        )
    return {
        "schema_version": WORKLIST_SCHEMA_VERSION,
        "generated_at": result.generated_at.isoformat(),
        "state": "pass" if result.passed else "fail",
        "source": "GithubRepoAuditor",
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace_root).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    truth_path = Path(args.truth).expanduser() if args.truth else truth_latest_path(output_dir)
    markdown_paths = [Path(path).expanduser() for path in args.markdown]
    if not markdown_paths:
        markdown_paths = [
            workspace_root / "project-registry.md",
            workspace_root / "PORTFOLIO-AUDIT-REPORT.md",
        ]
    result = lint_operator_os_seams(
        truth_path=truth_path,
        markdown_paths=markdown_paths,
        expected_schema_version=args.expected_schema_version,
        max_staleness_hours=args.max_staleness_hours,
    )
    payload = result.to_dict()
    if args.worklist_output:
        worklist_path = Path(args.worklist_output).expanduser()
        worklist_path.parent.mkdir(parents=True, exist_ok=True)
        worklist_path.write_text(json.dumps(build_worklist_payload(result), indent=2) + "\n")
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_text_summary(result)
    return 0 if result.passed else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="operator-os-seam-linter",
        description="Lint the small Operator-OS seam contract owned by GithubRepoAuditor.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "Projects")
    parser.add_argument("--truth", type=Path, default=None)
    parser.add_argument("--markdown", action="append", default=[])
    parser.add_argument("--worklist-output", type=Path, default=None)
    parser.add_argument("--expected-schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--max-staleness-hours", type=int, default=DEFAULT_MAX_STALENESS_HOURS)
    parser.add_argument("--json", action="store_true")
    return parser


def _load_truth_artifact(
    truth_path: Path, findings: list[SeamLintFinding]
) -> dict[str, Any] | None:
    try:
        data = json.loads(truth_path.read_text())
    except FileNotFoundError:
        findings.append(
            SeamLintFinding(
                check="artifact_freshness",
                artifact=str(truth_path),
                violation="truth artifact is missing",
                detail="Regenerate portfolio truth before downstream consumers read it.",
            )
        )
        return None
    except json.JSONDecodeError as exc:
        findings.append(
            SeamLintFinding(
                check="schema_pin",
                artifact=str(truth_path),
                violation="truth artifact is not valid JSON",
                detail=str(exc),
            )
        )
        return None
    if not isinstance(data, dict):
        findings.append(
            SeamLintFinding(
                check="schema_pin",
                artifact=str(truth_path),
                violation="truth artifact root is not an object",
                detail="Expected the portfolio truth JSON object contract.",
            )
        )
        return None
    return data


def _check_artifact_freshness(
    truth: dict[str, Any],
    *,
    truth_path: Path,
    now: datetime,
    max_staleness_hours: int,
) -> list[SeamLintFinding]:
    raw_generated_at = truth.get("generated_at")
    if not isinstance(raw_generated_at, str) or not raw_generated_at.strip():
        return [
            SeamLintFinding(
                check="artifact_freshness",
                artifact=str(truth_path),
                violation="generated_at is missing",
                detail="The truth artifact must declare when it was generated.",
            )
        ]
    try:
        generated_at = _parse_datetime(raw_generated_at)
    except ValueError as exc:
        return [
            SeamLintFinding(
                check="artifact_freshness",
                artifact=str(truth_path),
                violation="generated_at is not parseable",
                detail=str(exc),
            )
        ]
    max_age = timedelta(hours=max_staleness_hours)
    age = now - generated_at
    if age > max_age:
        return [
            SeamLintFinding(
                check="artifact_freshness",
                artifact=str(truth_path),
                violation="truth artifact is stale",
                detail=(
                    f"generated_at={raw_generated_at}; "
                    f"age_hours={age.total_seconds() / 3600:.2f}; "
                    f"max_staleness_hours={max_staleness_hours}"
                ),
            )
        ]
    if generated_at - now > timedelta(minutes=5):
        return [
            SeamLintFinding(
                check="artifact_freshness",
                artifact=str(truth_path),
                violation="generated_at is in the future",
                detail=f"generated_at={raw_generated_at}; now={now.isoformat()}",
            )
        ]
    return []


def _check_schema_pin(
    truth: dict[str, Any],
    *,
    truth_path: Path,
    expected_schema_version: str,
) -> list[SeamLintFinding]:
    declared = truth.get("schema_version")
    if not isinstance(declared, str) or not declared.strip():
        return [
            SeamLintFinding(
                check="schema_pin",
                artifact=str(truth_path),
                violation="schema_version is missing",
                detail="The truth artifact must declare its schema pin.",
            )
        ]
    if declared != expected_schema_version:
        return [
            SeamLintFinding(
                check="schema_pin",
                artifact=str(truth_path),
                violation="schema_version mismatch",
                detail=f"declared={declared}; expected={expected_schema_version}",
            )
        ]
    return []


def _check_generated_markdown(markdown_paths: list[Path]) -> list[SeamLintFinding]:
    findings: list[SeamLintFinding] = []
    for path in markdown_paths:
        try:
            text = path.read_text()
        except FileNotFoundError:
            findings.append(
                SeamLintFinding(
                    check="markdown_generated_not_hand_edited",
                    artifact=str(path),
                    violation="generated markdown is missing",
                    detail="Expected a generated compatibility markdown artifact.",
                )
            )
            continue
        if GENERATED_MARKDOWN_PROVENANCE_MARKER not in text:
            findings.append(
                SeamLintFinding(
                    check="markdown_generated_not_hand_edited",
                    artifact=str(path),
                    violation="generated provenance marker is missing",
                    detail=(
                        "Regenerate this markdown with GithubRepoAuditor; "
                        "the linter does not guess via content diffs."
                    ),
                )
            )
    return findings


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _print_text_summary(result: SeamLintResult) -> None:
    state = "PASS" if result.passed else "FAIL"
    print(f"Operator-OS seam-linter: {state}")
    print(f"expected_schema_version={result.expected_schema_version}")
    print(f"max_staleness_hours={result.max_staleness_hours}")
    if not result.findings:
        print("No seam violations found.")
        return
    for finding in result.findings:
        print(f"- {finding.check}: {finding.artifact}: {finding.violation}")
        print(f"  {finding.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
