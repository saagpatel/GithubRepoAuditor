from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from src.github_security_coverage import (
    SecurityCoverageError,
    SecurityCoverageReceiptBinding,
    verified_security_coverage_receipt_binding,
)
from src.portfolio_truth_reconcile import (
    build_portfolio_truth_snapshot,
    load_prior_notion_context,
)
from src.portfolio_truth_render import render_portfolio_report_markdown, render_registry_markdown
from src.portfolio_truth_lineage import resolve_notion_origin
from src.portfolio_truth_types import truth_latest_path
from src.producer_preflight import ProducerEvidence, verify_evidence_still_current
from src.portfolio_truth_validate import (
    canonicalize_truth_snapshot_payload,
    validate_portfolio_report_markdown,
    validate_publish_targets,
    validate_registry_markdown,
    validate_truth_snapshot,
)
from src.project_registry import build_project_registry, load_source_paths


_PORTFOLIO_TRUTH_IN_PROCESS_LOCK = threading.Lock()


@dataclass(frozen=True)
class PortfolioTruthPublishResult:
    snapshot_path: Path
    latest_path: Path
    registry_output: Path
    portfolio_report_output: Path
    project_count: int
    registry_changed: bool
    report_changed: bool
    project_registry_path: Path | None = None


@dataclass(frozen=True)
class _PriorSecurityEvidence:
    path: Path
    content_sha256: str | None
    alerts_by_full_name: dict[str, dict]


class PortfolioTruthPublishError(RuntimeError):
    """Raised when publishing would corrupt or misrepresent portfolio truth."""


