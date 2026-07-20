from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from src.contract_migration import (
    ContractMigrationError,
    assert_patch_target_available,
    build_contract_graph,
    build_migration_plan,
    observe_repository,
    plan_from_repository_descriptors,
    validate_descriptor,
    validate_plan_order,
    verify_plan_bindings,
)

INSPECTED_AT = "2026-07-20T07:00:00+00:00"
PRODUCER = "saagpatel/GithubRepoAuditor"
PERSONAL_OPS = "saagpatel/personal-ops"
PCC = "saagpatel/PortfolioCommandCenter"


def _descriptor(repository: str, role: str) -> dict:
    is_producer = role == "producer"
    return {
        "schema_version": "ContractDescriptorV1",
        "contract_id": "ghra.portfolio_truth",
        "repository": repository,
        "role": role,
        "producer": PRODUCER,
        "consumer": None if is_producer else repository,
        "current_version": "0.11.0",
        "target_version": "0.12.0",
        "accepted_version_range": None if is_producer else ">=0.11.0 <1.0.0",
        "compatibility": "additive",
        "expected_consumers": [PERSONAL_OPS, PCC] if is_producer else [],
        "evidence": "declared-static",
        "adapter": {
            "id": f"{repository.split('/')[-1].lower()}.portfolio_truth_0_12",
            "patch_paths": ["src/portfolio-truth-contract.ts"],
        },
        "verifier": {"commands": ["pnpm test"]},
        "rollback": {
            "strategy": (
                "producer-first" if is_producer else "consumer-remains-dual-read"
            ),
            "version": "0.11.0",
        },
    }


def _repo(tmp_path: Path, name: str, descriptor: dict) -> tuple[Path, Path]:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "contract@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Contract Fixture"],
        cwd=repo,
        check=True,
    )
    path = repo / "contracts/ghra.portfolio_truth.json"
    path.parent.mkdir()
    path.write_text(json.dumps(descriptor, indent=2) + "\n")
    (repo / "src").mkdir()
    (repo / "src/portfolio-truth-contract.ts").write_text("export {};\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    return repo, path


def _observations(tmp_path: Path):
    producer_repo, producer_path = _repo(
        tmp_path, "producer", _descriptor(PRODUCER, "producer")
    )
    personal_repo, personal_path = _repo(
        tmp_path, "personal", _descriptor(PERSONAL_OPS, "consumer")
    )
    pcc_repo, pcc_path = _repo(tmp_path, "pcc", _descriptor(PCC, "consumer"))
    specs = [
        (producer_repo, producer_path),
        (personal_repo, personal_path),
        (pcc_repo, pcc_path),
    ]
    return specs, [observe_repository(*spec) for spec in specs]


def test_real_descriptor_schema_matches_required_contract() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "contracts/contract-descriptor.v1.schema.json").read_text()
    )
    descriptor = json.loads(
        (root / "contracts/ghra.portfolio_truth.json").read_text()
    )
    assert set(schema["required"]) == set(descriptor)
    assert validate_descriptor(descriptor) == descriptor


def test_graph_has_one_producer_two_consumers_and_consumer_first_plan(
    tmp_path: Path,
) -> None:
    _specs, observations = _observations(tmp_path)
    graph = build_contract_graph(observations, contract_id="ghra.portfolio_truth")
    plan = build_migration_plan(graph, inspected_at=INSPECTED_AT)

    assert graph["state"] == "pass"
    assert len(graph["consumers"]) == 2
    assert plan["state"] == "pass"
    assert plan["schema_version"] == "MigrationPlanV1"
    assert plan["contract_graph"]["schema_version"] == "ContractGraphV1"
    assert plan["contract_graph"]["inspected_at"] == INSPECTED_AT
    assert len(plan["contract_graph"]["edges"]) == 2
    assert plan["patch_preparation_allowed"] is True
    assert [step["repository"] for step in plan["steps"]] == [
        PERSONAL_OPS,
        PCC,
        PRODUCER,
    ]
    assert plan["rollback"][0]["repository"] == PRODUCER
    assert plan["cleanup"] == "deferred"


