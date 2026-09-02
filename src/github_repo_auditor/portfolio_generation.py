from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

MANIFEST_SCHEMA = "PortfolioGenerationManifestV1"
POINTER_SCHEMA = "PortfolioGenerationPointerV1"
CONTRACT_VERSION = "portfolio_generation_v1"
GENERATION_PREFIX = "portfolio-generation-"
MANIFEST_NAME = "manifest.json"
POINTER_NAME = "pointer.json"
LOCK_NAME = "writer.lock"
RELEASES_NAME = "releases"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GENERATION_RE = re.compile(r"^portfolio-generation-[0-9a-f]{16}$")


class PortfolioGenerationError(RuntimeError):
    """Raised when a coherent portfolio generation cannot be proven."""


@dataclass(frozen=True)
class ArtifactInput:
    name: str
    source: Path
    media_type: str
    contract_version: str


@dataclass(frozen=True)
class ProducerBinding:
    repository: str
    commit: str
    receipt_id: str
    receipt_sha256: str
    verified_at: str


@dataclass(frozen=True)
class SecurityBinding:
    schema_version: str
    receipt_id: str
    content_sha256: str
    produced_at: str
    evaluated_at: str
    valid_until: str
    max_age_hours: int
    producer_repository: str
    producer_commit: str
    state: str
    terminal_schema: str
    terminal_state: str
    terminal_content_sha256: str
    terminal_observed_at: str
    terminal_automation_id: str
    terminal_destination: str
    terminal_operator_commit: str
    terminal_controlled: bool


