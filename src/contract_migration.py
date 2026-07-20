from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

DESCRIPTOR_SCHEMA_VERSION = "ContractDescriptorV1"
GRAPH_SCHEMA_VERSION = "ContractGraphV1"
PLAN_SCHEMA_VERSION = "MigrationPlanV1"

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_RANGE_RE = re.compile(
    r"^>=(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*) "
    r"<(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.-]+$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_FORBIDDEN_COMMAND_TOKENS = (
    "\n",
    "\r",
    ";",
    "|",
    "&",
    ">",
    "<",
    "`",
    "$",
    "\\",
    "../",
    "/tmp/",
    "/Users/",
)
_ALLOWED_COMMANDS = {"uv", "pnpm", "cargo", "node"}
_ALLOWED_PNPM_SCRIPTS = {"build", "test", "typecheck"}
_SECRET_TEXT_RE = re.compile(
    r"(?:api[_-]?key|credential|password|secret|token)",
    re.IGNORECASE,
)
_FORBIDDEN_SECRET_KEYS = {
    "api_key",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}
_FORBIDDEN_SECRET_PATH_PARTS = {".env", "credentials", "keychain"}

_REQUIRED_FIELDS = {
    "schema_version",
    "contract_id",
    "repository",
    "role",
    "producer",
    "consumer",
    "current_version",
    "target_version",
    "accepted_version_range",
    "compatibility",
    "expected_consumers",
    "evidence",
    "adapter",
    "verifier",
    "rollback",
}


class ContractMigrationError(ValueError):
    """A fail-closed contract or repository authority violation."""


@dataclass(frozen=True)
class RepositoryObservation:
    repository_path: str
    branch: str
    head: str
    descriptor_path: str
    descriptor_sha256: str
    descriptor: dict[str, Any]

    def binding(self) -> dict[str, str]:
        return {
            "repository": str(self.descriptor["repository"]),
            "repository_path": self.repository_path,
            "branch": self.branch,
            "head": self.head,
            "descriptor_path": self.descriptor_path,
            "descriptor_sha256": self.descriptor_sha256,
        }


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    return completed.stdout.strip()