def test_plan_is_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    _specs, observations = _observations(tmp_path)
    graph = build_contract_graph(observations, contract_id="ghra.portfolio_truth")
    first = build_migration_plan(graph, inspected_at=INSPECTED_AT)
    second = build_migration_plan(graph, inspected_at=INSPECTED_AT)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_static_analysis_and_plan_generation_stays_under_ten_seconds(
    tmp_path: Path,
) -> None:
    specs, _observations_value = _observations(tmp_path)
    started = time.perf_counter()
    plan = plan_from_repository_descriptors(
        specs,
        contract_id="ghra.portfolio_truth",
        inspected_at=INSPECTED_AT,
    )
    elapsed = time.perf_counter() - started
    assert plan["state"] == "pass"
    assert elapsed <= 10.0


def test_missing_consumer_is_unknown_and_blocks_patch_preparation(
    tmp_path: Path,
) -> None:
    _specs, observations = _observations(tmp_path)
    graph = build_contract_graph(
        observations[:-1], contract_id="ghra.portfolio_truth"
    )
    plan = build_migration_plan(graph, inspected_at=INSPECTED_AT)
    assert plan["state"] == "unknown"
    assert plan["patch_preparation_allowed"] is False
    assert plan["steps"] == []
    assert any("missing declared consumers" in finding for finding in plan["findings"])


def test_duplicate_producer_and_unexpected_consumer_are_unknown(
    tmp_path: Path,
) -> None:
    _specs, observations = _observations(tmp_path)
    duplicate_producer_graph = build_contract_graph(
        [*observations, observations[0]],
        contract_id="ghra.portfolio_truth",
    )
    assert duplicate_producer_graph["state"] == "unknown"
    assert duplicate_producer_graph["findings"] == [
        "expected exactly one producer, observed 2"
    ]

    unexpected_descriptor = _descriptor(
        "saagpatel/UnexpectedConsumer", "consumer"
    )
    unexpected_repo, unexpected_path = _repo(
        tmp_path, "unexpected", unexpected_descriptor
    )
    unexpected_observation = observe_repository(
        unexpected_repo, unexpected_path
    )
    unexpected_graph = build_contract_graph(
        [*observations, unexpected_observation],
        contract_id="ghra.portfolio_truth",
    )
    unexpected_plan = build_migration_plan(
        unexpected_graph, inspected_at=INSPECTED_AT
    )
    assert unexpected_plan["state"] == "unknown"
    assert any(
        "unexpected consumers" in finding
        for finding in unexpected_plan["findings"]
    )
    assert unexpected_plan["contract_graph"]["consumers"][-1]["repository"] == (
        "saagpatel/UnexpectedConsumer"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("current_version", "not-semver", "strict semantic version"),
        ("target_version", "1.0.0", "range rejects target"),
        ("evidence", "dynamic", "dynamic or hidden"),
    ],
)
def test_malformed_incompatible_or_hidden_consumer_is_unknown(
    field: str,
    value: str,
    message: str,
) -> None:
    descriptor = _descriptor(PERSONAL_OPS, "consumer")
    descriptor[field] = value
    with pytest.raises(ContractMigrationError, match=message):
        validate_descriptor(descriptor)


def test_stale_consumer_descriptor_is_unknown(tmp_path: Path) -> None:
    _specs, observations = _observations(tmp_path)
    stale_payload = dict(observations[1].descriptor)
    stale_payload["current_version"] = "0.10.0"
    stale_payload["rollback"] = {
        "strategy": "consumer-remains-dual-read",
        "version": "0.10.0",
    }
    stale_payload["accepted_version_range"] = ">=0.10.0 <1.0.0"
    stale_observation = observations[1].__class__(
        **{**observations[1].__dict__, "descriptor": validate_descriptor(stale_payload)}
    )
    graph = build_contract_graph(
        [observations[0], stale_observation, observations[2]],
        contract_id="ghra.portfolio_truth",
    )
    assert graph["state"] == "unknown"
    assert any("descriptor is stale" in finding for finding in graph["findings"])