@dataclass(frozen=True)
class PublishedGeneration:
    generation_id: str
    manifest_sha256: str
    generation_dir: Path
    pointer_path: Path


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _parse_instant(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PortfolioGenerationError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioGenerationError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise PortfolioGenerationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _instant_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_regular(path: Path, *, label: str) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise PortfolioGenerationError(f"{label} is missing: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PortfolioGenerationError(f"{label} must be a regular non-symlink file")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PortfolioGenerationError(f"could not read {label}: {path}: {exc}") from exc


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular(path, label=label))
    except json.JSONDecodeError as exc:
        raise PortfolioGenerationError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PortfolioGenerationError(f"{label} must be a JSON object: {path}")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_fsynced(path: Path, content: bytes, *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if exclusive:
        flags |= os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _validate_artifact_name(name: str) -> None:
    if not name or Path(name).name != name or name in {".", "..", MANIFEST_NAME}:
        raise PortfolioGenerationError(f"invalid generation artifact name: {name!r}")


def _validate_generation_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not GENERATION_RE.fullmatch(value):
        raise PortfolioGenerationError(f"{field} is invalid")
    return value


def _validate_sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise PortfolioGenerationError(f"{field} is invalid")
    return value


def _crash_if_requested(step: str) -> None:
    if os.environ.get("PORTFOLIO_GENERATION_CRASH_AT") == step:
        os._exit(97)
    if os.environ.get("PORTFOLIO_GENERATION_FAIL_AT") == step:
        raise PortfolioGenerationError(f"injected publication failure at {step}")


@contextmanager
def writer_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / LOCK_NAME
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PortfolioGenerationError(
                f"portfolio generation writer lock is held: {lock_path}"
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def load_producer_binding(
    receipt_path: Path,
    *,
    repo_root: Path,
    expected_repository: str,
    expected_commit: str,
) -> ProducerBinding:
    from github_repo_auditor.producer_preflight import (
        load_producer_evidence,
        verify_evidence_still_current,
    )

    content = _read_regular(receipt_path, label="producer receipt")
    try:
        evidence = load_producer_evidence(receipt_path)
        verify_evidence_still_current(repo_root, evidence)
    except (OSError, TypeError, ValueError) as exc:
        raise PortfolioGenerationError(f"producer receipt is not current: {exc}") from exc
    if evidence.repository != expected_repository:
        raise PortfolioGenerationError(
            "producer receipt repository mismatch: "
            f"observed={evidence.repository}; expected={expected_repository}"
        )
    if evidence.commit != expected_commit:
        raise PortfolioGenerationError(
            "producer receipt commit mismatch: "
            f"observed={evidence.commit}; expected={expected_commit}"
        )
    return ProducerBinding(
        repository=evidence.repository,
        commit=evidence.commit,
        receipt_id=evidence.receipt_id,
        receipt_sha256=_sha256(content),
        verified_at=_instant_text(evidence.verified_at),
    )


def load_security_binding(
    receipt_path: Path,
    *,
    terminal_receipt_path: Path,
    expected_producer_commit: str,
    expected_operator_commit: str,
    max_age_hours: int,
    now: datetime,
) -> SecurityBinding:
    from github_repo_auditor.github_security_coverage import (
        SecurityCoverageError,
        load_security_coverage_receipt,
    )

    try:
        loaded = load_security_coverage_receipt(
            receipt_path,
            max_age_hours=max_age_hours,
            expected_cohort_count=None,
            expected_producer_commit=expected_producer_commit,
            require_cohort_transition=True,
            now=now,
        )
    except (OSError, SecurityCoverageError) as exc:
        raise PortfolioGenerationError(f"security receipt is not admissible: {exc}") from exc
    if loaded.receipt_state != "fresh":
        raise PortfolioGenerationError("security receipt is stale")
    if loaded.receipt_id is None or loaded.content_sha256 is None:
        raise PortfolioGenerationError("security receipt lacks immutable identity")
    produced_at = _parse_instant(loaded.produced_at, field="security produced_at")
    valid_until = produced_at + timedelta(hours=max_age_hours)
    producer_payload = _read_object(receipt_path, label="security receipt").get(
        "producer"
    )
    if not isinstance(producer_payload, dict):
        raise PortfolioGenerationError("security receipt producer is missing")
    repository = producer_payload.get("repository")
    if not isinstance(repository, str) or not repository:
        raise PortfolioGenerationError("security receipt producer repository is missing")
    terminal_bytes = _read_regular(
        terminal_receipt_path, label="security terminal receipt"
    )
    terminal = _read_object(
        terminal_receipt_path, label="security terminal receipt"
    )
    if (
        terminal.get("schema") != "AutomationTerminalStateV1"
        or terminal.get("state") != "succeeded"
        or terminal.get("completed") is not True
        or terminal.get("partial") is not False
        or terminal.get("exit_code") != 0
    ):
        raise PortfolioGenerationError("security terminal receipt is not successful")
    automation_id = terminal.get("automation_id")
    if automation_id not in {
        "com.d.github-security-coverage",
        "com.d.github-security-coverage.rehearsal",
    }:
        raise PortfolioGenerationError("security terminal automation identity is invalid")
    destination = terminal.get("destination_readback")
    if not isinstance(destination, dict) or destination.get("verified") is not True:
        raise PortfolioGenerationError("security terminal destination is not verified")
    expected_destination = str(receipt_path.resolve())
    if destination.get("destination_id") != expected_destination:
        raise PortfolioGenerationError("security terminal destination path mismatch")
    terminal_observed = _parse_instant(
        terminal.get("observed_at"), field="security terminal observed_at"
    )
    if terminal_observed < produced_at or terminal_observed > now.astimezone(UTC):
        raise PortfolioGenerationError("security terminal observation time is invalid")
    evidence = destination.get("evidence")
    if not isinstance(evidence, dict):
        raise PortfolioGenerationError("security terminal evidence is missing")
    if evidence.get("destination_sha256") != loaded.content_sha256:
        raise PortfolioGenerationError("security terminal content hash mismatch")
    if evidence.get("producer_commit") != expected_producer_commit:
        raise PortfolioGenerationError("security terminal producer commit mismatch")
    operator_generation = evidence.get("producer_generation")
    if (
        not isinstance(operator_generation, dict)
        or operator_generation.get("repository") != "saagpatel/operator-scripts"
        or operator_generation.get("commit") != expected_operator_commit
    ):
        raise PortfolioGenerationError("security terminal operator generation mismatch")
    invocation = terminal.get("invocation")
    dispatch = evidence.get("dispatch")
    controlled = (
        isinstance(dispatch, dict) and dispatch.get("dispatch_kind") == "controlled"
    )
    if not isinstance(invocation, dict):
        raise PortfolioGenerationError("security terminal invocation is missing")
    return SecurityBinding(
        schema_version=loaded.schema_version,
        receipt_id=loaded.receipt_id,
        content_sha256=loaded.content_sha256,
        produced_at=_instant_text(produced_at),
        evaluated_at=_instant_text(now),
        valid_until=_instant_text(valid_until),
        max_age_hours=max_age_hours,
        producer_repository=repository,
        producer_commit=loaded.producer_commit,
        state=loaded.receipt_state,
        terminal_schema="AutomationTerminalStateV1",
        terminal_state="succeeded",
        terminal_content_sha256=_sha256(terminal_bytes),
        terminal_observed_at=_instant_text(terminal_observed),
        terminal_automation_id=automation_id,
        terminal_destination=expected_destination,
        terminal_operator_commit=expected_operator_commit,
        terminal_controlled=controlled,
    )


def _artifact_records(artifacts: Sequence[ArtifactInput]) -> tuple[dict[str, Any], ...]:
    if not artifacts:
        raise PortfolioGenerationError("at least one generation artifact is required")
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for artifact in artifacts:
        _validate_artifact_name(artifact.name)
        if artifact.name in seen:
            raise PortfolioGenerationError(f"duplicate artifact name: {artifact.name}")
        seen.add(artifact.name)
        content = _read_regular(artifact.source, label=f"artifact {artifact.name}")
        records.append(
            {
                "name": artifact.name,
                "path": artifact.name,
                "sha256": _sha256(content),
                "size_bytes": len(content),
                "media_type": artifact.media_type,
                "contract_version": artifact.contract_version,
            }
        )
    return tuple(sorted(records, key=lambda item: item["name"]))


def _manifest_core(
    *,
    artifacts: tuple[dict[str, Any], ...],
    producer: ProducerBinding,
    security: SecurityBinding,
    created_at: datetime,
    prior_generation: str | None,
) -> dict[str, Any]:
    if security.state != "fresh":
        raise PortfolioGenerationError("security binding must be fresh")
    if security.producer_commit != producer.commit:
        raise PortfolioGenerationError("security and producer commits disagree")
    if security.producer_repository != producer.repository:
        raise PortfolioGenerationError("security and producer repositories disagree")
    evaluated = _parse_instant(security.evaluated_at, field="security evaluated_at")
    valid_until = _parse_instant(security.valid_until, field="security valid_until")
    if evaluated > valid_until or created_at.astimezone(UTC) > valid_until:
        raise PortfolioGenerationError("security binding expired before publication")
    if prior_generation is not None:
        _validate_generation_id(prior_generation, field="prior_generation")
    return {
        "schema_version": MANIFEST_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "created_at": _instant_text(created_at),
        "prior_generation": prior_generation,
        "artifacts": list(artifacts),
        "producer": {
            "repository": producer.repository,
            "commit": producer.commit,
            "receipt_id": producer.receipt_id,
            "receipt_sha256": producer.receipt_sha256,
            "verified_at": producer.verified_at,
        },
        "github_security": {
            "schema_version": security.schema_version,
            "receipt_id": security.receipt_id,
            "content_sha256": security.content_sha256,
            "produced_at": security.produced_at,
            "evaluated_at": security.evaluated_at,
            "valid_until": security.valid_until,
            "max_age_hours": security.max_age_hours,
            "state": security.state,
            "producer_repository": security.producer_repository,
            "producer_commit": security.producer_commit,
            "terminal_receipt": {
                "schema": security.terminal_schema,
                "state": security.terminal_state,
                "content_sha256": security.terminal_content_sha256,
                "observed_at": security.terminal_observed_at,
                "automation_id": security.terminal_automation_id,
                "destination": security.terminal_destination,
                "operator_commit": security.terminal_operator_commit,
                "controlled": security.terminal_controlled,
            },
        },
    }


def verify_generation_dir(
    generation_dir: Path,
    *,
    expected_generation_id: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    manifest_path = generation_dir / MANIFEST_NAME
    manifest_bytes = _read_regular(manifest_path, label="generation manifest")
    manifest_sha256 = _sha256(manifest_bytes)
    if expected_manifest_sha256 is not None and manifest_sha256 != _validate_sha256(
        expected_manifest_sha256, field="expected manifest sha256"
    ):
        raise PortfolioGenerationError("generation manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise PortfolioGenerationError("generation manifest is invalid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise PortfolioGenerationError("generation manifest schema mismatch")
    if set(manifest) != {
        "schema_version",
        "contract_version",
        "generation_id",
        "content_identity_sha256",
        "created_at",
        "prior_generation",
        "artifacts",
        "producer",
        "github_security",
    }:
        raise PortfolioGenerationError("generation manifest fields are invalid")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise PortfolioGenerationError("generation manifest contract mismatch")
    generation_id = _validate_generation_id(
        manifest.get("generation_id"), field="manifest generation_id"
    )
    if expected_generation_id is not None and generation_id != expected_generation_id:
        raise PortfolioGenerationError("generation id mismatch")
    if generation_dir.name != generation_id:
        raise PortfolioGenerationError("generation directory identity mismatch")
    core = {key: value for key, value in manifest.items() if key not in {"generation_id", "content_identity_sha256"}}
    identity = _sha256(_canonical_bytes(core))
    if manifest.get("content_identity_sha256") != identity:
        raise PortfolioGenerationError("generation content identity mismatch")
    if generation_id != f"{GENERATION_PREFIX}{identity[:16]}":
        raise PortfolioGenerationError("generation id is not content-derived")
    records = manifest.get("artifacts")
    if not isinstance(records, list) or not records:
        raise PortfolioGenerationError("generation manifest artifacts are missing")
    names: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise PortfolioGenerationError(f"artifact[{index}] is invalid")
        if set(record) != {
            "name",
            "path",
            "sha256",
            "size_bytes",
            "media_type",
            "contract_version",
        }:
            raise PortfolioGenerationError(f"artifact[{index}] fields are invalid")
        name = record.get("name")
        if not isinstance(name, str):
            raise PortfolioGenerationError(f"artifact[{index}] name is invalid")
        _validate_artifact_name(name)
        if name in names or record.get("path") != name:
            raise PortfolioGenerationError("artifact names or paths are contradictory")
        names.add(name)
        content = _read_regular(generation_dir / name, label=f"artifact {name}")
        if len(content) != record.get("size_bytes"):
            raise PortfolioGenerationError(f"artifact size mismatch: {name}")
        if _sha256(content) != _validate_sha256(record.get("sha256"), field=f"artifact {name} sha256"):
            raise PortfolioGenerationError(f"artifact hash mismatch: {name}")
    return manifest, manifest_sha256


def _pointer_entry(value: object, *, field: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PortfolioGenerationError(f"pointer {field} is invalid")
    return {
        "generation_id": _validate_generation_id(
            value.get("generation_id"), field=f"pointer {field} generation_id"
        ),
        "manifest_sha256": _validate_sha256(
            value.get("manifest_sha256"), field=f"pointer {field} manifest_sha256"
        ),
    }


def read_pointer(root: Path, *, validate_generations: bool = True) -> dict[str, Any]:
    payload = _read_object(root / POINTER_NAME, label="portfolio generation pointer")
    if set(payload) != {"schema_version", "current", "previous", "updated_at"}:
        raise PortfolioGenerationError("portfolio generation pointer fields are invalid")
    if payload.get("schema_version") != POINTER_SCHEMA:
        raise PortfolioGenerationError("portfolio generation pointer schema mismatch")
    current = _pointer_entry(payload.get("current"), field="current")
    previous = _pointer_entry(payload.get("previous"), field="previous")
    if current is None:
        raise PortfolioGenerationError("portfolio generation pointer has no current")
    if previous is not None and previous == current:
        raise PortfolioGenerationError("current and previous pointer entries are identical")
    _parse_instant(payload.get("updated_at"), field="pointer updated_at")
    normalized = {
        "schema_version": POINTER_SCHEMA,
        "current": current,
        "previous": previous,
        "updated_at": payload["updated_at"],
    }
    if validate_generations:
        for field, entry in (("current", current), ("previous", previous)):
            if entry is None:
                continue
            verify_generation_dir(
                root / RELEASES_NAME / entry["generation_id"],
                expected_generation_id=entry["generation_id"],
                expected_manifest_sha256=entry["manifest_sha256"],
            )
    return normalized


def resolve_current(root: Path) -> PublishedGeneration:
    pointer = read_pointer(root, validate_generations=True)
    current = pointer["current"]
    return PublishedGeneration(
        generation_id=current["generation_id"],
        manifest_sha256=current["manifest_sha256"],
        generation_dir=root / RELEASES_NAME / current["generation_id"],
        pointer_path=root / POINTER_NAME,
    )


def publish_generation(
    *,
    root: Path,
    artifacts: Sequence[ArtifactInput],
    producer: ProducerBinding,
    security: SecurityBinding,
    created_at: datetime | None = None,
    pre_pointer_check: Callable[[], None] | None = None,
) -> PublishedGeneration:
    created = (created_at or datetime.now(UTC)).astimezone(UTC)
    records = _artifact_records(artifacts)
    root = root.resolve()
    releases = root / RELEASES_NAME
    with writer_lock(root):
        _crash_if_requested("after_lock")
        prior_pointer: dict[str, Any] | None = None
        if (root / POINTER_NAME).exists():
            prior_pointer = read_pointer(root, validate_generations=True)
        prior_generation = (
            prior_pointer["current"]["generation_id"] if prior_pointer else None
        )
        core = _manifest_core(
            artifacts=records,
            producer=producer,
            security=security,
            created_at=created,
            prior_generation=prior_generation,
        )
        identity = _sha256(_canonical_bytes(core))
        generation_id = f"{GENERATION_PREFIX}{identity[:16]}"
        manifest = {
            **core,
            "generation_id": generation_id,
            "content_identity_sha256": identity,
        }
        manifest_bytes = _canonical_bytes(manifest)
        manifest_sha256 = _sha256(manifest_bytes)
        releases.mkdir(parents=True, exist_ok=True)
        stage_parent = Path(
            tempfile.mkdtemp(prefix=".portfolio-generation-stage-", dir=root)
        )
        stage = stage_parent / generation_id
        stage.mkdir()
        _crash_if_requested("after_stage_created")
        try:
            sources = {artifact.name: artifact.source for artifact in artifacts}
            for record in records:
                content = _read_regular(sources[record["name"]], label=f"artifact {record['name']}")
                if _sha256(content) != record["sha256"]:
                    raise PortfolioGenerationError(
                        f"artifact changed after admission: {record['name']}"
                    )
                _write_fsynced(stage / record["name"], content, exclusive=True)
            _fsync_directory(stage)
            _crash_if_requested("after_artifacts_written")
            _write_fsynced(stage / MANIFEST_NAME, manifest_bytes, exclusive=True)
            _fsync_directory(stage)
            _crash_if_requested("after_manifest_written")
            verify_generation_dir(
                stage,
                expected_generation_id=generation_id,
                expected_manifest_sha256=manifest_sha256,
            )
            _crash_if_requested("after_stage_validated")
            generation_dir = releases / generation_id
            if generation_dir.exists():
                verify_generation_dir(
                    generation_dir,
                    expected_generation_id=generation_id,
                    expected_manifest_sha256=manifest_sha256,
                )
                shutil.rmtree(stage)
            else:
                os.replace(stage, generation_dir)
                _fsync_directory(releases)
            _crash_if_requested("after_generation_visible")
            if pre_pointer_check is not None:
                pre_pointer_check()
            current_entry = {
                "generation_id": generation_id,
                "manifest_sha256": manifest_sha256,
            }
            previous_entry = prior_pointer["current"] if prior_pointer else None
            if previous_entry == current_entry:
                previous_entry = prior_pointer.get("previous") if prior_pointer else None
            pointer = {
                "schema_version": POINTER_SCHEMA,
                "current": current_entry,
                "previous": previous_entry,
                "updated_at": _instant_text(created),
            }
            pointer_path = root / POINTER_NAME
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{POINTER_NAME}.", suffix=".tmp", dir=root
            )
            temporary_path = Path(temporary)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(_canonical_bytes(pointer))
                    handle.flush()
                    os.fsync(handle.fileno())
                _crash_if_requested("after_pointer_staged")
                os.replace(temporary_path, pointer_path)
                _fsync_directory(root)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
            _crash_if_requested("after_pointer_replaced")
            resolved = resolve_current(root)
            if resolved.generation_id != generation_id:
                raise PortfolioGenerationError("portfolio generation pointer readback mismatch")
            _crash_if_requested("after_readback")
            return resolved
        finally:
            if stage.exists():
                shutil.rmtree(stage)
            if stage_parent.exists():
                stage_parent.rmdir()


def swap_current_previous(root: Path, *, updated_at: datetime | None = None) -> dict[str, Any]:
    with writer_lock(root):
        pointer = read_pointer(root, validate_generations=True)
        if pointer["previous"] is None:
            raise PortfolioGenerationError("no previous portfolio generation is available")
        swapped = {
            "schema_version": POINTER_SCHEMA,
            "current": pointer["previous"],
            "previous": pointer["current"],
            "updated_at": _instant_text(updated_at or datetime.now(UTC)),
        }
        _atomic_json(root / POINTER_NAME, swapped)
        readback = read_pointer(root, validate_generations=True)
        if readback["current"] != swapped["current"] or readback["previous"] != swapped["previous"]:
            raise PortfolioGenerationError("portfolio generation rollback readback mismatch")
        return readback


def _artifact_argument(value: str) -> ArtifactInput:
    parts = value.split("=", 3)
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "artifact must be NAME=PATH=MEDIA_TYPE=CONTRACT_VERSION"
        )
    return ArtifactInput(parts[0], Path(parts[1]), parts[2], parts[3])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage coherent portfolio generations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--root", type=Path, required=True)
    publish.add_argument("--artifact", action="append", type=_artifact_argument, required=True)
    publish.add_argument("--producer-receipt", type=Path, required=True)
    publish.add_argument("--producer-repo-root", type=Path, required=True)
    publish.add_argument("--expected-repository", required=True)
    publish.add_argument("--expected-commit", required=True)
    publish.add_argument("--security-receipt", type=Path, required=True)
    publish.add_argument("--security-terminal-receipt", type=Path, required=True)
    publish.add_argument("--expected-operator-commit", required=True)
    publish.add_argument("--security-max-age-hours", type=int, default=1)
    publish.add_argument("--created-at")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    swap = subparsers.add_parser("swap-current-previous")
    swap.add_argument("--root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "publish":
            created = (
                _parse_instant(args.created_at, field="created_at")
                if args.created_at
                else datetime.now(UTC)
            )
            producer = load_producer_binding(
                args.producer_receipt,
                repo_root=args.producer_repo_root,
                expected_repository=args.expected_repository,
                expected_commit=args.expected_commit,
            )
            security = load_security_binding(
                args.security_receipt,
                terminal_receipt_path=args.security_terminal_receipt,
                expected_producer_commit=args.expected_commit,
                expected_operator_commit=args.expected_operator_commit,
                max_age_hours=args.security_max_age_hours,
                now=created,
            )

            def pre_pointer_check() -> None:
                current_producer = load_producer_binding(
                    args.producer_receipt,
                    repo_root=args.producer_repo_root,
                    expected_repository=args.expected_repository,
                    expected_commit=args.expected_commit,
                )
                current_security = load_security_binding(
                    args.security_receipt,
                    terminal_receipt_path=args.security_terminal_receipt,
                    expected_producer_commit=args.expected_commit,
                    expected_operator_commit=args.expected_operator_commit,
                    max_age_hours=args.security_max_age_hours,
                    now=datetime.now(UTC),
                )
                if current_producer != producer:
                    raise PortfolioGenerationError(
                        "producer receipt changed before pointer publication"
                    )
                if (
                    current_security.receipt_id != security.receipt_id
                    or current_security.content_sha256 != security.content_sha256
                    or current_security.producer_commit != security.producer_commit
                    or current_security.terminal_content_sha256
                    != security.terminal_content_sha256
                ):
                    raise PortfolioGenerationError(
                        "security receipt changed before pointer publication"
                    )

            result = publish_generation(
                root=args.root,
                artifacts=args.artifact,
                producer=producer,
                security=security,
                created_at=created,
                pre_pointer_check=pre_pointer_check,
            )
            print(json.dumps(result.__dict__, default=str, sort_keys=True))
        elif args.command == "verify":
            print(json.dumps(resolve_current(args.root).__dict__, default=str, sort_keys=True))
        else:
            print(json.dumps(swap_current_previous(args.root), sort_keys=True))
    except PortfolioGenerationError as exc:
        print(f"portfolio generation refused: {exc}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
