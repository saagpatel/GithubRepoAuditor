from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.portfolio_truth_render import GENERATED_MARKDOWN_PROVENANCE_MARKER
from src.portfolio_truth_types import SCHEMA_VERSION, truth_latest_path
from src.project_registry import (
    BRIDGE_CANONICAL_KEY_DISAGREEMENTS,
    IDENTITY_ALIAS_MAP,
    IDENTITY_ALIAS_MAP_DEPRECATES_AFTER,
    normalize,
)

DEFAULT_MAX_STALENESS_HOURS = 30
WORKLIST_SCHEMA_VERSION = "operator_os_seam_linter_worklist.v1"
DEFAULT_BRIDGE_DB_PATH = Path("~/.local/share/bridge-db/bridge.db").expanduser()
DEFAULT_NOTIFICATION_DB_PATH = Path(
    "~/.local/share/notification-hub/inbox.sqlite3"
).expanduser()
DEFAULT_NOTION_SNAPSHOT_PATH = Path(
    "~/.local/share/notion-os/project-snapshot.json"
).expanduser()

HEX_FRAGMENT_RE = re.compile(r"^[0-9a-fA-F]{3}$")
EXPLICIT_UNRESOLVED_IDENTITIES = {"homeadhoc", "unresolved"}


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
            "findings": [finding.to_dict() for finding in self.findings],
        }


