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
PRODUCER_REPOSITORY = "saagpatel/GithubRepoAuditor"
CONSUMER_REPOSITORY = "saagpatel/PortfolioCommandCenter"
FIXTURE_RELATIVE_PATH = (
    "fixtures/contracts/portfolio-command-center-v1/portfolio-truth.json"
)
MANIFEST_RELATIVE_PATH = (
    "fixtures/contracts/portfolio-command-center-v1/manifest.json"
)

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


def build_contract_fixture() -> dict[str, Any]:
    """Return the fixed-clock public-safe PortfolioTruth compatibility fixture."""
    fixture = build_snapshot(
        GENERATED_AT,
        project_specs=_contract_project_specs(),
    )
    fixture["contract_fixture"] = {
        "contract_version": CONTRACT_VERSION,
        "deterministic": True,
    }
    fixture["projects"][0]["additive_contract_canary"] = {
        "consumer_behavior": "ignore-compatible-addition"
    }
    return fixture


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a contract artifact in the one canonical committed form."""
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return f"{rendered}\n".encode()


def fixture_bytes() -> bytes:
    return canonical_json_bytes(build_contract_fixture())


def fixture_sha256() -> str:
    return hashlib.sha256(fixture_bytes()).hexdigest()


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
            "additive_canary_paths": [
                "contract_fixture",
                "projects[0].additive_contract_canary",
            ],
        },
    }


def manifest_bytes() -> bytes:
    return canonical_json_bytes(build_contract_manifest())
