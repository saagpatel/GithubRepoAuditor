"""Deterministic PortfolioTruth fixture shared with PortfolioCommandCenter.

The full public demo remains a rolling, portfolio-scale artifact. This smaller
fixture is the stable producer/consumer compatibility seam: it carries one row
for every receipt-backed security state and intentionally includes additive
fields that a compatible 0.x consumer must ignore.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from src.demo_portfolio import DEMO_PROJECTS, DemoProject, build_snapshot
from src.portfolio_truth_types import SCHEMA_VERSION

CONTRACT_VERSION = "ghra-pcc-portfolio-truth.v1"
PORTABLE_CONTRACT_VERSION = "ghra-portfolio-truth-portable.v1"
PRODUCER_REPOSITORY = "saagpatel/GithubRepoAuditor"
CONSUMER_REPOSITORY = "saagpatel/PortfolioCommandCenter"
FIXTURE_RELATIVE_PATH = (
    "fixtures/contracts/portfolio-command-center-v1/portfolio-truth.json"
)
MANIFEST_RELATIVE_PATH = (
    "fixtures/contracts/portfolio-command-center-v1/manifest.json"
)
PORTABLE_FIXTURE_RELATIVE_PATH = (
    "fixtures/contracts/portable-consumers-v1/portfolio-truth.json"
)
CONSUMER_PROFILE_MANIFEST_PATHS = {
    "operator-control-plane-v1": (
        "fixtures/contracts/operator-control-plane-v1/manifest.json"
    ),
    "public-site-projection-v1": (
        "fixtures/contracts/public-site-projection-v1/manifest.json"
    ),
}

# Fixed-clock values make the bytes durable. Consumers evaluate freshness
# against EVALUATED_AT rather than wall time; runtime freshness behavior remains
# independently tested against its real clock.
GENERATED_AT = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
EVALUATED_AT = GENERATED_AT + timedelta(hours=6)

_PROJECT_CODENAMES = (
    "Dovetail Forge",  # complete
    "Kestrel Loom",  # partial
    "Quartz Signal",  # stale
    "Solstice Cairn",  # unknown
)


def _contract_project_specs() -> tuple[DemoProject, ...]:
    by_codename = {project.codename: project for project in DEMO_PROJECTS}
    missing = [name for name in _PROJECT_CODENAMES if name not in by_codename]
    if missing:
        raise ValueError(f"Contract fixture project(s) missing: {missing}")
    return tuple(by_codename[name] for name in _PROJECT_CODENAMES)


def _build_fixture(contract_version: str) -> dict[str, Any]:
    fixture = build_snapshot(
        GENERATED_AT,
        project_specs=_contract_project_specs(),
    )
    # This deterministic compatibility artifact is not emitted by an attested
    # producer checkout. Canonical truth uses an empty object for absent
    # evidence; partial synthetic evidence would be invalid and misleading.
    fixture["producer"] = {}
    fixture["contract_fixture"] = {
        "contract_version": contract_version,
        "deterministic": True,
        "producer_evidence": "absent",
        "security_evidence_semantics": "synthetic-cross-receipt-state-matrix",
    }
    fixture["projects"][0]["additive_contract_canary"] = {
        "consumer_behavior": "ignore-compatible-addition"
    }
    return fixture


def build_contract_fixture() -> dict[str, Any]:
    """Return the byte-stable legacy PortfolioCommandCenter fixture."""
    return _build_fixture(CONTRACT_VERSION)


def build_portable_contract_fixture() -> dict[str, Any]:
    """Return the shared public-safe fixture for additive consumer profiles."""
    return _build_fixture(PORTABLE_CONTRACT_VERSION)


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a contract artifact in the one canonical committed form."""
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return f"{rendered}\n".encode()


def fixture_bytes() -> bytes:
    return canonical_json_bytes(build_contract_fixture())


def fixture_sha256() -> str:
    return hashlib.sha256(fixture_bytes()).hexdigest()


def portable_fixture_bytes() -> bytes:
    return canonical_json_bytes(build_portable_contract_fixture())


def portable_fixture_sha256() -> str:
    return hashlib.sha256(portable_fixture_bytes()).hexdigest()