def lint_operator_os_seams(
    *,
    truth_path: Path,
    markdown_paths: list[Path],
    expected_schema_version: str = SCHEMA_VERSION,
    max_staleness_hours: int = DEFAULT_MAX_STALENESS_HOURS,
    bridge_db_path: Path | None = None,
    notification_db_path: Path | None = None,
    notion_snapshot_path: Path | None = None,
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
        findings.extend(
            _check_identity_resolution(
                truth,
                bridge_db_path=bridge_db_path,
                notification_db_path=notification_db_path,
                notion_snapshot_path=notion_snapshot_path,
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
        bridge_db_path=args.bridge_db if args.identity_resolution else None,
        notification_db_path=args.notification_db if args.identity_resolution else None,
        notion_snapshot_path=args.notion_snapshot if args.identity_resolution else None,
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
    parser.add_argument(
        "--identity-resolution",
        action="store_true",
        help="Also audit cross-store project identity dialects in local operator stores.",
    )
    parser.add_argument("--bridge-db", type=Path, default=DEFAULT_BRIDGE_DB_PATH)
    parser.add_argument("--notification-db", type=Path, default=DEFAULT_NOTIFICATION_DB_PATH)
    parser.add_argument("--notion-snapshot", type=Path, default=DEFAULT_NOTION_SNAPSHOT_PATH)
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


def _check_identity_resolution(
    truth: dict[str, Any],
    *,
    bridge_db_path: Path | None,
    notification_db_path: Path | None,
    notion_snapshot_path: Path | None,
) -> list[SeamLintFinding]:
    resolver = _build_identity_resolver(truth)
    findings: list[SeamLintFinding] = []
    checked = resolved = explicit_unresolved = 0

    for identity in _read_emitted_identities(
        bridge_db_path=bridge_db_path,
        notification_db_path=notification_db_path,
        notion_snapshot_path=notion_snapshot_path,
    ):
        checked += 1
        raw = identity["value"]
        source = identity["source"]
        field = identity["field"]
        artifact = identity["artifact"]
        normalized = _identity_norm(raw)

        if normalized in EXPLICIT_UNRESOLVED_IDENTITIES:
            explicit_unresolved += 1
            continue
        if _is_silent_unresolved_identity(raw):
            findings.append(
                _identity_finding(
                    artifact=artifact,
                    violation="silent unresolved identity",
                    detail=(
                        f"{source}.{field} emitted {raw!r}; use explicit "
                        "home-adhoc/unresolved instead of empty, None, or hex fragments."
                    ),
                )
            )
            continue

        canonical = resolver.get(normalized)
        if canonical is None:
            findings.append(
                _identity_finding(
                    artifact=artifact,
                    violation="minted identity dialect",
                    detail=(
                        f"{source}.{field} emitted {raw!r}, which is not in the "
                        f"census-seeded alias map. checked={checked}; "
                        f"resolved={resolved}; explicit_unresolved={explicit_unresolved}; "
                        f"deprecates_after={IDENTITY_ALIAS_MAP_DEPRECATES_AFTER}"
                    ),
                )
            )
            continue

        resolved += 1
        if source == "bridge" and field == "canonical_key":
            disagreement = BRIDGE_CANONICAL_KEY_DISAGREEMENTS.get(str(raw))
            if disagreement:
                findings.append(
                    _identity_finding(
                        artifact=artifact,
                        violation="bridge canonical_key disagrees with alias map",
                        detail=(
                            f"bridge.canonical_key emitted {raw!r}; {disagreement} "
                            f"resolved_canonical={canonical}"
                        ),
                    )
                )

    if findings:
        summary = (
            f" identity_resolution_summary checked={checked}; resolved={resolved}; "
            f"explicit_unresolved={explicit_unresolved}; findings={len(findings)}"
        )
        return [
            SeamLintFinding(
                check=finding.check,
                artifact=finding.artifact,
                violation=finding.violation,
                detail=f"{finding.detail};{summary}",
            )
            for finding in findings
        ]
    return []


def _identity_finding(*, artifact: str, violation: str, detail: str) -> SeamLintFinding:
    return SeamLintFinding(
        check="identity_resolution",
        artifact=artifact,
        violation=violation,
        detail=detail,
    )


def _build_identity_resolver(truth: dict[str, Any]) -> dict[str, str]:
    resolver: dict[str, str] = {}
    for alias, canonical in IDENTITY_ALIAS_MAP.items():
        _add_identity_alias(resolver, alias, canonical)
    for project in truth.get("projects", []):
        if not isinstance(project, dict):
            continue
        identity = project.get("identity")
        if not isinstance(identity, dict):
            continue
        canonical = identity.get("repo_full_name")
        if not isinstance(canonical, str) or "/" not in canonical:
            continue
        for value in (
            identity.get("display_name"),
            identity.get("repo_full_name"),
            _repo_name(canonical),
        ):
            _add_identity_alias(resolver, value, canonical)
        _add_identity_alias(resolver, _flatten_project_key(identity.get("project_key")), canonical)
    return resolver


def _add_identity_alias(
    resolver: dict[str, str], alias: object, canonical: str | None
) -> None:
    if not isinstance(alias, str) or not isinstance(canonical, str) or not canonical:
        return
    normalized = _identity_norm(alias)
    if normalized:
        resolver.setdefault(normalized, canonical)


def _read_emitted_identities(
    *,
    bridge_db_path: Path | None,
    notification_db_path: Path | None,
    notion_snapshot_path: Path | None,
) -> list[dict[str, str]]:
    identities: list[dict[str, str]] = []
    identities.extend(_read_bridge_identities(bridge_db_path))
    identities.extend(_read_notification_identities(notification_db_path))
    identities.extend(_read_session_cost_identities(bridge_db_path))
    identities.extend(_read_notion_title_identities(notion_snapshot_path))
    return identities


def _read_bridge_identities(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    rows = _sqlite_rows(
        path,
        "SELECT DISTINCT project_name, canonical_key FROM activity_log",
    )
    identities: list[dict[str, str]] = []
    for project_name, canonical_key in rows:
        if project_name is not None:
            identities.append(
                {
                    "source": "bridge",
                    "field": "project_name",
                    "value": str(project_name),
                    "artifact": str(path),
                }
            )
        if canonical_key is not None:
            identities.append(
                {
                    "source": "bridge",
                    "field": "canonical_key",
                    "value": str(canonical_key),
                    "artifact": str(path),
                }
            )
    return identities


def _read_session_cost_identities(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    rows = _sqlite_rows(
        path,
        "SELECT DISTINCT project_name FROM session_costs",
    )
    return [
        {
            "source": "session_costs",
            "field": "project_name",
            "value": "" if row[0] is None else str(row[0]),
            "artifact": str(path),
        }
        for row in rows
    ]


def _read_notification_identities(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    if _sqlite_table_exists(path, "notification_feed"):
        rows = _sqlite_rows(path, "SELECT DISTINCT project FROM notification_feed")
    elif _sqlite_table_exists(path, "durable_events"):
        rows = _sqlite_rows(path, "SELECT DISTINCT project FROM durable_events")
    else:
        rows = []
    return [
        {
            "source": "notification_hub",
            "field": "project",
            "value": "" if row[0] is None else str(row[0]),
            "artifact": str(path),
        }
        for row in rows
    ]


def _read_notion_title_identities(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    projects = payload.get("projects", []) if isinstance(payload, dict) else []
    return [
        {
            "source": "notion",
            "field": "title",
            "value": str(project.get("title", "")),
            "artifact": str(path),
        }
        for project in projects
        if isinstance(project, dict)
    ]


def _sqlite_rows(path: Path, query: str) -> list[tuple[Any, ...]]:
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            return list(conn.execute(query).fetchall())
    except sqlite3.Error:
        return []


def _sqlite_table_exists(path: Path, table: str) -> bool:
    safe_table = table.replace("'", "''")
    rows = _sqlite_rows(
        path,
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{safe_table}'",
    )
    return any(row[0] == table for row in rows)


def _identity_norm(value: object) -> str:
    if value is None:
        return ""
    return normalize(str(value))


def _is_silent_unresolved_identity(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.lower() == "none" or bool(HEX_FRAGMENT_RE.fullmatch(text))


def _repo_name(repo_full_name: str) -> str:
    return repo_full_name.rsplit("/", 1)[-1]


def _flatten_project_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


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