def _parse_bound_datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PortfolioTruthPublishError(f"{field} is required.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioTruthPublishError(f"{field} is invalid.") from exc
    if parsed.tzinfo is None:
        raise PortfolioTruthPublishError(f"{field} must include a timezone.")
    return parsed


def _load_prior_security_alerts(
    latest_path: Path,
    *,
    current_security_metadata: dict[str, object],
    security_max_age_hours: int,
) -> _PriorSecurityEvidence:
    """Load validated prior receipt evidence for independent cohort derivation."""
    try:
        content = latest_path.read_bytes()
    except FileNotFoundError:
        return _PriorSecurityEvidence(
            path=latest_path,
            content_sha256=None,
            alerts_by_full_name={},
        )
    except OSError as exc:
        raise PortfolioTruthPublishError(
            f"Prior PortfolioTruth cannot authorize security cohort derivation: {exc}"
        ) from exc

    try:
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("snapshot must be an object")
        canonical = canonicalize_truth_snapshot_payload(
            payload,
            security_max_age_hours=security_max_age_hours,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise PortfolioTruthPublishError(
            f"Prior PortfolioTruth cannot authorize security cohort derivation: {exc}"
        ) from exc

    projects = canonical.get("projects") or []
    receipt_projects = [
        project
        for project in projects
        if (project.get("security") or {}).get("receipt_schema_version")
    ]
    if receipt_projects:
        github_security = (canonical.get("inputs") or {}).get("github_security") or {}
        if not github_security.get("receipt_id") or not github_security.get(
            "content_sha256"
        ):
            raise PortfolioTruthPublishError(
                "Prior PortfolioTruth security evidence is not immutably bound."
            )

    prior_generated_at = _parse_bound_datetime(
        canonical.get("generated_at"),
        field="Prior PortfolioTruth generated_at",
    )
    current_produced_at = _parse_bound_datetime(
        current_security_metadata.get("produced_at"),
        field="Current security receipt produced_at",
    )
    if prior_generated_at > current_produced_at:
        raise PortfolioTruthPublishError(
            "Prior PortfolioTruth was generated after the current security receipt."
        )

    alerts: dict[str, dict] = {}
    for project in receipt_projects:
        identity = project.get("identity") or {}
        security = project.get("security") or {}
        repository = str(identity.get("repo_full_name") or "").strip()
        if not repository or security.get("cohort_member") is not True:
            continue
        if repository in alerts:
            raise PortfolioTruthPublishError(
                "Prior PortfolioTruth security cohort contains duplicate repository "
                f"identity: {repository}."
            )
        remote = (project.get("repository_state") or {}).get(
            "remote_default_branch"
        ) or {}
        alerts[repository] = {
            **security,
            "repo_full_name": repository,
            "repository": remote,
        }
    return _PriorSecurityEvidence(
        path=latest_path,
        content_sha256=hashlib.sha256(content).hexdigest(),
        alerts_by_full_name=alerts,
    )


def _verify_prior_security_evidence_current(
    evidence: _PriorSecurityEvidence,
) -> None:
    """Fail closed if the canonical truth pointer changed after candidate derivation."""
    try:
        content = evidence.path.read_bytes()
    except FileNotFoundError:
        if evidence.content_sha256 is None:
            return
        raise PortfolioTruthPublishError(
            "Prior PortfolioTruth disappeared after it authorized security cohort "
            "derivation."
        ) from None
    except OSError as exc:
        raise PortfolioTruthPublishError(
            "Prior PortfolioTruth could not be revalidated before publication: "
            f"{exc}"
        ) from exc

    observed_sha256 = hashlib.sha256(content).hexdigest()
    if evidence.content_sha256 is None or observed_sha256 != evidence.content_sha256:
        raise PortfolioTruthPublishError(
            "Prior PortfolioTruth changed after it authorized security cohort "
            "derivation."
        )


@contextmanager
def _portfolio_truth_publication_lock(latest_path: Path) -> Iterator[None]:
    """Serialize complete truth builds and replacement across local publishers."""
    lock_path = latest_path.with_name(f".{latest_path.name}.lock")
    with _PORTFOLIO_TRUTH_IN_PROCESS_LOCK:
        try:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            raise PortfolioTruthPublishError(
                f"PortfolioTruth publication lock is unavailable: {lock_path}: {exc}"
            ) from exc
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _REPO_ROOT / "config"


def _build_project_registry_json(snapshot, *, include_notion: bool) -> str:
    """Render the canonical cross-store project registry from a snapshot.

    External sources (bridge-db, Notion snapshot, memory) degrade gracefully
    when absent, so this never fails the publish run.
    """
    overrides_config_path = _CONFIG_DIR / "project-registry-overrides.json"
    sources = load_source_paths(overrides_config_path)

    scoring_pageids: dict[str, str] = {}
    if include_notion and sources.get("scoring_data_source_id"):
        try:
            from src.notion_client import get_notion_token
            from src.project_registry import fetch_scoring_pageids

            token = get_notion_token()
            if token:
                scoring_pageids = fetch_scoring_pageids(
                    str(sources["scoring_data_source_id"]), token
                )
        except Exception:
            scoring_pageids = {}

    registry = build_project_registry(
        snapshot.to_dict(),
        bridge_db_path=sources["bridge_db"],
        notion_snapshot_path=sources["notion_snapshot"],
        notion_project_map_path=_CONFIG_DIR / "notion-project-map.json",
        memory_dir=sources["memory_dir"],
        scoring_pageids=scoring_pageids,
        overrides_config_path=overrides_config_path,
        generated_at=snapshot.generated_at,
    )
    return json.dumps(registry, indent=2) + "\n"


def publish_portfolio_truth(
    *,
    workspace_root: Path,
    output_dir: Path,
    registry_output: Path,
    portfolio_report_output: Path,
    catalog_path: Path | None = None,
    legacy_registry_path: Path | None = None,
    include_notion: bool = True,
    allow_empty_notion: bool = False,
    release_count_by_name: dict[str, int] | None = None,
    security_alerts_by_name: dict[str, dict] | None = None,
    security_coverage_metadata: dict[str, object] | None = None,
    security_receipt_binding: SecurityCoverageReceiptBinding | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
    producer_evidence: ProducerEvidence | None = None,
    producer_repo_root: Path | None = None,
    require_producer_evidence: bool = False,
    now: datetime | None = None,
) -> PortfolioTruthPublishResult:
    if (
        security_coverage_metadata is not None
        or security_receipt_binding is not None
    ) and now is None:
        raise PortfolioTruthPublishError(
            "Receipt-backed security publication requires an explicit evaluation clock."
        )
    if require_producer_evidence and producer_evidence is None:
        raise PortfolioTruthPublishError(
            "Canonical publication requires validated producer evidence."
        )
    if producer_evidence is not None:
        if producer_repo_root is None:
            raise PortfolioTruthPublishError(
                "producer_repo_root is required with producer evidence."
            )
        try:
            verify_evidence_still_current(producer_repo_root, producer_evidence)
        except ValueError as exc:
            raise PortfolioTruthPublishError(str(exc)) from exc
    _validate_security_receipt_binding(
        metadata=security_coverage_metadata,
        binding=security_receipt_binding,
        required=require_producer_evidence
        and (
            security_alerts_by_name is not None
            or security_coverage_metadata is not None
        ),
    )
    validate_publish_targets(
        workspace_root=workspace_root,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
    )
    latest_path = truth_latest_path(output_dir)
    with _portfolio_truth_publication_lock(latest_path):
        return _publish_portfolio_truth_locked(
            workspace_root=workspace_root,
            output_dir=output_dir,
            registry_output=registry_output,
            portfolio_report_output=portfolio_report_output,
            catalog_path=catalog_path,
            legacy_registry_path=legacy_registry_path,
            include_notion=include_notion,
            allow_empty_notion=allow_empty_notion,
            release_count_by_name=release_count_by_name,
            security_alerts_by_name=security_alerts_by_name,
            security_coverage_metadata=security_coverage_metadata,
            security_receipt_binding=security_receipt_binding,
            repo_status_by_name=repo_status_by_name,
            producer_evidence=producer_evidence,
            producer_repo_root=producer_repo_root,
            require_producer_evidence=require_producer_evidence,
            now=now,
        )


def _publish_portfolio_truth_locked(
    *,
    workspace_root: Path,
    output_dir: Path,
    registry_output: Path,
    portfolio_report_output: Path,
    catalog_path: Path | None = None,
    legacy_registry_path: Path | None = None,
    include_notion: bool = True,
    allow_empty_notion: bool = False,
    release_count_by_name: dict[str, int] | None = None,
    security_alerts_by_name: dict[str, dict] | None = None,
    security_coverage_metadata: dict[str, object] | None = None,
    security_receipt_binding: SecurityCoverageReceiptBinding | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
    producer_evidence: ProducerEvidence | None = None,
    producer_repo_root: Path | None = None,
    require_producer_evidence: bool = False,
    now: datetime | None = None,
) -> PortfolioTruthPublishResult:
    if (
        security_coverage_metadata is not None
        or security_receipt_binding is not None
    ) and now is None:
        raise PortfolioTruthPublishError(
            "Receipt-backed security publication requires an explicit evaluation clock."
        )
    if require_producer_evidence and producer_evidence is None:
        raise PortfolioTruthPublishError(
            "Canonical publication requires validated producer evidence."
        )
    _validate_security_receipt_binding(
        metadata=security_coverage_metadata,
        binding=security_receipt_binding,
        required=require_producer_evidence
        and (
            security_alerts_by_name is not None
            or security_coverage_metadata is not None
        ),
    )
    validate_publish_targets(
        workspace_root=workspace_root,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
    )
    security_max_age_hours = (
        security_receipt_binding.max_age_hours
        if security_receipt_binding is not None
        else 24
    )
    latest_path = truth_latest_path(output_dir)
    notion_context_fallback = (
        load_prior_notion_context(latest_path) if allow_empty_notion else None
    )
    prior_notion_generated_at = resolve_notion_origin(latest_path)
    prior_security_evidence = (
        _load_prior_security_alerts(
            latest_path,
            current_security_metadata=security_coverage_metadata,
            security_max_age_hours=security_max_age_hours,
        )
        if security_coverage_metadata is not None
        and security_alerts_by_name is not None
        else None
    )
    build_result = build_portfolio_truth_snapshot(
        workspace_root=workspace_root,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=include_notion,
        notion_context_fallback=notion_context_fallback,
        release_count_by_name=release_count_by_name,
        security_alerts_by_name=security_alerts_by_name,
        security_coverage_metadata=security_coverage_metadata,
        prior_security_alerts_by_name=(
            prior_security_evidence.alerts_by_full_name
            if prior_security_evidence is not None
            else None
        ),
        repo_status_by_name=repo_status_by_name,
        producer=producer_evidence.to_dict() if producer_evidence else {},
        prior_notion_generated_at=prior_notion_generated_at,
        now=now,
    )
    validate_truth_snapshot(
        build_result.snapshot,
        security_max_age_hours=security_max_age_hours,
    )

    snapshot_stamp = build_result.snapshot.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_path = output_dir / f"portfolio-truth-{snapshot_stamp}.json"
    _guard_against_notion_context_drop(
        build_result.snapshot.source_summary,
        latest_path=latest_path,
        include_notion=include_notion,
        allow_empty_notion=allow_empty_notion,
    )
    latest_name = latest_path.name
    snapshot_json = json.dumps(build_result.snapshot.to_dict(), indent=2) + "\n"
    project_registry_path = output_dir / "project-registry.json"
    project_registry_json = _build_project_registry_json(
        build_result.snapshot, include_notion=include_notion
    )
    registry_markdown = render_registry_markdown(build_result.snapshot)
    report_markdown = render_portfolio_report_markdown(build_result.snapshot, latest_name)

    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=output_dir, suffix=".registry-check.md"
    ) as handle:
        temp_registry_path = Path(handle.name)
    try:
        validate_registry_markdown(registry_markdown, build_result.snapshot, temp_registry_path)
        validate_portfolio_report_markdown(report_markdown)
    finally:
        if temp_registry_path.exists():
            temp_registry_path.unlink()

    targets = {
        snapshot_path: snapshot_json,
        latest_path: snapshot_json,
        registry_output: registry_markdown,
        portfolio_report_output: report_markdown,
        project_registry_path: project_registry_json,
    }
    changed: dict[Path, bool] = {
        registry_output: _content_changed(registry_output, registry_markdown),
        portfolio_report_output: _content_changed(portfolio_report_output, report_markdown),
        snapshot_path: True,
        latest_path: True,
        project_registry_path: True,
    }
    temp_files = {path: _stage_text(path, content) for path, content in targets.items()}
    originals = {path: (path.read_text() if path.exists() else None) for path in targets}
    published: list[Path] = []

    # This live guard is intentionally separate from the snapshot's shared
    # evaluation clock: it catches receipt replacement or expiry before writes.
    publication_guard = (
        verified_security_coverage_receipt_binding(security_receipt_binding)
        if security_receipt_binding is not None
        else nullcontext()
    )
    try:
        if producer_evidence is not None and producer_repo_root is not None:
            verify_evidence_still_current(producer_repo_root, producer_evidence)
        with publication_guard as live_security:
            if (
                live_security is not None
                and live_security.entries_by_full_name != security_alerts_by_name
            ):
                raise PortfolioTruthPublishError(
                    "Security receipt normalized evidence changed after it was loaded."
                )
            if prior_security_evidence is not None:
                _verify_prior_security_evidence_current(prior_security_evidence)
            for path, staged in temp_files.items():
                if path in {registry_output, portfolio_report_output} and not changed[path]:
                    staged.unlink(missing_ok=True)
                    continue
                staged.replace(path)
                published.append(path)
    except Exception as exc:
        for path in reversed(published):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(original)
        for staged in temp_files.values():
            staged.unlink(missing_ok=True)
        if isinstance(exc, (SecurityCoverageError, ValueError)):
            raise PortfolioTruthPublishError(str(exc)) from exc
        raise

    for staged in temp_files.values():
        staged.unlink(missing_ok=True)

    return PortfolioTruthPublishResult(
        snapshot_path=snapshot_path,
        latest_path=latest_path,
        registry_output=registry_output,
        portfolio_report_output=portfolio_report_output,
        project_count=len(build_result.snapshot.projects),
        registry_changed=changed[registry_output],
        report_changed=changed[portfolio_report_output],
        project_registry_path=project_registry_path,
    )


def _validate_security_receipt_binding(
    *,
    metadata: dict[str, object] | None,
    binding: SecurityCoverageReceiptBinding | None,
    required: bool,
) -> None:
    if binding is None:
        if required:
            raise PortfolioTruthPublishError(
                "Canonical security publication requires immutable receipt identity."
            )
        return
    if metadata is None:
        raise PortfolioTruthPublishError(
            "Security receipt binding requires PortfolioTruth input metadata."
        )
    if metadata.get("receipt_id") != binding.receipt_id:
        raise PortfolioTruthPublishError(
            "Security receipt_id metadata does not match the bound receipt."
        )
    if metadata.get("content_sha256") != binding.content_sha256:
        raise PortfolioTruthPublishError(
            "Security content_sha256 metadata does not match the bound receipt bytes."
        )
    if metadata.get("path") != binding.source_path:
        raise PortfolioTruthPublishError(
            "Security receipt path metadata does not match the bound receipt."
        )


def _stage_text(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=target.parent, suffix=f".{target.name}.tmp"
    ) as handle:
        handle.write(content)
        return Path(handle.name)


def _content_changed(path: Path, content: str) -> bool:
    if not path.exists():
        return True
    return path.read_text() != content


def _guard_against_notion_context_drop(
    source_summary: dict[str, object],
    *,
    latest_path: Path,
    include_notion: bool,
    allow_empty_notion: bool = False,
) -> None:
    """Avoid overwriting local truth when Notion bootstrap silently disappears."""
    if allow_empty_notion:
        # Operator explicitly opted into publishing without live Notion (a headless or
        # scheduled refresh); prior advisory is carried forward where available.
        return
    if not include_notion or not _notion_project_context_configured():
        return
    current_rows = _int_value(source_summary.get("notion_context_rows"))
    if current_rows != 0:
        return
    previous_rows = _previous_notion_context_rows(latest_path)
    if previous_rows is None or previous_rows <= 0:
        return
    raise PortfolioTruthPublishError(
        "Refusing to publish portfolio truth with 0 Notion context rows because "
        f"{latest_path} currently has {previous_rows}. Load NOTION_TOKEN or run "
        "with an explicit no-Notion path before replacing local portfolio truth."
    )


def _notion_project_context_configured() -> bool:
    path = _CONFIG_DIR / "notion-config.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(str(data.get("projects_data_source_id", "")).strip())


def _previous_notion_context_rows(latest_path: Path) -> int | None:
    try:
        data = json.loads(latest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    source_summary = data.get("source_summary", {})
    if not isinstance(source_summary, dict):
        return None
    return _int_value(source_summary.get("notion_context_rows"))


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