def _semver(value: object, *, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ContractMigrationError(f"{field} must be a semantic-version string")
    match = _SEMVER_RE.fullmatch(value)
    if not match:
        raise ContractMigrationError(f"{field} is not strict semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def _range_accepts(version: str, accepted_range: str) -> bool:
    match = _RANGE_RE.fullmatch(accepted_range)
    if not match:
        raise ContractMigrationError(
            "accepted_version_range must use the bounded form >=x.y.z <x.y.z"
        )
    lower = tuple(int(part) for part in match.groups()[:3])
    upper = tuple(int(part) for part in match.groups()[3:])
    parsed = _semver(version, field="version")
    return lower <= parsed < upper


def _validate_relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractMigrationError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or value.startswith(("-", "~"))
        or any(character in value for character in ("*", "?", "[", "]"))
    ):
        raise ContractMigrationError(f"{field} escapes the repository: {value}")
    if any(part.lower() in _FORBIDDEN_SECRET_PATH_PARTS for part in path.parts):
        raise ContractMigrationError(f"{field} targets secret-bearing state: {value}")
    return value


def _validate_verifier_command(command: object) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ContractMigrationError("verifier commands must be non-empty strings")
    if any(token in command for token in _FORBIDDEN_COMMAND_TOKENS):
        raise ContractMigrationError(f"verifier command escapes bounded execution: {command}")
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ContractMigrationError("verifier command has malformed quoting") from exc
    if not tokens:
        raise ContractMigrationError("verifier commands must be non-empty strings")
    if any(_SECRET_TEXT_RE.search(token) for token in tokens):
        raise ContractMigrationError("verifier command includes secret-bearing arguments")
    executable = tokens[0]
    if executable not in _ALLOWED_COMMANDS:
        raise ContractMigrationError(
            f"verifier command uses an unapproved executable: {executable}"
        )
    if executable == "uv":
        _validate_uv_verifier(tokens)
    elif executable == "pnpm":
        _validate_pnpm_verifier(tokens)
    elif executable == "cargo":
        _validate_cargo_verifier(tokens)
    else:
        _validate_node_verifier(tokens)
    return command


def _validate_verifier_path(value: str, *, field: str) -> None:
    path_part = value.split("::", 1)[0]
    _validate_relative_path(path_part, field=field)


def _validate_uv_verifier(tokens: list[str]) -> None:
    if len(tokens) < 4 or tokens[1] != "run":
        raise ContractMigrationError("uv verifier must use `uv run`")
    index = 2
    while index < len(tokens) and tokens[index] == "--extra":
        if index + 1 >= len(tokens) or not _IDENTIFIER_RE.fullmatch(tokens[index + 1]):
            raise ContractMigrationError("uv verifier has an invalid --extra value")
        index += 2
    if index >= len(tokens):
        raise ContractMigrationError("uv verifier is missing its bounded tool")
    tool = tokens[index]
    arguments = tokens[index + 1 :]
    if tool == "ruff":
        if not arguments or arguments[0] != "check":
            raise ContractMigrationError("ruff verifier must use `ruff check`")
        paths = arguments[1:]
    elif tool == "pytest":
        paths = []
        for argument in arguments:
            if argument in {"-q", "--quiet"}:
                continue
            if argument.startswith("-"):
                raise ContractMigrationError("pytest verifier uses an unapproved option")
            paths.append(argument)
    else:
        raise ContractMigrationError(f"uv verifier tool is not approved: {tool}")
    if not paths:
        raise ContractMigrationError(f"{tool} verifier must name tracked targets")
    for path in paths:
        _validate_verifier_path(path, field=f"{tool} verifier target")


def _validate_pnpm_verifier(tokens: list[str]) -> None:
    if len(tokens) == 2 and tokens[1] in _ALLOWED_PNPM_SCRIPTS:
        return
    if (
        len(tokens) == 5
        and tokens[1] == "--dir"
        and tokens[3] == "run"
        and tokens[4] in _ALLOWED_PNPM_SCRIPTS
    ):
        _validate_relative_path(tokens[2], field="pnpm --dir")
        return
    raise ContractMigrationError("pnpm verifier must run a bounded repository script")


def _validate_cargo_verifier(tokens: list[str]) -> None:
    if tokens == ["cargo", "check"]:
        return
    if (
        len(tokens) == 4
        and tokens[1:3] == ["check", "--manifest-path"]
    ):
        _validate_relative_path(tokens[3], field="cargo manifest")
        if Path(tokens[3]).name != "Cargo.toml":
            raise ContractMigrationError("cargo verifier must target Cargo.toml")
        return
    raise ContractMigrationError("cargo verifier must use bounded `cargo check`")


def _validate_node_verifier(tokens: list[str]) -> None:
    if len(tokens) < 3 or tokens[1] != "--test":
        raise ContractMigrationError("node verifier must use `node --test`")
    for path in tokens[2:]:
        _validate_verifier_path(path, field="node test target")
        if Path(path.split("::", 1)[0]).suffix != ".js":
            raise ContractMigrationError("node verifier targets must be JavaScript tests")


def _reject_secret_fields(value: object, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in _FORBIDDEN_SECRET_KEYS:
                location = ".".join((*path, key))
                raise ContractMigrationError(
                    f"descriptor includes forbidden secret field: {location}"
                )
            _reject_secret_fields(nested, path=(*path, key))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secret_fields(nested, path=(*path, str(index)))


def validate_descriptor(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractMigrationError("descriptor root must be an object")
    _reject_secret_fields(payload)
    missing = sorted(_REQUIRED_FIELDS - payload.keys())
    extra = sorted(payload.keys() - _REQUIRED_FIELDS)
    if missing:
        raise ContractMigrationError(f"descriptor is missing fields: {missing}")
    if extra:
        raise ContractMigrationError(f"descriptor has unexpected fields: {extra}")
    if payload["schema_version"] != DESCRIPTOR_SCHEMA_VERSION:
        raise ContractMigrationError("descriptor schema_version is not pinned to v1")
    contract_id = payload["contract_id"]
    if not isinstance(contract_id, str) or not _IDENTIFIER_RE.fullmatch(contract_id):
        raise ContractMigrationError("contract_id is malformed")
    for field in ("repository", "producer"):
        value = payload[field]
        if not isinstance(value, str) or not _REPOSITORY_RE.fullmatch(value):
            raise ContractMigrationError(f"{field} is malformed")

    role = payload["role"]
    if role not in {"producer", "consumer"}:
        raise ContractMigrationError("role must be producer or consumer")
    current = _semver(payload["current_version"], field="current_version")
    target = _semver(payload["target_version"], field="target_version")
    if target <= current:
        raise ContractMigrationError("target_version must be newer than current_version")
    if payload["compatibility"] not in {"additive", "breaking"}:
        raise ContractMigrationError("compatibility must be additive or breaking")
    if payload["evidence"] != "declared-static":
        raise ContractMigrationError(
            "consumer access is dynamic or hidden; affected-edge state is UNKNOWN"
        )

    expected_consumers = payload["expected_consumers"]
    if not isinstance(expected_consumers, list) or not all(
        isinstance(item, str) and _REPOSITORY_RE.fullmatch(item)
        for item in expected_consumers
    ):
        raise ContractMigrationError("expected_consumers must be repository identities")
    if len(set(expected_consumers)) != len(expected_consumers):
        raise ContractMigrationError("expected_consumers contains duplicates")

    consumer = payload["consumer"]
    accepted_range = payload["accepted_version_range"]
    if role == "producer":
        if payload["repository"] != payload["producer"]:
            raise ContractMigrationError("producer descriptor repository must own the contract")
        if consumer is not None or accepted_range is not None:
            raise ContractMigrationError(
                "producer descriptor cannot declare consumer compatibility"
            )
        if not expected_consumers:
            raise ContractMigrationError("producer must declare expected consumers")
        if payload["rollback"] != {
            "strategy": "producer-first",
            "version": payload["current_version"],
        }:
            raise ContractMigrationError("producer rollback must restore current version first")
    else:
        if consumer != payload["repository"]:
            raise ContractMigrationError("consumer descriptor must name its own repository")
        if expected_consumers:
            raise ContractMigrationError(
                "consumer descriptor cannot declare expected consumers"
            )
        if not isinstance(accepted_range, str):
            raise ContractMigrationError(
                "consumer must declare an accepted_version_range"
            )
        if not _range_accepts(payload["current_version"], accepted_range):
            raise ContractMigrationError("consumer range rejects current producer version")
        if not _range_accepts(payload["target_version"], accepted_range):
            raise ContractMigrationError("consumer range rejects target producer version")
        if payload["rollback"] != {
            "strategy": "consumer-remains-dual-read",
            "version": payload["current_version"],
        }:
            raise ContractMigrationError(
                "consumer rollback must preserve old-version dual-read"
            )

    adapter = payload["adapter"]
    if not isinstance(adapter, dict) or set(adapter) != {"id", "patch_paths"}:
        raise ContractMigrationError("adapter must contain only id and patch_paths")
    adapter_id = adapter["id"]
    if not isinstance(adapter_id, str) or not _IDENTIFIER_RE.fullmatch(adapter_id):
        raise ContractMigrationError("adapter id is malformed")
    patch_paths = adapter["patch_paths"]
    if not isinstance(patch_paths, list) or not patch_paths:
        raise ContractMigrationError("adapter patch_paths cannot be empty")
    normalized_paths = [
        _validate_relative_path(path, field="adapter.patch_paths")
        for path in patch_paths
    ]
    if len(set(normalized_paths)) != len(normalized_paths):
        raise ContractMigrationError("adapter patch_paths contains duplicates")

    verifier = payload["verifier"]
    if not isinstance(verifier, dict) or set(verifier) != {"commands"}:
        raise ContractMigrationError("verifier must contain only commands")
    commands = verifier["commands"]
    if not isinstance(commands, list) or not commands:
        raise ContractMigrationError("verifier commands cannot be empty")
    validated_commands = [_validate_verifier_command(command) for command in commands]
    if len(set(validated_commands)) != len(validated_commands):
        raise ContractMigrationError("verifier commands contains duplicates")

    rollback = payload["rollback"]
    if not isinstance(rollback, dict) or set(rollback) != {"strategy", "version"}:
        raise ContractMigrationError("rollback must contain only strategy and version")
    _semver(rollback["version"], field="rollback.version")
    return payload


def _descriptor_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ContractMigrationError(f"descriptor is unavailable: {path}") from exc


def _verify_tracked_repository_file(
    root: Path,
    relative_path: str,
    *,
    field: str,
) -> None:
    candidate = root
    for part in Path(relative_path).parts:
        candidate /= part
        if candidate.is_symlink():
            raise ContractMigrationError(f"{field} cannot be a symlink: {relative_path}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ContractMigrationError(
            f"{field} escapes or is absent from repository: {relative_path}"
        ) from exc
    if not resolved.is_file():
        raise ContractMigrationError(f"{field} is not a file: {relative_path}")
    try:
        _git(root, "ls-files", "--error-unmatch", relative_path)
    except subprocess.CalledProcessError as exc:
        raise ContractMigrationError(
            f"{field} is not tracked by Git: {relative_path}"
        ) from exc


def observe_repository(
    repo_root: Path,
    descriptor_path: Path,
    *,
    expected_head: str | None = None,
) -> RepositoryObservation:
    root = repo_root.resolve()
    descriptor = descriptor_path
    if descriptor.is_symlink():
        raise ContractMigrationError(f"descriptor cannot be a symlink: {descriptor}")
    try:
        resolved_descriptor = descriptor.resolve(strict=True)
        relative_descriptor = resolved_descriptor.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ContractMigrationError(
            f"descriptor escapes or is absent from repository: {descriptor}"
        ) from exc

    actual_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if actual_root != root:
        raise ContractMigrationError(
            f"repository root mismatch: expected={root}; actual={actual_root}"
        )
    head = _git(root, "rev-parse", "HEAD")
    if expected_head is not None and head != expected_head:
        raise ContractMigrationError(
            f"repository HEAD changed: expected={expected_head}; actual={head}"
        )
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ContractMigrationError(f"repository worktree is dirty: {root}")
    try:
        _git(root, "ls-files", "--error-unmatch", relative_descriptor.as_posix())
    except subprocess.CalledProcessError as exc:
        raise ContractMigrationError(
            f"descriptor is not tracked by Git: {relative_descriptor}"
        ) from exc

    raw = _descriptor_bytes(resolved_descriptor)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractMigrationError(f"descriptor is malformed JSON: {descriptor}") from exc
    validated = validate_descriptor(payload)
    for adapter_path in validated["adapter"]["patch_paths"]:
        _verify_tracked_repository_file(
            root,
            adapter_path,
            field="adapter patch path",
        )
    branch = _git(root, "branch", "--show-current") or "DETACHED"
    return RepositoryObservation(
        repository_path=str(root),
        branch=branch,
        head=head,
        descriptor_path=relative_descriptor.as_posix(),
        descriptor_sha256=hashlib.sha256(raw).hexdigest(),
        descriptor=validated,
    )


def _unknown_plan(
    *,
    contract_id: str,
    inspected_at: str,
    findings: Iterable[str],
    contract_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_findings = sorted(set(findings))
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "state": "unknown",
        "contract_id": contract_id,
        "inspected_at": inspected_at,
        "patch_preparation_allowed": False,
        "findings": normalized_findings,
        "contract_graph": contract_graph
        or {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "state": "unknown",
            "contract_id": contract_id,
            "inspected_at": inspected_at,
            "findings": normalized_findings,
            "producer": None,
            "expected_consumers": [],
            "consumers": [],
            "edges": [],
        },
        "bindings": [],
        "steps": [],
        "rollback": [],
        "cleanup": "deferred",
    }
    return _with_fingerprint(plan)


def _with_fingerprint(plan: dict[str, Any]) -> dict[str, Any]:
    material = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return {**plan, "plan_fingerprint": f"sha256:{hashlib.sha256(material).hexdigest()}"}


def _validate_inspected_at(inspected_at: str) -> None:
    try:
        parsed_time = datetime.fromisoformat(inspected_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractMigrationError("inspected_at must be an ISO-8601 timestamp") from exc
    if parsed_time.tzinfo is None:
        raise ContractMigrationError("inspected_at must include a timezone")


def _contract_graph_payload(
    graph: dict[str, Any],
    *,
    inspected_at: str,
) -> dict[str, Any]:
    producer: RepositoryObservation | None = graph["producer"]
    consumers: list[RepositoryObservation] = graph["consumers"]
    expected_consumers = (
        list(producer.descriptor["expected_consumers"]) if producer else []
    )
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "state": graph["state"],
        "contract_id": graph["contract_id"],
        "inspected_at": inspected_at,
        "findings": sorted(set(graph["findings"])),
        "producer": producer.binding() if producer else None,
        "expected_consumers": expected_consumers,
        "consumers": [consumer.binding() for consumer in consumers],
        "edges": [
            {
                "producer": producer.descriptor["repository"],
                "consumer": consumer.descriptor["repository"],
                "accepted_version_range": consumer.descriptor[
                    "accepted_version_range"
                ],
                "compatibility": consumer.descriptor["compatibility"],
                "consumer_binding": consumer.binding(),
            }
            for consumer in consumers
        ]
        if producer
        else [],
    }


def build_contract_graph(
    observations: Sequence[RepositoryObservation],
    *,
    contract_id: str,
) -> dict[str, Any]:
    relevant = [
        observation
        for observation in observations
        if observation.descriptor["contract_id"] == contract_id
    ]
    findings: list[str] = []
    producers = [
        observation
        for observation in relevant
        if observation.descriptor["role"] == "producer"
    ]
    consumers = [
        observation
        for observation in relevant
        if observation.descriptor["role"] == "consumer"
    ]
    if len(producers) != 1:
        findings.append(f"expected exactly one producer, observed {len(producers)}")
    if len(producers) == 1:
        producer = producers[0].descriptor
        expected = list(producer["expected_consumers"])
        observed = [str(item.descriptor["repository"]) for item in consumers]
        missing = [repository for repository in expected if repository not in observed]
        unexpected = [repository for repository in observed if repository not in expected]
        if missing:
            findings.append(f"missing declared consumers: {missing}")
        if unexpected:
            findings.append(f"unexpected consumers: {unexpected}")
        if len(observed) != len(set(observed)):
            findings.append("duplicate consumer descriptors")
        for consumer_observation in consumers:
            consumer = consumer_observation.descriptor
            if consumer["producer"] != producer["repository"]:
                findings.append(
                    f"{consumer['repository']} names the wrong producer"
                )
            if consumer["current_version"] != producer["current_version"]:
                findings.append(
                    f"{consumer['repository']} descriptor is stale: "
                    f"{consumer['current_version']} != {producer['current_version']}"
                )
            if consumer["target_version"] != producer["target_version"]:
                findings.append(
                    f"{consumer['repository']} target version conflicts with producer"
                )
            if consumer["compatibility"] != producer["compatibility"]:
                findings.append(
                    f"{consumer['repository']} compatibility conflicts with producer"
                )

    ordered_consumers: list[RepositoryObservation] = []
    if len(producers) == 1:
        expected = list(producers[0].descriptor["expected_consumers"])
        for repository in expected:
            ordered_consumers.extend(
                sorted(
                    (
                        observation
                        for observation in consumers
                        if observation.descriptor["repository"] == repository
                    ),
                    key=lambda observation: (
                        observation.repository_path,
                        observation.descriptor_sha256,
                    ),
                )
            )
        ordered_consumers.extend(
            sorted(
                (
                    observation
                    for observation in consumers
                    if observation.descriptor["repository"] not in expected
                ),
                key=lambda observation: (
                    str(observation.descriptor["repository"]),
                    observation.repository_path,
                    observation.descriptor_sha256,
                ),
            )
        )
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "state": "unknown" if findings else "pass",
        "contract_id": contract_id,
        "findings": findings,
        "producer": producers[0] if len(producers) == 1 else None,
        "consumers": ordered_consumers,
    }


def build_migration_plan(
    graph: dict[str, Any],
    *,
    inspected_at: str,
) -> dict[str, Any]:
    _validate_inspected_at(inspected_at)
    contract_graph = _contract_graph_payload(graph, inspected_at=inspected_at)
    if graph["state"] != "pass":
        return _unknown_plan(
            contract_id=str(graph["contract_id"]),
            inspected_at=inspected_at,
            findings=graph["findings"],
            contract_graph=contract_graph,
        )

    producer: RepositoryObservation = graph["producer"]
    consumers: list[RepositoryObservation] = graph["consumers"]
    steps = [
        {
            "order": index,
            "repository": observation.descriptor["repository"],
            "role": "consumer",
            "adapter": observation.descriptor["adapter"]["id"],
            "patch_paths": observation.descriptor["adapter"]["patch_paths"],
            "verifier": observation.descriptor["verifier"]["commands"],
        }
        for index, observation in enumerate(consumers, start=1)
    ]
    steps.append(
        {
            "order": len(steps) + 1,
            "repository": producer.descriptor["repository"],
            "role": "producer",
            "adapter": producer.descriptor["adapter"]["id"],
            "patch_paths": producer.descriptor["adapter"]["patch_paths"],
            "verifier": producer.descriptor["verifier"]["commands"],
        }
    )
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "state": "pass",
        "contract_id": graph["contract_id"],
        "current_version": producer.descriptor["current_version"],
        "target_version": producer.descriptor["target_version"],
        "compatibility": producer.descriptor["compatibility"],
        "inspected_at": inspected_at,
        "patch_preparation_allowed": True,
        "findings": [],
        "contract_graph": contract_graph,
        "bindings": sorted(
            [observation.binding() for observation in [*consumers, producer]],
            key=lambda binding: binding["repository"],
        ),
        "steps": steps,
        "rollback": [
            {
                "order": 1,
                "repository": producer.descriptor["repository"],
                "restore_version": producer.descriptor["rollback"]["version"],
            },
            {
                "order": 2,
                "consumer_state": "dual-read-remains-compatible",
                "repositories": [
                    observation.descriptor["repository"] for observation in consumers
                ],
            },
        ],
        "cleanup": "deferred",
    }
    validate_plan_order(plan)
    return _with_fingerprint(plan)


def validate_plan_order(plan: dict[str, Any]) -> None:
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ContractMigrationError("migration plan has no steps")
    producer_indexes = [
        index for index, step in enumerate(steps) if step.get("role") == "producer"
    ]
    if producer_indexes != [len(steps) - 1]:
        raise ContractMigrationError("producer-first or ambiguous merge order is forbidden")
    if any(step.get("role") != "consumer" for step in steps[:-1]):
        raise ContractMigrationError("all consumers must precede the producer")


def verify_plan_bindings(
    plan: dict[str, Any],
    repository_roots: dict[str, Path],
) -> None:
    fingerprint = plan.get("plan_fingerprint")
    without_fingerprint = {
        key: value for key, value in plan.items() if key != "plan_fingerprint"
    }
    expected = _with_fingerprint(without_fingerprint)["plan_fingerprint"]
    if fingerprint != expected:
        raise ContractMigrationError("migration plan fingerprint was tampered")
    validate_plan_order(plan)
    for binding in plan["bindings"]:
        repository = binding["repository"]
        root = repository_roots.get(repository)
        if root is None:
            raise ContractMigrationError(
                f"repository binding cannot be reverified: {repository}"
            )
        resolved_root = root.resolve()
        if str(resolved_root) != binding["repository_path"]:
            raise ContractMigrationError(
                f"repository path changed after planning: {repository}"
            )
        observation = observe_repository(
            resolved_root,
            resolved_root / binding["descriptor_path"],
            expected_head=binding["head"],
        )
        if observation.branch != binding["branch"]:
            raise ContractMigrationError(
                f"repository branch changed after planning: {repository}"
            )
        if observation.descriptor_sha256 != binding["descriptor_sha256"]:
            raise ContractMigrationError(
                f"descriptor changed after planning: {repository}"
            )


def assert_patch_target_available(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ContractMigrationError(f"patch worktree target is occupied: {path}")


def plan_from_repository_descriptors(
    specs: Sequence[tuple[Path, Path]],
    *,
    contract_id: str,
    inspected_at: str,
    expected_heads: dict[str, str] | None = None,
    patch_targets: Sequence[Path] = (),
) -> dict[str, Any]:
    _validate_inspected_at(inspected_at)
    observations: list[RepositoryObservation] = []
    findings: list[str] = []
    for target in patch_targets:
        try:
            assert_patch_target_available(target)
        except ContractMigrationError as exc:
            findings.append(str(exc))
    for repo_root, descriptor_path in specs:
        try:
            expected = (expected_heads or {}).get(str(repo_root.resolve()))
            observations.append(
                observe_repository(
                    repo_root,
                    descriptor_path,
                    expected_head=expected,
                )
            )
        except (ContractMigrationError, subprocess.CalledProcessError) as exc:
            findings.append(str(exc))
    if findings:
        return _unknown_plan(
            contract_id=contract_id,
            inspected_at=inspected_at,
            findings=findings,
        )
    graph = build_contract_graph(observations, contract_id=contract_id)
    return build_migration_plan(graph, inspected_at=inspected_at)


def _parse_spec(value: str) -> tuple[Path, Path]:
    try:
        repo, descriptor = value.split("::", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "descriptor spec must be REPO_ROOT::DESCRIPTOR_PATH"
        ) from exc
    return Path(repo), Path(descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a fail-closed cross-repository contract migration plan."
    )
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--inspected-at", required=True)
    parser.add_argument(
        "--descriptor",
        action="append",
        required=True,
        type=_parse_spec,
        metavar="REPO_ROOT::DESCRIPTOR_PATH",
    )
    parser.add_argument(
        "--patch-target",
        action="append",
        type=Path,
        default=[],
        help="Require a prospective isolated patch-worktree path to be unoccupied.",
    )
    args = parser.parse_args(argv)
    plan = plan_from_repository_descriptors(
        args.descriptor,
        contract_id=args.contract_id,
        inspected_at=args.inspected_at,
        patch_targets=args.patch_target,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0 if plan["state"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