def build_contract_manifest() -> dict[str, Any]:
    """Describe the portable artifact without a self-referential Git commit.

    The consumer lock owns the immutable producer commit. Keeping the commit out
    of this producer file avoids a hash that changes merely because it names
    itself.
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "producer": {
            "repository": PRODUCER_REPOSITORY,
            "generator": (
                "src.portfolio_truth_contract_fixture:build_contract_fixture"
            ),
            "manifest_path": MANIFEST_RELATIVE_PATH,
            "artifact_path": FIXTURE_RELATIVE_PATH,
            "artifact_sha256": fixture_sha256(),
        },
        "consumer": {
            "repository": CONSUMER_REPOSITORY,
            "compatibility_policy": "additive-0.x",
        },
        "portfolio_truth_schema_version": SCHEMA_VERSION,
        "fixture": {
            "generated_at": GENERATED_AT.isoformat(),
            "evaluation_time": EVALUATED_AT.isoformat(),
            "project_count": len(_PROJECT_CODENAMES),
            "coverage_states": ["complete", "partial", "stale", "unknown"],
            "producer_evidence": "absent",
            "security_evidence_semantics": (
                "synthetic-cross-receipt-state-matrix"
            ),
            "additive_canary_paths": [
                "contract_fixture",
                "projects[0].additive_contract_canary",
            ],
        },
    }


def manifest_bytes() -> bytes:
    return canonical_json_bytes(build_contract_manifest())


def _profile_acceptance(profile_id: str) -> dict[str, Any]:
    common_cases = [
        {
            "case_id": "valid-current-schema",
            "source": "artifact",
            "expected": "accept",
        },
        {
            "case_id": "additive-canary",
            "source": "artifact",
            "pointer": "/projects/0/additive_contract_canary",
            "expected": "accept-ignore-addition",
        },
        {
            "case_id": "missing-schema-version",
            "source": "artifact",
            "mutation": {"op": "remove", "path": "/schema_version"},
            "expected": "reject",
        },
        {
            "case_id": "malformed-root",
            "source": "literal",
            "value": [],
            "expected": "reject",
        },
    ]
    if profile_id == "operator-control-plane-v1":
        return {
            "coverage_cases": [
                *common_cases,
                {
                    "case_id": "contradictory-contract-envelope",
                    "source": "artifact",
                    "mutation": {
                        "op": "add",
                        "path": "/contract",
                        "value": {
                            "id": "ghra.portfolio_truth",
                            "version": "0.12.0",
                            "compatibility": "additive",
                        },
                    },
                    "expected": "reject",
                },
            ],
            "fail_closed_behavior": "incompatible-artifact-yields-unavailable-health",
        }
    if profile_id == "public-site-projection-v1":
        return {
            "coverage_cases": [
                *common_cases,
                {
                    "case_id": "non-allowlisted-project",
                    "source": "artifact",
                    "expected": "aggregate-only",
                },
                {
                    "case_id": "missing-projects",
                    "source": "artifact",
                    "mutation": {"op": "remove", "path": "/projects"},
                    "expected": "reject",
                },
                {
                    "case_id": "malformed-projects",
                    "source": "artifact",
                    "mutation": {
                        "op": "replace",
                        "path": "/projects",
                        "value": "invalid",
                    },
                    "expected": "reject",
                },
            ],
            "public_projection": {
                "allowlisted_repo_slugs": ["dovetail-forge", "kestrel-loom"],
                "expected_curated_repo_slugs": [
                    "dovetail-forge",
                    "kestrel-loom",
                ],
            },
            "fail_closed_behavior": "unknown-project-identities-remain-anonymous",
        }
    raise ValueError(f"Unknown PortfolioTruth consumer profile: {profile_id}")


def build_consumer_profile_manifest(profile_id: str) -> dict[str, Any]:
    """Describe one consumer profile without exposing a private repository name."""
    manifest_path = CONSUMER_PROFILE_MANIFEST_PATHS.get(profile_id)
    if manifest_path is None:
        raise ValueError(f"Unknown PortfolioTruth consumer profile: {profile_id}")
    return {
        "contract_version": PORTABLE_CONTRACT_VERSION,
        "producer": {
            "repository": PRODUCER_REPOSITORY,
            "generator": (
                "src.portfolio_truth_contract_fixture:"
                "build_portable_contract_fixture"
            ),
            "manifest_path": manifest_path,
            "artifact_path": PORTABLE_FIXTURE_RELATIVE_PATH,
            "artifact_sha256": portable_fixture_sha256(),
        },
        "consumer_profile": {
            "id": profile_id,
            "compatibility_policy": "additive-0.x",
        },
        "portfolio_truth_schema_version": SCHEMA_VERSION,
        "fixture": {
            "generated_at": GENERATED_AT.isoformat(),
            "evaluation_time": EVALUATED_AT.isoformat(),
            "project_count": len(_PROJECT_CODENAMES),
            "producer_evidence": "absent",
            "additive_canary_paths": [
                "contract_fixture",
                "projects[0].additive_contract_canary",
            ],
        },
        "acceptance": _profile_acceptance(profile_id),
    }


def consumer_profile_manifest_bytes(profile_id: str) -> bytes:
    return canonical_json_bytes(build_consumer_profile_manifest(profile_id))
