"""Leaf status overlays used while publishing portfolio truth."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.cache import ResponseCache
from src.github_client import GitHubClient
from src.github_security_coverage import (
    GITHUB_SECURITY_RECEIPT_FILENAME,
    LoadedSecurityCoverage,
    SecurityCoverageError,
    load_security_coverage_receipt,
)


def load_release_count_by_name(*, output_dir: Path, username: str) -> dict[str, int] | None:
    audit_files = sorted(
        output_dir.glob(f"audit-report-{username}-*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not audit_files:
        logging.getLogger(__name__).warning(
            "--portfolio-truth-include-release-count requires a prior audit run; "
            "no audit-report-%s-*.json found in %s — skipping release_count overlay",
            username,
            output_dir,
        )
        return None
    try:
        with audit_files[-1].open() as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "--portfolio-truth-include-release-count: could not read %s: %s — skipping",
            audit_files[-1],
            exc,
        )
        return None
    result: dict[str, int] = {}
    for audit in data.get("audits") or []:
        name = (audit.get("metadata") or {}).get("name")
        if not name:
            continue
        for analyzer_result in audit.get("analyzer_results") or []:
            if analyzer_result.get("dimension") == "activity":
                release_count = (analyzer_result.get("details") or {}).get("release_count")
                if isinstance(release_count, int):
                    result[name] = release_count
                break
    return result


def latest_audit_report_path(*, output_dir: Path, username: str) -> Path | None:
    audit_files = sorted(
        output_dir.glob(f"audit-report-{username}-*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    return audit_files[-1] if audit_files else None


def _repo_status_entries_from_metadata(
    repo_metadata: list[dict], *, source: str
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for metadata in repo_metadata:
        name = str(metadata.get("name") or "").strip()
        full_name = str(metadata.get("full_name") or "").strip()
        archived = metadata.get("archived")
        if not name or not isinstance(archived, bool):
            continue
        entry = {"archived": archived, "full_name": full_name, "source": source}
        result[name] = entry
        repo_name = full_name.rsplit("/", 1)[-1] if full_name else ""
        if repo_name:
            result.setdefault(repo_name, entry)
    return result


def load_live_repo_status_by_name(
    *, username: str, token: str | None, cache: ResponseCache | None
) -> dict[str, dict] | None:
    try:
        repos = GitHubClient(token=token, cache=cache).list_repos(username)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "--portfolio-truth: could not fetch live GitHub repo status for %s: %s — "
            "falling back to latest audit report metadata",
            username,
            exc,
        )
        return None
    return _repo_status_entries_from_metadata(repos, source="github_api")


def load_repo_status_from_audit_by_name(
    *, output_dir: Path, username: str
) -> dict[str, dict] | None:
    audit_path = latest_audit_report_path(output_dir=output_dir, username=username)
    if audit_path is None:
        return None
    try:
        with audit_path.open() as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "--portfolio-truth: could not read repo status overlay from %s: %s — skipping",
            audit_path,
            exc,
        )
        return None
    repo_metadata = [
        metadata
        for audit in data.get("audits") or []
        if isinstance(metadata := audit.get("metadata") or {}, dict)
    ]
    return _repo_status_entries_from_metadata(repo_metadata, source="audit_report")


def load_security_alerts_by_name(
    *, output_dir: Path, username: str
) -> dict[str, dict] | None:
    ghas_files = sorted(
        output_dir.glob(f"ghas-alerts-{username}-*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not ghas_files:
        logging.getLogger(__name__).warning(
            "--portfolio-truth-include-security requires a prior `audit report --ghas-alerts` "
            "run; no ghas-alerts-%s-*.json found in %s — skipping security overlay",
            username,
            output_dir,
        )
        return None
    try:
        with ghas_files[-1].open() as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "--portfolio-truth-include-security: could not read %s: %s — skipping",
            ghas_files[-1],
            exc,
        )
        return None
    if not isinstance(data, dict):
        logging.getLogger(__name__).warning(
            "--portfolio-truth-include-security: %s is not a name-keyed object — skipping",
            ghas_files[-1],
        )
        return None
    return {name: entry for name, entry in data.items() if isinstance(entry, dict)}


def load_security_coverage_by_full_name(
    *,
    output_dir: Path,
    receipt_path: Path | None = None,
    max_age_hours: int = 24,
    now: datetime | None = None,
) -> LoadedSecurityCoverage | None:
    """Load the canonical provenance-bearing security receipt.

    Unlike the legacy GHAS overlay loader above, this path never discovers
    candidates by filesystem mtime.  The fixed pointer or explicit path must
    validate its embedded schema, producer, cohort, observation timestamps, and
    freshness before PortfolioTruth may consume it.
    """
    selected = receipt_path or output_dir / GITHUB_SECURITY_RECEIPT_FILENAME
    try:
        return load_security_coverage_receipt(
            selected,
            max_age_hours=max_age_hours,
            now=now,
        )
    except SecurityCoverageError as exc:
        logging.getLogger(__name__).warning(
            "--portfolio-truth-include-security: %s — security coverage remains unknown",
            exc,
        )
        return None
