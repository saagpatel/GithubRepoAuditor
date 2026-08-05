from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.producer_preflight import (
    PREFLIGHT_SCHEMA_VERSION,
    PREFLIGHT_PASS_CHECKS,
    ProducerEvidence,
    inspect_canonical_producer,
    load_producer_evidence,
    producer_evidence_receipt_id,
    verify_evidence_still_current,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Tests")
    (repo / "README.md").write_text("fixture\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "fixture")
    _git(repo, "remote", "add", "origin", "git@github.com:saagpatel/GithubRepoAuditor.git")
    commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", commit)
    return repo, commit


def test_canonical_producer_passes_for_clean_matching_ref(tmp_path: Path) -> None:
    repo, commit = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
        now=datetime(2026, 7, 10, tzinfo=UTC),
    )
    assert result.state == "pass"
    assert result.evidence is not None
    assert result.evidence.commit == commit
    assert result.checks == PREFLIGHT_PASS_CHECKS


def test_canonical_producer_fails_dirty_worktree(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "untracked.txt").write_text("dirty\n")
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    assert result.state == "fail"
    assert result.checks["worktree_clean"] == "fail"


def test_canonical_producer_missing_ref_is_unknown(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/missing",
        checkout_role="canonical-automation",
    )
    assert result.state == "unknown"


def test_evidence_rejects_head_change(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    assert result.evidence is not None
    evidence = result.evidence
    (repo / "README.md").write_text("changed\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "move head")
    with pytest.raises(ValueError, match="HEAD changed after preflight"):
        verify_evidence_still_current(repo, evidence)


def test_currentness_rejects_invalid_in_memory_evidence_before_git_reads(
    tmp_path: Path,
) -> None:
    repo, commit = _repo(tmp_path)
    evidence = ProducerEvidence(
        repository="saagpatel/GithubRepoAuditor",
        expected_repository="attacker/other-repository",
        commit=commit,
        ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
        checkout_path=str(repo.resolve()),
        worktree_clean=True,
        dirty_path_count=0,
        verified_at=datetime.now(UTC),
        receipt_id="sha256:" + "a" * 64,
    )

    with pytest.raises(ValueError, match="invalid before currentness verification"):
        verify_evidence_still_current(repo, evidence)


def test_load_producer_evidence_accepts_passing_receipt(tmp_path: Path) -> None:
    path = tmp_path / "producer.json"
    verified_at = "2026-07-10T12:00:00Z"
    receipt_id = producer_evidence_receipt_id(
        repository="saagpatel/GithubRepoAuditor",
        expected_repository="saagpatel/GithubRepoAuditor",
        commit="a" * 40,
        ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
        checkout_path=str(tmp_path / "producer-repo"),
        verified_at=verified_at,
    )
    path.write_text(
        __import__("json").dumps(
            {
                "schema_version": PREFLIGHT_SCHEMA_VERSION,
                "state": "pass",
                "repository": "saagpatel/GithubRepoAuditor",
                "expected_repository": "saagpatel/GithubRepoAuditor",
                "commit": "a" * 40,
                "ref": "refs/remotes/origin/main",
                "checkout_role": "canonical-automation",
                "checkout_path": str(tmp_path / "producer-repo"),
                "worktree_clean": True,
                "dirty_path_count": 0,
                "verified_at": verified_at,
                "receipt_id": receipt_id,
                "checks": PREFLIGHT_PASS_CHECKS,
            }
        )
    )

    evidence = load_producer_evidence(path)

    assert evidence.commit == "a" * 40
    assert evidence.verified_at.tzinfo is not None
    assert evidence.to_dict()["verified_at"] == verified_at
    assert evidence.to_dict()["receipt_id"] == receipt_id


def test_producer_evidence_preserves_non_utc_serialized_timestamp() -> None:
    verified_at = "2026-07-10T17:30:00+05:30"
    payload = {
        "repository": "saagpatel/GithubRepoAuditor",
        "expected_repository": "saagpatel/GithubRepoAuditor",
        "commit": "a" * 40,
        "ref": "refs/remotes/origin/main",
        "checkout_role": "canonical-automation",
        "checkout_path": "/demo-workspace/producer",
        "worktree_clean": True,
        "dirty_path_count": 0,
        "verified_at": verified_at,
        "receipt_id": producer_evidence_receipt_id(
            repository="saagpatel/GithubRepoAuditor",
            expected_repository="saagpatel/GithubRepoAuditor",
            commit="a" * 40,
            ref="refs/remotes/origin/main",
            checkout_role="canonical-automation",
            checkout_path="/demo-workspace/producer",
            verified_at=verified_at,
        ),
    }

    evidence = ProducerEvidence.from_dict(payload)

    assert evidence.to_dict() == payload
    assert evidence.verified_at.utcoffset().total_seconds() == 0


def test_producer_evidence_rejects_receipt_after_repository_tamper() -> None:
    verified_at = "2026-07-10T12:00:00+00:00"
    payload = {
        "repository": "saagpatel/GithubRepoAuditor",
        "expected_repository": "saagpatel/GithubRepoAuditor",
        "commit": "a" * 40,
        "ref": "refs/remotes/origin/main",
        "checkout_role": "canonical-automation",
        "checkout_path": "/demo-workspace/producer",
        "worktree_clean": True,
        "dirty_path_count": 0,
        "verified_at": verified_at,
        "receipt_id": producer_evidence_receipt_id(
            repository="saagpatel/GithubRepoAuditor",
            expected_repository="saagpatel/GithubRepoAuditor",
            commit="a" * 40,
            ref="refs/remotes/origin/main",
            checkout_role="canonical-automation",
            checkout_path="/demo-workspace/producer",
            verified_at=verified_at,
        ),
    }
    payload["repository"] = "attacker/other-repository"

    with pytest.raises(ValueError, match="does not match expected_repository"):
        ProducerEvidence.from_dict(payload)


def test_producer_receipt_identity_is_not_delimiter_ambiguous() -> None:
    common = {
        "repository": "saagpatel/GithubRepoAuditor",
        "expected_repository": "saagpatel/GithubRepoAuditor",
        "commit": "a" * 40,
        "checkout_path": "/demo-workspace/producer",
        "verified_at": "2026-07-10T12:00:00Z",
    }
    left = {
        **common,
        "ref": "refs/heads/main\ncanonical",
        "checkout_role": "producer",
    }
    right = {
        **common,
        "ref": "refs/heads/main",
        "checkout_role": "canonical\nproducer",
    }
    assert "\n".join(left.values()) == "\n".join(right.values())

    assert producer_evidence_receipt_id(**left) != producer_evidence_receipt_id(
        **right
    )


def test_load_producer_evidence_rejects_nonpassing_receipt(tmp_path: Path) -> None:
    path = tmp_path / "producer.json"
    path.write_text(
        __import__("json").dumps(
            {
                "schema_version": PREFLIGHT_SCHEMA_VERSION,
                "state": "fail",
            }
        )
    )

    with pytest.raises(ValueError, match="did not pass preflight"):
        load_producer_evidence(path)


def test_load_producer_evidence_rejects_v2_without_legacy_fallback(
    tmp_path: Path,
) -> None:
    path = tmp_path / "producer-v2.json"
    path.write_text(json.dumps({"schema_version": "ghra_producer_preflight.v2"}))

    with pytest.raises(
        ValueError,
        match=r"schema mismatch.*ghra_producer_preflight\.v2.*v3",
    ):
        load_producer_evidence(path)


@pytest.mark.parametrize(
    "checks",
    (
        {
            key: value
            for key, value in PREFLIGHT_PASS_CHECKS.items()
            if key != "worktree_clean"
        },
        {**PREFLIGHT_PASS_CHECKS, "invented_check": "pass"},
        {**PREFLIGHT_PASS_CHECKS, "repository_identity": "fail"},
    ),
)
def test_load_producer_evidence_requires_exact_v3_pass_checks(
    tmp_path: Path,
    checks: dict[str, str],
) -> None:
    repo, _ = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    payload = result.to_dict()
    payload["checks"] = checks
    path = tmp_path / "producer.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="checks must exactly match"):
        load_producer_evidence(path)


def test_rewritten_repository_identity_failure_cannot_load_as_pass(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="other-owner/other-repository",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    assert result.state == "fail"
    assert result.checks["repository_identity"] == "fail"
    payload = result.to_dict()
    payload.update(state="pass", checks=PREFLIGHT_PASS_CHECKS)
    path = tmp_path / "rewritten-repository.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="does not match expected_repository"):
        load_producer_evidence(path)


def test_rewritten_head_ref_failure_fails_currentness_and_publication(
    tmp_path: Path,
) -> None:
    from src.portfolio_truth_publish import (
        PortfolioTruthPublishError,
        publish_portfolio_truth,
    )

    repo, prior_commit = _repo(tmp_path)
    (repo / "README.md").write_text("new head\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "advance head only")
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    assert result.state == "fail"
    assert result.evidence is not None
    assert result.evidence.commit != prior_commit
    assert result.checks["head_matches_expected_ref"] == "fail"
    payload = result.to_dict()
    payload.update(state="pass", checks=PREFLIGHT_PASS_CHECKS)
    path = tmp_path / "rewritten-ref.json"
    path.write_text(json.dumps(payload))

    evidence = load_producer_evidence(path)
    with pytest.raises(ValueError, match="Producer ref changed after preflight"):
        verify_evidence_still_current(repo, evidence)
    with pytest.raises(PortfolioTruthPublishError, match="Producer ref changed"):
        publish_portfolio_truth(
            workspace_root=tmp_path / "workspace",
            output_dir=tmp_path / "output",
            registry_output=tmp_path / "registry.md",
            portfolio_report_output=tmp_path / "report.md",
            producer_evidence=evidence,
            producer_repo_root=repo,
        )


def test_currentness_rechecks_origin_and_reports_missing_ref(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    assert result.evidence is not None
    evidence = result.evidence

    _git(repo, "remote", "set-url", "origin", "git@github.com:attacker/other.git")
    with pytest.raises(ValueError, match="origin repository changed"):
        verify_evidence_still_current(repo, evidence)

    _git(
        repo,
        "remote",
        "set-url",
        "origin",
        "git@github.com:saagpatel/GithubRepoAuditor.git",
    )
    _git(repo, "update-ref", "-d", evidence.ref)
    with pytest.raises(ValueError, match="Unable to verify producer ref"):
        verify_evidence_still_current(repo, evidence)
