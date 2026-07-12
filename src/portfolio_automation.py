"""Bounded-automation eligibility + candidate selection (Arc D, phase 1).

This module is strictly advisory and read-only. It answers a single question
for each repo: *does it clear the automation trust bar?* A repo is eligible
only when ALL of the following hold:

* the portfolio's ``decision_quality_status`` is ``"trusted"`` (a portfolio-wide
  gate — when calibration is noisy/mixed/insufficient, nothing is eligible);
* the repo's ``path_confidence`` is ``"high"`` (its operating path is settled);
* the repo's ``activity_status`` is active or candidate (not archived/parked);
* the repo's ``context_quality`` is non-trivial (not boilerplate/none/unknown).

Selecting candidates does NOT propose or apply any change — proposal creation
(phase 2) and gated execution (phase 3) build on top of this signal layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CONTRACT_VERSION = "automation_candidates_v1"

# Trust-bar thresholds. Kept as module constants so later phases (proposal
# creation, execution re-checks) reuse the exact same gate.
TRUSTED_DECISION_QUALITY = "trusted"
ELIGIBLE_PATH_CONFIDENCE = frozenset({"high"})
ELIGIBLE_ACTIVITY_STATUS = frozenset({"active", "candidate"})
ELIGIBLE_CONTEXT_QUALITY = frozenset({"minimum-viable", "standard", "full"})

MAX_AUTOMATION_CANDIDATES = 25


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class AutomationEligibility:
    """Whether a repo clears the automation trust bar, with reasons if not."""

    eligible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class AutomationCandidate:
    """An eligible repo surfaced as a bounded-automation candidate."""

    display_name: str
    repo_full_name: str
    activity_status: str
    path_confidence: str
    context_quality: str

    def to_dict(self) -> dict[str, str]:
        return {
            "repo": self.display_name,
            "repo_full_name": self.repo_full_name,
            "activity_status": self.activity_status,
            "path_confidence": self.path_confidence,
            "context_quality": self.context_quality,
        }


def evaluate_automation_eligibility(
    project: dict[str, Any], *, decision_quality_status: str
) -> AutomationEligibility:
    """Evaluate a single truth project against the bounded-automation trust bar.

    ``decision_quality_status`` is the portfolio-level value (the same for every
    repo in a run); the remaining checks are per-repo. Blockers accumulate so
    the operator sees every reason a repo is held back, not just the first.
    """
    derived = _mapping(project.get("derived"))
    blockers: list[str] = []
    if _text(decision_quality_status) != TRUSTED_DECISION_QUALITY:
        blockers.append("decision-quality-not-trusted")
    if _text(derived.get("activity_status")) not in ELIGIBLE_ACTIVITY_STATUS:
        blockers.append("activity-status-not-eligible")
    if _text(derived.get("path_confidence")) not in ELIGIBLE_PATH_CONFIDENCE:
        blockers.append("path-confidence-not-high")
    if _text(derived.get("context_quality")) not in ELIGIBLE_CONTEXT_QUALITY:
        blockers.append("context-quality-too-weak")
    return AutomationEligibility(eligible=not blockers, blockers=tuple(blockers))


def select_automation_candidates(
    portfolio_truth: dict[str, Any], *, decision_quality_status: str
) -> list[AutomationCandidate]:
    """Return the eligible repos (sorted by display name, capped) as candidates."""
    projects = portfolio_truth.get("projects") or []
    candidates: list[AutomationCandidate] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        eligibility = evaluate_automation_eligibility(
            project, decision_quality_status=decision_quality_status
        )
        if not eligibility.eligible:
            continue
        identity = _mapping(project.get("identity"))
        derived = _mapping(project.get("derived"))
        candidates.append(
            AutomationCandidate(
                display_name=_text(identity.get("display_name")) or "Repo",
                repo_full_name=_text(identity.get("repo_full_name")),
                activity_status=_text(derived.get("activity_status")),
                path_confidence=_text(derived.get("path_confidence")),
                context_quality=_text(derived.get("context_quality")),
            )
        )
    candidates.sort(key=lambda candidate: candidate.display_name.lower())
    return candidates[:MAX_AUTOMATION_CANDIDATES]