def test_changed_head_dirty_repo_symlink_and_occupied_target_fail_closed(
    tmp_path: Path,
) -> None:
    specs, _observations_value = _observations(tmp_path)
    repo, descriptor = specs[0]
    with pytest.raises(ContractMigrationError, match="HEAD changed"):
        observe_repository(repo, descriptor, expected_head="0" * 40)

    (repo / "dirty.txt").write_text("dirty\n")
    plan = plan_from_repository_descriptors(
        specs,
        contract_id="ghra.portfolio_truth",
        inspected_at=INSPECTED_AT,
    )
    assert plan["state"] == "unknown"
    assert plan["patch_preparation_allowed"] is False
    assert any("worktree is dirty" in finding for finding in plan["findings"])
    (repo / "dirty.txt").unlink()

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    occupied_plan = plan_from_repository_descriptors(
        specs,
        contract_id="ghra.portfolio_truth",
        inspected_at=INSPECTED_AT,
        patch_targets=[occupied],
    )
    assert occupied_plan["state"] == "unknown"
    assert occupied_plan["patch_preparation_allowed"] is False
    assert any("target is occupied" in finding for finding in occupied_plan["findings"])

    external = tmp_path / "external.json"
    external.write_text(descriptor.read_text())
    link = repo / "contracts/symlink.json"
    link.symlink_to(external)
    with pytest.raises(ContractMigrationError, match="symlink"):
        observe_repository(repo, link)

    with pytest.raises(ContractMigrationError, match="occupied"):
        assert_patch_target_available(occupied)


def test_adapter_paths_must_exist_be_tracked_and_not_be_symlinks(
    tmp_path: Path,
) -> None:
    missing_descriptor = _descriptor(PERSONAL_OPS, "consumer")
    missing_descriptor["adapter"]["patch_paths"] = ["src/does-not-exist.ts"]
    missing_repo, missing_path = _repo(tmp_path, "missing", missing_descriptor)
    with pytest.raises(ContractMigrationError, match="absent from repository"):
        observe_repository(missing_repo, missing_path)

    untracked_repo, untracked_path = _repo(
        tmp_path, "untracked", _descriptor(PERSONAL_OPS, "consumer")
    )
    untracked_payload = json.loads(untracked_path.read_text())
    untracked_payload["adapter"]["patch_paths"].append("src/untracked.ts")
    untracked_path.write_text(json.dumps(untracked_payload, indent=2) + "\n")
    subprocess.run(["git", "add", "."], cwd=untracked_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "reference untracked adapter"],
        cwd=untracked_repo,
        check=True,
    )
    (untracked_repo / "src/untracked.ts").write_text("export {};\n")
    (untracked_repo / ".git/info/exclude").write_text("src/untracked.ts\n")
    with pytest.raises(ContractMigrationError, match="not tracked by Git"):
        observe_repository(untracked_repo, untracked_path)

    symlink_descriptor = _descriptor(PERSONAL_OPS, "consumer")
    symlink_descriptor["adapter"]["patch_paths"] = ["src/link.ts"]
    symlink_repo, symlink_path = _repo(
        tmp_path, "symlink-adapter", symlink_descriptor
    )
    external = tmp_path / "adapter-external.ts"
    external.write_text("export {};\n")
    (symlink_repo / "src/link.ts").symlink_to(external)
    subprocess.run(["git", "add", "."], cwd=symlink_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "track symlink adapter"],
        cwd=symlink_repo,
        check=True,
    )
    with pytest.raises(ContractMigrationError, match="cannot be a symlink"):
        observe_repository(symlink_repo, symlink_path)


