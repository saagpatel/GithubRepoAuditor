from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PREFLIGHT_SCHEMA_VERSION = "ghra_producer_preflight.v1"


@dataclass(frozen=True)
class ProducerEvidence:
    repository: str
    commit: str
    ref: str
    checkout_role: str
    worktree_clean: bool
    verified_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "commit": self.commit,
            "ref": self.ref,
            "checkout_role": self.checkout_role,
            "worktree_clean": self.worktree_clean,
            "verified_at": self.verified_at.isoformat(),
        }


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
    evidence = ProducerEvidence(
        repository=repository,
        commit=commit,
        ref=expected_ref,
        checkout_role=checkout_role,
        worktree_clean=not status,
        verified_at=now or datetime.now(UTC),
    )
    return ProducerPreflightResult(state=state, checks=checks, evidence=evidence)


def verify_evidence_still_current(repo_root: Path, evidence: ProducerEvidence) -> None:
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != evidence.commit:
        raise ValueError(
            "Producer HEAD changed after preflight: "
            f"verified={evidence.commit}; current={current}"
        )


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
