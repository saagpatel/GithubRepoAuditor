"""Publisher CLI regressions using strictly validated, offline truth fixtures."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from github_repo_auditor import portfolio_generation as generation
from github_repo_auditor.github_security_coverage import (
    DEFAULT_COHORT_POLICY,
    collect_security_coverage,
    derive_default_attention_cohort,
    load_security_coverage_receipt,
    write_security_coverage_receipt,
)
from github_repo_auditor.portfolio_cohort_plan import PRODUCER_REPOSITORY
from github_repo_auditor.portfolio_cohort_plan_contract import (
    build_cohort_plan_payload,
    validate_cohort_plan,
)
from github_repo_auditor.portfolio_decision_queue import (
    build_decision_digest,
    render_decision_digest_markdown,
)
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from github_repo_auditor.portfolio_truth_validate import (
    _snapshot_from_payload,
    validate_truth_snapshot,
)
from github_repo_auditor.producer_preflight import inspect_canonical_producer

OPERATOR_COMMIT = "b" * 40
ARTIFACTS = (
    ("portfolio-truth.json", "application/json", "ghra.portfolio_truth@0.12.0"),
    ("decision-queue-v2.json", "application/json", "portfolio_decision_digest_v2"),
    ("portfolio-digest.md", "text/markdown", "portfolio_digest_markdown_v1"),
)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (
        value
        if isinstance(value, bytes)
        else (json.dumps(value, indent=2) + "\n").encode()
    )
    path.write_bytes(data)
    path.chmod(0o600)


def _stamp(path: Path) -> dict[str, Any]:
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }


def _environment(root: Path) -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(Path(generation.__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "TMPDIR": str(root / "tmp"),
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=_environment(repo.parent),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _initialize_repo(repo: Path, repository: str) -> str:
    repo.mkdir(parents=True, mode=0o700)
    _git(repo, "init", "-q", "--initial-branch=main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "remote", "add", "origin", f"https://github.com/{repository}.git")
    _write(repo / "README.md", b"# Fixture\n\nOwned offline fixture repository.\n")
    _write(
        repo / "AGENTS.md",
        b"# Fixture Context\n\n## What This Project Is\n\n"
        b"An owned offline product fixture for validating portfolio publication.\n\n"
        b"## Current State\n\nThe fixture is ready for local contract checks and is actively maintained.\n\n"
        b"## Stack\n\nPython and JSON provide the local fixture data and test runner.\n\n"
        b"## How To Run\n\nRun the local unit tests with Python. No external credentials are required.\n\n"
        b"## Known Risks\n\nProvider coverage remains unknown without credentials; this fixture is not a live audit.\n\n"
        b"## Next Recommended Move\n\nVerify the receipt identity and preserve prior published generations.\n",
    )
    _git(repo, "add", "README.md", "AGENTS.md")
    _git(repo, "commit", "-qm", "Synthetic fixture")
    return _git(repo, "rev-parse", "HEAD")


class _NoTransport:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def get(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("offline collection attempted a request")

    def post(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("offline collection attempted a request")


def _binding(root: Path, commit: str, now: datetime) -> generation.SecurityBinding:
    return generation.load_security_binding(
        root / "live/security.json",
        terminal_receipt_path=root / "live/terminal.json",
        expected_producer_commit=commit,
        expected_operator_commit=OPERATOR_COMMIT,
        max_age_hours=1,
        now=now,
    )


def replace_pair(root: Path, label: str) -> None:
    for name in ("security.json", "terminal.json"):
        staged = root / "live" / f"{name}.new"
        _write(staged, (root / "pairs" / label / name).read_bytes())
        os.replace(staged, root / "live" / name)


def build_fixture(root: Path, *, clock: datetime | None = None) -> dict[str, Any]:
    """Generate canonical truth locally, validate strictly, and retain all bytes."""
    root.mkdir(parents=True, mode=0o700)
    (root / "tmp").mkdir(mode=0o700)
    now = clock or (datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=20))
    workspace = root / "workspace"
    _initialize_repo(workspace / "Alpha", "fixture/alpha")
    producer_repo = root / "producer"
    commit = _initialize_repo(producer_repo, PRODUCER_REPOSITORY)
    preflight = inspect_canonical_producer(
        repo_root=producer_repo,
        expected_repository=PRODUCER_REPOSITORY,
        expected_ref=commit,
        checkout_role="canonical",
        now=now,
    )
    assert preflight.state == "pass" and preflight.evidence is not None
    _write(root / "producer.json", preflight.to_dict())
    catalog = root / "catalog.yaml"
    _write(
        catalog,
        b"defaults:\n  lifecycle_state: maintenance\n  criticality: medium\n"
        b"  category: vanity\nrepos:\n  Alpha:\n    lifecycle_state: active\n"
        b"    owner: fixture\n    category: commercial\n    tool_provenance: codex\n"
        b"    operating_path: maintain\n",
    )
    registry = root / "empty-registry.md"
    _write(registry, b"# Project Registry\n")
    candidate = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog,
        legacy_registry_path=registry,
        include_notion=False,
        repo_status_by_name={},
        now=now,
    ).snapshot.to_dict()
    cohort = derive_default_attention_cohort(candidate, expected_count=1)
    prior_bytes = (json.dumps(candidate, sort_keys=True) + "\n").encode()
    _write(root / "prior-truth.json", prior_bytes)
    plan_payload = build_cohort_plan_payload(
        generated_at=now,
        producer_commit=commit,
        producer_repository=PRODUCER_REPOSITORY,
        catalog_sha256=_stamp(catalog)["sha256"],
        workspace_root=str(workspace),
        prior_truth_path=str(root / "prior-truth.json"),
        prior_truth_sha256=hashlib.sha256(prior_bytes).hexdigest(),
        prior_truth_generated_at=now.isoformat(),
        policy=DEFAULT_COHORT_POLICY,
        prospective_repositories=cohort,
        prior_published_repositories=cohort,
    )
    plan = validate_cohort_plan(plan_payload)
    _write(root / "plan.json", plan_payload)
    admissions = {}
    for index, label in enumerate(("A", "B")):
        produced = now + timedelta(seconds=index)
        receipt = collect_security_coverage(
            candidate,
            token=None,
            expected_cohort_count=None,
            cohort_plan=plan,
            producer_commit=commit,
            now=produced,
            session=_NoTransport(),
            truth_sha256=plan.prior_truth_sha256,
        )
        loaded = write_security_coverage_receipt(
            receipt,
            root / "live/security.json",
            expected_cohort_count=None,
        )
        terminal = {
            "schema": "AutomationTerminalStateV1",
            "state": "succeeded",
            "completed": True,
            "partial": False,
            "exit_code": 0,
            "automation_id": "com.d.github-security-coverage.rehearsal",
            "observed_at": (produced + timedelta(seconds=1)).isoformat(),
            "invocation": {"kind": "offline-fixture"},
            "destination_readback": {
                "verified": True,
                "destination_id": str((root / "live/security.json").resolve()),
                "evidence": {
                    "destination_sha256": loaded.content_sha256,
                    "producer_commit": commit,
                    "producer_generation": {
                        "repository": PRODUCER_REPOSITORY.split("/")[0]
                        + "/operator-scripts",
                        "commit": OPERATOR_COMMIT,
                    },
                    "dispatch": {"dispatch_kind": "controlled"},
                },
            },
        }
        _write(root / "live/terminal.json", terminal)
        admissions[label] = dataclasses.asdict(
            _binding(root, commit, now + timedelta(seconds=5))
        )
        for name in ("security.json", "terminal.json"):
            _write(root / "pairs" / label / name, (root / "live" / name).read_bytes())
    assert admissions["A"]["receipt_id"] != admissions["B"]["receipt_id"]
    assert admissions["A"]["content_sha256"] != admissions["B"]["content_sha256"]
    replace_pair(root, "A")
    _write(root / "pinned-A.json", (root / "live/security.json").read_bytes())
    security = load_security_coverage_receipt(
        root / "pinned-A.json",
        expected_cohort_count=None,
        expected_producer_commit=commit,
        require_cohort_transition=True,
        max_age_hours=1,
        now=now + timedelta(seconds=5),
    )
    metadata = {
        "source_id": "github-security-coverage-receipt",
        "schema_version": security.schema_version,
        "produced_at": security.produced_at,
        "state": security.receipt_state,
        "age_hours": security.age_hours,
        "producer_commit": security.producer_commit,
        "cohort_policy": security.cohort_policy,
        "cohort_repository_count": len(cohort),
        "path": security.source_path,
        "receipt_id": security.receipt_id,
        "content_sha256": security.content_sha256,
    }
    validated = []
    for index, marker in enumerate(("seed-old", "seed-current", "trial")):
        instant = now + timedelta(seconds=2 + index)
        built = build_portfolio_truth_snapshot(
            workspace_root=workspace,
            catalog_path=catalog,
            legacy_registry_path=registry,
            include_notion=False,
            repo_status_by_name={},
            now=instant,
            security_alerts_by_name=security.entries_by_full_name,
            security_coverage_metadata=metadata,
            security_cohort_required=security.required_repositories,
            security_cohort_outgoing=security.outgoing_repositories,
            security_cohort_transition=security.transition,
            require_cohort_transition=True,
            producer=preflight.evidence.to_dict(),
        )
        validate_truth_snapshot(built.snapshot, security_max_age_hours=1)
        truth = built.snapshot.to_dict()
        folder = root / "artifacts" / marker
        _write(folder / "portfolio-truth.json", truth)
        # Validate what was serialized as well, with ordinary canonical rules.
        roundtrip = _snapshot_from_payload(
            json.loads((folder / "portfolio-truth.json").read_bytes())
        )
        validate_truth_snapshot(roundtrip, security_max_age_hours=1)
        assert roundtrip.to_dict() == truth
        assert len(truth["projects"]) == 1
        assert (
            truth["inputs"]["github_security"]["receipt_id"]
            == admissions["A"]["receipt_id"]
        )
        digest = build_decision_digest(truth)
        _write(folder / "decision-queue-v2.json", digest)
        _write(
            folder / "portfolio-digest.md",
            render_decision_digest_markdown(digest).encode(),
        )
        validated.append(marker)
    config = {
        "commit": commit,
        "admissions": admissions,
        "strictly_validated_truth": validated,
        "cohort": list(cohort),
        "source_file": str(Path(generation.__file__).resolve()),
    }
    _write(root / "config.json", config)
    return config


def worker(root: Path, marker: str, window: str) -> int:
    """Run the real CLI body; trace insertion does not replace the final guard."""
    config = json.loads((root / "config.json").read_text())
    args = [
        "publish",
        "--root",
        str(root / "published"),
        "--producer-receipt",
        str(root / "producer.json"),
        "--producer-repo-root",
        str(root / "producer"),
        "--expected-repository",
        PRODUCER_REPOSITORY,
        "--expected-commit",
        config["commit"],
        "--expected-operator-commit",
        OPERATOR_COMMIT,
        "--security-receipt",
        str(root / "live/security.json"),
        "--security-terminal-receipt",
        str(root / "live/terminal.json"),
    ]
    for name, media, contract in ARTIFACTS:
        args += [
            "--artifact",
            f"{name}={root / 'artifacts' / marker / name}={media}={contract}",
        ]
    events = []
    if window == "before-entry":
        replace_pair(root, "B")
        events.append("replaced-before-main")
    elif window == "mismatched-terminal":
        _write(
            root / "live/security.json", (root / "pairs/B/security.json").read_bytes()
        )
        events.append("receipt-B-terminal-A-before-main")
    switched = False

    def trace(frame: Any, event: str, arg: Any) -> Any:
        nonlocal switched
        if frame.f_code.co_filename != generation.__file__:
            return trace
        name = frame.f_code.co_name
        if (
            name == "load_security_binding"
            and event == "return"
            and isinstance(arg, generation.SecurityBinding)
        ):
            events.append({"admitted": dataclasses.asdict(arg)})
        if name == "pre_pointer_check" and event == "call":
            events.append("actual-pre-pointer-check-entry")
            if window == "after-entry" and not switched:
                replace_pair(root, "B")
                switched = True
                events.append("replaced-before-actual-guard-body")
        if name == "pre_pointer_check" and event == "exception":
            events.append({"guard_exception": str(arg[1])})
        return trace

    sys.settrace(trace)
    try:
        rc = generation.main(args)
    finally:
        sys.settrace(None)
    _write(
        root / f"{marker}-trace.json",
        {"returncode": rc, "events": events, "argv": args},
    )
    return rc


def invoke(root: Path, marker: str, window: str) -> subprocess.CompletedProcess[str]:
    outcome = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            str(root),
            marker,
            window,
        ],
        env=_environment(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    _write(root / f"{marker}-stdout.txt", outcome.stdout.encode())
    _write(root / f"{marker}-stderr.txt", outcome.stderr.encode())
    return outcome


def check_real_cli_valid_truth_identity_and_replacement_windows(
    tmp_path: Path, window: str
) -> None:
    build_fixture(tmp_path / "case")
    root = tmp_path / "case"
    for marker in ("seed-old", "seed-current"):
        seed = invoke(root, marker, "unchanged")
        assert seed.returncode == 0, seed.stderr
    published = root / "published"
    pointer_bytes = (published / "pointer.json").read_bytes()
    before = json.loads(pointer_bytes)
    preserved = {
        str(p.relative_to(published)): _stamp(p)
        for p in (published / "releases").rglob("*")
        if p.is_file()
    }
    inputs = {n: _stamp(root / "artifacts/trial" / n) for n, _, _ in ARTIFACTS}
    outcome = invoke(root, "trial", window)
    after = generation.read_pointer(published)
    for relative, recorded in preserved.items():
        assert _stamp(published / relative) == recorded
    for name, recorded in inputs.items():
        assert _stamp(root / "artifacts/trial" / name) == recorded
    old_ids = {Path(relative).parts[1] for relative in preserved}
    added = {p.name for p in (published / "releases").iterdir()} - old_ids
    if window == "unchanged":
        assert outcome.returncode == 0, outcome.stderr
        assert after["previous"] == before["current"]
        assert after["current"] != before["current"]
        selected = generation.resolve_current(published).generation_dir
        manifest = json.loads((selected / "manifest.json").read_text())
        truth = json.loads((selected / "portfolio-truth.json").read_text())
        validate_truth_snapshot(_snapshot_from_payload(truth), security_max_age_hours=1)
        for field in ("receipt_id", "content_sha256"):
            assert (
                truth["inputs"]["github_security"][field]
                == manifest["github_security"][field]
            )
        assert len(added) == 1
    else:
        assert outcome.returncode == 1, outcome.stdout + outcome.stderr
        assert (published / "pointer.json").read_bytes() == pointer_bytes
        if window == "after-entry":
            assert (
                "security receipt changed before pointer publication" in outcome.stderr
            )
            assert len(added) == 1
            trace = json.loads((root / "trial-trace.json").read_text())
            assert "actual-pre-pointer-check-entry" in trace["events"]
            assert "replaced-before-actual-guard-body" in trace["events"]
        else:
            assert not added
            if window == "mismatched-terminal":
                assert "security terminal content hash mismatch" in outcome.stderr
            else:
                assert "identity" in outcome.stderr or "receipt_id" in outcome.stderr
    generation.resolve_current(published)


class CanonicalTruthPublicationTests(unittest.TestCase):
    def run_window(self, window: str) -> None:
        with tempfile.TemporaryDirectory(
            prefix="valid-truth-publication-", dir=os.environ.get("TMPDIR")
        ) as folder:
            check_real_cli_valid_truth_identity_and_replacement_windows(
                Path(folder), window
            )

    def test_correct_publication(self) -> None:
        self.run_window("unchanged")

    def test_replacement_before_admission(self) -> None:
        self.run_window("before-entry")

    def test_replacement_after_admission(self) -> None:
        self.run_window("after-entry")

    def test_mismatched_terminal(self) -> None:
        self.run_window("mismatched-terminal")


if __name__ == "__main__":

    def deny_network(event: str, args: Any) -> None:
        if event in {
            "socket.connect",
            "socket.connect_ex",
            "socket.getaddrinfo",
            "socket.bind",
        }:
            raise RuntimeError("offline publisher fixture forbids networking")

    sys.addaudithook(deny_network)
    if sys.argv[1] == "worker":
        raise SystemExit(worker(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
    if sys.argv[1] == "build":
        build_fixture(Path(sys.argv[2]))