def test_path_verifier_secret_and_producer_first_controls() -> None:
    escaping = _descriptor(PERSONAL_OPS, "consumer")
    escaping["adapter"]["patch_paths"] = ["../outside"]
    with pytest.raises(ContractMigrationError, match="escapes"):
        validate_descriptor(escaping)

    verifier_escape = _descriptor(PERSONAL_OPS, "consumer")
    verifier_escape["verifier"]["commands"] = ["pnpm test > /tmp/result"]
    with pytest.raises(ContractMigrationError, match="bounded execution"):
        validate_descriptor(verifier_escape)

    verifier_background_escape = _descriptor(PERSONAL_OPS, "consumer")
    verifier_background_escape["verifier"]["commands"] = [
        "pnpm test & touch escaped"
    ]
    with pytest.raises(ContractMigrationError, match="bounded execution"):
        validate_descriptor(verifier_background_escape)

    for command in (
        "pnpm publish",
        "pnpm install",
        "pnpm exec arbitrary-command",
        "node -e process.exit(0)",
        "cargo check --manifest-path /etc/Cargo.toml",
        "pnpm test --token=do-not-copy",
        "uv run ruff check --fix src",
        "pnpm --dir ~ run build",
        "cargo check --manifest-path ~/Cargo.toml",
        "node --test ~/outside.js",
        "uv run ruff check {~/outside,src/inside}.py",
        "node --test {~/outside,src/inside}.js",
        "pnpm --dir =ls run build",
    ):
        unsafe_verifier = _descriptor(PERSONAL_OPS, "consumer")
        unsafe_verifier["verifier"]["commands"] = [command]
        with pytest.raises(ContractMigrationError):
            validate_descriptor(unsafe_verifier)

    secret = _descriptor(PERSONAL_OPS, "consumer")
    secret["token"] = "do-not-copy"
    with pytest.raises(ContractMigrationError, match="forbidden secret field"):
        validate_descriptor(secret)

    with pytest.raises(ContractMigrationError, match="producer-first"):
        validate_plan_order(
            {
                "steps": [
                    {"role": "producer"},
                    {"role": "consumer"},
                ]
            }
        )


def test_tampered_hash_and_changed_descriptor_binding_are_rejected(
    tmp_path: Path,
) -> None:
    specs, observations = _observations(tmp_path)
    graph = build_contract_graph(observations, contract_id="ghra.portfolio_truth")
    plan = build_migration_plan(graph, inspected_at=INSPECTED_AT)
    roots = {
        observation.descriptor["repository"]: Path(observation.repository_path)
        for observation in observations
    }
    verify_plan_bindings(plan, roots)

    tampered = json.loads(json.dumps(plan))
    tampered["bindings"][0]["descriptor_sha256"] = "0" * 64
    with pytest.raises(ContractMigrationError, match="fingerprint was tampered"):
        verify_plan_bindings(tampered, roots)

    repo, descriptor = specs[1]
    payload = json.loads(descriptor.read_text())
    payload["adapter"]["id"] = "personalops.changed"
    descriptor.write_text(json.dumps(payload, indent=2) + "\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "change descriptor"], cwd=repo, check=True)
    with pytest.raises(ContractMigrationError, match="HEAD changed"):
        verify_plan_bindings(plan, roots)


def test_changed_repository_path_and_branch_binding_are_rejected(
    tmp_path: Path,
) -> None:
    specs, observations = _observations(tmp_path)
    graph = build_contract_graph(observations, contract_id="ghra.portfolio_truth")
    plan = build_migration_plan(graph, inspected_at=INSPECTED_AT)
    roots = {
        observation.descriptor["repository"]: Path(observation.repository_path)
        for observation in observations
    }

    personal_repo = specs[1][0]
    clone = tmp_path / "personal-clone"
    subprocess.run(["git", "clone", "-q", str(personal_repo), str(clone)], check=True)
    clone_roots = {**roots, PERSONAL_OPS: clone}
    with pytest.raises(ContractMigrationError, match="path changed"):
        verify_plan_bindings(plan, clone_roots)

    subprocess.run(
        ["git", "switch", "-q", "-c", "other-branch"],
        cwd=personal_repo,
        check=True,
    )
    with pytest.raises(ContractMigrationError, match="branch changed"):
        verify_plan_bindings(plan, roots)
