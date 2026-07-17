from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PREFLIGHT_SCHEMA_VERSION = "ghra_producer_preflight.v2"


@dataclass(frozen=True)
class ProducerEvidence:
    repository: str
    commit: str
    ref: str
    checkout_role: str
    checkout_path: str
    worktree_clean: bool
    dirty_path_count: int
    verified_at: datetime
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "commit": self.commit,
            "ref": self.ref,
            "checkout_role": self.checkout_role,
            "checkout_path": self.checkout_path,
            "worktree_clean": self.worktree_clean,
            "dirty_path_count": self.dirty_path_count,
            "verified_at": self.verified_at.isoformat(),
            "receipt_id": self.receipt_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProducerEvidence:
        required = {
            "repository",
            "commit",
            "ref",
            "checkout_role",
            "checkout_path",
            "worktree_clean",
            "dirty_path_count",
            "verified_at",
            "receipt_id",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"Producer evidence is missing fields: {missing}")
        verified_at = str(payload["verified_at"])
        if verified_at.endswith("Z"):
            verified_at = f"{verified_at[:-1]}+00:00"
        try:
            parsed_verified_at = datetime.fromisoformat(verified_at)
        except ValueError as exc:
            raise ValueError("Producer evidence verified_at is not valid ISO-8601.") from exc
        if parsed_verified_at.tzinfo is None:
            raise ValueError("Producer evidence verified_at must include a timezone.")
        commit = str(payload["commit"])
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise ValueError("Producer evidence commit must be a lowercase 40-character SHA.")
        if payload["worktree_clean"] is not True:
            raise ValueError("Producer evidence must declare a clean worktree.")
        if payload["dirty_path_count"] != 0:
            raise ValueError("Clean producer evidence must declare dirty_path_count=0.")
        return cls(
            repository=str(payload["repository"]),
            commit=commit,
            ref=str(payload["ref"]),
            checkout_role=str(payload["checkout_role"]),
            checkout_path=str(payload["checkout_path"]),
            worktree_clean=True,
            dirty_path_count=0,
            verified_at=parsed_verified_at.astimezone(UTC),
            receipt_id=str(payload["receipt_id"]),
        )


@dataclass(frozen=True)
class ProducerPreflightResult:
    state: str
    checks: dict[str, str]
    evidence: ProducerEvidence | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "state": self.state,
            "checks": dict(self.checks),
        }
        if self.evidence is not None:
            payload.update(self.evidence.to_dict())
        if self.detail:
            payload["detail"] = self.detail
        return payload


def inspect_canonical_producer(
    *,
    repo_root: Path,
    expected_repository: str,
    expected_ref: str,
    checkout_role: str,
    now: datetime | None = None,
) -> ProducerPreflightResult:
    checks: dict[str, str] = {}
    try:
        repository = _origin_repository(repo_root)
        commit = _git(repo_root, "rev-parse", "HEAD")
        expected_commit = _git(repo_root, "rev-parse", "--verify", expected_ref)
        status = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.CalledProcessError) as exc:
        return ProducerPreflightResult(
            state="unknown",
            checks={"expected_ref_available": "unknown"},
            detail=str(exc),
        )

    checks["repository_identity"] = (
        "pass" if repository == expected_repository else "fail"
    )
    checks["worktree_clean"] = "pass" if not status else "fail"
    checks["expected_ref_available"] = "pass"
    checks["head_matches_expected_ref"] = (
        "pass" if commit == expected_commit else "fail"
    )
    state = "pass" if all(value == "pass" for value in checks.values()) else "fail"
    verified_at = now or datetime.now(UTC)
    dirty_path_count = len(status.splitlines()) if status else 0
    receipt_material = "\n".join(
        (repository, commit, expected_ref, checkout_role, str(repo_root.resolve()), verified_at.isoformat())
    )
    evidence = ProducerEvidence(
        repository=repository,
        commit=commit,
        ref=expected_ref,
        checkout_role=checkout_role,
        checkout_path=str(repo_root.resolve()),
        worktree_clean=not status,
        dirty_path_count=dirty_path_count,
        verified_at=verified_at,
        receipt_id=f"sha256:{hashlib.sha256(receipt_material.encode()).hexdigest()}",
    )
    return ProducerPreflightResult(state=state, checks=checks, evidence=evidence)


def verify_evidence_still_current(repo_root: Path, evidence: ProducerEvidence) -> None:
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != evidence.commit:
        raise ValueError(
            "Producer HEAD changed after preflight: "
            f"verified={evidence.commit}; current={current}"
        )
    if str(repo_root.resolve()) != evidence.checkout_path:
        raise ValueError(
            "Producer checkout changed after preflight: "
            f"verified={evidence.checkout_path}; current={repo_root.resolve()}"
        )
    status = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("Producer worktree became dirty after preflight.")


def load_producer_evidence(path: Path) -> ProducerEvidence:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"Producer evidence file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Producer evidence file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Producer evidence root must be a JSON object.")
    if payload.get("schema_version") != PREFLIGHT_SCHEMA_VERSION:
        raise ValueError(
            "Producer evidence schema mismatch: "
            f"declared={payload.get('schema_version')!r}; expected={PREFLIGHT_SCHEMA_VERSION!r}"
        )
    if payload.get("state") != "pass":
        raise ValueError(
            f"Producer evidence did not pass preflight: state={payload.get('state')!r}"
        )
    return ProducerEvidence.from_dict(payload)


def _origin_repository(repo_root: Path) -> str:
    remote = _git(repo_root, "remote", "get-url", "origin")
    if remote.startswith("git@") and ":" in remote:
        path = remote.split(":", 1)[1]
    else:
        path = urlparse(remote).path
    return path.strip("/").removesuffix(".git")


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate canonical GHRA producer identity.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-ref", required=True)
    parser.add_argument("--checkout-role", default="canonical-automation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = inspect_canonical_producer(
        repo_root=args.repo_root,
        expected_repository=args.expected_repository,
        expected_ref=args.expected_ref,
        checkout_role=args.checkout_role,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"GHRA producer preflight: {result.state.upper()}")
        for check, state in result.checks.items():
            print(f"- {check}: {state}")
        if result.detail:
            print(result.detail)
    return 0 if result.state == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
