"""Derive the prospective default-attention cohort for one governed transition.

The collector cannot derive its denominator from the truth it is about to
replace: that is the circular dependency that made every cohort boundary
uncrossable. This module derives the *prospective* cohort from current source at
the pinned producer revision, using the producer's own candidate machinery, and
emits a small `PortfolioCohortPlanV1`.

The plan is **not** PortfolioTruth. It carries no project data, never authorizes
portfolio state, and lives beside the security receipt rather than in the truth
lineage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from github_repo_auditor.portfolio_cohort_plan_contract import (
    CohortPlanError,
    build_cohort_plan_payload,
    validate_cohort_plan,
)
from github_repo_auditor.github_security_coverage import (
    DEFAULT_COHORT_POLICY,
    DEFAULT_MAX_COHORT_DELTA,
    DEFAULT_MAX_COHORT_SIZE,
)
from github_repo_auditor.portfolio_truth_publish import (
    PortfolioTruthPublishError,
    load_prior_security_evidence,
)
from github_repo_auditor.portfolio_truth_reconcile import (
    build_materialization_context,
    derive_candidate_cohort,
)
from github_repo_auditor.portfolio_truth_status import (
    load_live_repo_status_by_name,
    load_repo_status_from_audit_by_name,
)

PRODUCER_REPOSITORY = "saagpatel/GithubRepoAuditor"

_COMMIT_LENGTH = 40


class CohortPlanDerivationError(RuntimeError):
    """Raised when a prospective cohort cannot be derived from current source."""


def _resolve_producer_commit(repo_root: Path, declared: str | None) -> str:
    commit = declared
    if not commit:
        try:
            commit = subprocess.run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CohortPlanDerivationError(
                "producer commit unavailable; refusing an unproven cohort plan"
            ) from exc
    if len(commit) != _COMMIT_LENGTH or any(
        character not in "0123456789abcdef" for character in commit
    ):
        raise CohortPlanDerivationError(
            "producer commit is invalid; refusing an unproven cohort plan"
        )
    return commit


def build_cohort_plan(
    *,
    truth_path: Path,
    workspace_root: Path,
    catalog_path: Path,
    output_dir: Path,
    username: str,
    producer_commit: str,
    repo_root: Path,
    security_max_age_hours: int = 24,
    include_notion: bool = True,
    now: datetime | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
) -> dict:
    """Return a signed `PortfolioCohortPlanV1` payload for the next collection."""
    generated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        truth_bytes = truth_path.read_bytes()
    except OSError as exc:
        raise CohortPlanDerivationError(
            f"prior PortfolioTruth is unreadable: {truth_path}: {exc}"
        ) from exc
    prior_truth_sha256 = hashlib.sha256(truth_bytes).hexdigest()

    try:
        prior_evidence = load_prior_security_evidence(
            truth_path,
            security_max_age_hours=security_max_age_hours,
        )
    except PortfolioTruthPublishError as exc:
        raise CohortPlanDerivationError(
            f"prior PortfolioTruth cannot authorize cohort planning: {exc}"
        ) from exc
    if prior_evidence.final_cohort_repositories is None:
        raise CohortPlanDerivationError(
            "prior PortfolioTruth carries no published default-attention cohort"
        )
    if prior_evidence.generated_at is None:
        raise CohortPlanDerivationError(
            "prior PortfolioTruth carries no generated_at provenance"
        )

    if repo_status_by_name is None:
        # Credential-posture parity with the producer: no token is passed here,
        # and the collector keeps GITHUB_TOKEN out of this step's environment, so
        # the plan and the 02:00 candidate pass see the same repository set.
        repo_status_by_name = load_live_repo_status_by_name(
            username=username,
            token=None,
            cache=None,
        )
        if repo_status_by_name is None:
            repo_status_by_name = load_repo_status_from_audit_by_name(
                output_dir=output_dir,
                username=username,
            )

    context = build_materialization_context(
        workspace_root=workspace_root,
        catalog_path=catalog_path,
        legacy_registry_path=workspace_root / "project-registry.md",
        include_notion=include_notion,
        now=generated_at,
    )
    candidate = derive_candidate_cohort(
        context,
        prior_security_alerts_by_name=prior_evidence.alerts_by_full_name,
        prior_security_cohort_repositories=prior_evidence.final_cohort_repositories,
        repo_status_by_name=repo_status_by_name,
    )

    catalog_source = context.catalog_data.get("path")
    catalog_bytes = (
        Path(str(catalog_source)).read_bytes()
        if catalog_source and Path(str(catalog_source)).is_file()
        else b""
    )
    payload = build_cohort_plan_payload(
        generated_at=generated_at,
        producer_commit=producer_commit,
        producer_repository=PRODUCER_REPOSITORY,
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        workspace_root=workspace_root.as_posix(),
        prior_truth_path=str(truth_path),
        prior_truth_sha256=prior_truth_sha256,
        prior_truth_generated_at=prior_evidence.generated_at.isoformat(),
        policy=DEFAULT_COHORT_POLICY,
        prospective_repositories=candidate.repositories,
        prior_published_repositories=prior_evidence.final_cohort_repositories,
    )
    # Refuse to emit a plan the collector would reject.
    validate_cohort_plan(payload)
    return payload


def write_cohort_plan(payload: dict, path: Path) -> str:
    """Atomically write a validated plan and return its content digest."""
    validate_cohort_plan(payload)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return hashlib.sha256(serialized).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive the prospective default-attention cohort plan consumed by "
            "bounded GitHub security collection"
        )
    )
    parser.add_argument(
        "--truth",
        type=Path,
        default=Path("output/portfolio-truth-latest.json"),
        help="Published PortfolioTruth whose final cohort is the prior set",
    )
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument(
        "--workspace-root", type=Path, default=Path("/Users/d/Projects")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/portfolio-cohort-plan-latest.json"),
    )
    parser.add_argument("--username", default="saagpatel")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--producer-commit",
        default=None,
        help="Override the derived producer commit (defaults to repo HEAD)",
    )
    parser.add_argument("--security-max-age-hours", type=int, default=24)
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="Skip Notion context; only for isolated derivation tests",
    )
    args = parser.parse_args()

    catalog_path = args.catalog or (args.repo_root / "config/portfolio-catalog.yaml")
    try:
        producer_commit = _resolve_producer_commit(args.repo_root, args.producer_commit)
        payload = build_cohort_plan(
            truth_path=args.truth,
            workspace_root=args.workspace_root,
            catalog_path=catalog_path,
            output_dir=args.output_dir,
            username=args.username,
            producer_commit=producer_commit,
            repo_root=args.repo_root,
            security_max_age_hours=args.security_max_age_hours,
            include_notion=not args.no_notion,
        )
        content_sha256 = write_cohort_plan(payload, args.output)
    except (CohortPlanDerivationError, CohortPlanError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    cohort = payload["cohort"]
    print(
        json.dumps(
            {
                "state": "written",
                "path": str(args.output),
                "plan_id": payload["plan_id"],
                "content_sha256": content_sha256,
                "producer_commit": producer_commit,
                "prior_truth_sha256": payload["source"]["prior_truth_sha256"],
                "transition_kind": cohort["transition_kind"],
                "required_count": len(cohort["required_repositories"]),
                "outgoing_count": len(cohort["outgoing_repositories"]),
                "incoming_count": len(cohort["incoming_repositories"]),
                "collection_count": len(cohort["collection_repositories"]),
                "max_cohort_size": DEFAULT_MAX_COHORT_SIZE,
                "max_cohort_delta": DEFAULT_MAX_COHORT_DELTA,
            },
            indent=2,
        )
    )


if __name__ == "__main__":  # pragma: no cover - module entry point
    main()
