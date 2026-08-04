from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.portfolio_truth_types import CHECKOUT_COLLISION_SCHEMA_VERSION


@dataclass(frozen=True)
class ValidatedCheckoutAuthority:
    origin: str
    checkout_count: int
    full_clone_count: int
    state: str
    reason_code: str
    canonical_project_path: str
    representative_path: str
    selected_path: str | None
    discarded_count: int


def validate_checkout_authority_envelope(
    authority: object,
    *,
    identity_path: str | None = None,
    repo_full_name: str | None = None,
) -> ValidatedCheckoutAuthority:
    """Validate the complete CheckoutCollisionV1 group and its path binding."""
    if not isinstance(authority, Mapping):
        raise ValueError("Checkout collision group must be an object.")
    required_group = {
        "schema_version",
        "origin",
        "canonical_project_path",
        "checkout_count",
        "full_clone_count",
        "declared_checkout_paths",
        "declared_path_evidence",
        "unresolved_declared_paths",
        "selection",
        "checkouts",
        "discarded_checkouts",
    }
    missing = sorted(required_group - authority.keys())
    if missing:
        raise ValueError(f"Checkout collision group is missing fields: {missing}")
    if authority.get("schema_version") != CHECKOUT_COLLISION_SCHEMA_VERSION:
        raise ValueError("Unexpected checkout collision schema version.")

    origin = authority.get("origin")
    if not isinstance(origin, str) or not origin.strip():
        raise ValueError("Checkout collision origin must be non-empty.")
    if repo_full_name and origin.lower() != repo_full_name.lower():
        raise ValueError("Checkout collision origin differs from project identity.")
    canonical_project_path = _require_relative_path(
        authority.get("canonical_project_path"),
        "checkout canonical_project_path",
    )
    if identity_path is not None and canonical_project_path != identity_path:
        raise ValueError("Canonical project path differs from collision identity.")

    checkout_count = _require_nonnegative_count(authority, "checkout_count")
    full_clone_count = _require_nonnegative_count(authority, "full_clone_count")
    if checkout_count < 1:
        raise ValueError("Checkout authority groups require at least one checkout.")
    if not 1 <= full_clone_count <= checkout_count:
        raise ValueError("Checkout collision full_clone_count is out of range.")

    selection = authority.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("Checkout collision selection must be an object.")
    for key in (
        "state",
        "reason_code",
        "reason",
        "representative_path",
        "selected_path",
        "rationale",
    ):
        if key not in selection:
            raise ValueError(f"Checkout collision selection is missing {key}.")
    state = selection.get("state")
    if state not in {"selected", "unknown"}:
        raise ValueError(f"Invalid checkout authority state: {state}")
    representative_path = _require_relative_path(
        selection.get("representative_path"),
        "checkout representative_path",
    )
    selected_path = selection.get("selected_path")
    if state == "unknown":
        if selected_path is not None:
            raise ValueError("UNKNOWN checkout authority cannot select a path.")
    elif selected_path != representative_path:
        raise ValueError("Selected checkout path must equal the representative path.")
    for key in ("reason_code", "reason", "rationale"):
        if not isinstance(selection.get(key), str) or not selection[key].strip():
            raise ValueError(
                f"Checkout collision selection {key} must be non-empty."
            )

    checkouts = authority.get("checkouts")
    discarded = authority.get("discarded_checkouts")
    if not isinstance(checkouts, list) or len(checkouts) != checkout_count:
        raise ValueError("Checkout collision checkouts do not match checkout_count.")
    if not isinstance(discarded, list):
        raise ValueError("Discarded checkouts must be a list.")
    checkout_paths: set[str] = set()
    representative_count = 0
    for checkout in checkouts:
        if not isinstance(checkout, Mapping):
            raise ValueError("Checkout collision checkout must be an object.")
        required_checkout = {
            "path",
            "state",
            "relation",
            "head",
            "branch",
            "dirty",
            "dirty_path_count",
            "bare",
        }
        missing_checkout = sorted(required_checkout - checkout.keys())
        if missing_checkout:
            raise ValueError(
                f"Checkout collision checkout is missing fields: {missing_checkout}"
            )
        path = _require_relative_path(checkout.get("path"), "checkout path")
        if path in checkout_paths:
            raise ValueError(f"Duplicate checkout collision path: {path}")
        checkout_paths.add(path)
        if checkout.get("state") not in {"observed", "unknown"}:
            raise ValueError("Invalid checkout observation state.")
        relation = checkout.get("relation")
        if relation not in {
            "representative",
            "linked_worktree",
            "independent_full_clone",
        }:
            raise ValueError("Invalid checkout relation.")
        representative_count += int(relation == "representative")
        head = checkout.get("head")
        if head is not None and not re.fullmatch(
            r"[0-9a-f]{40}|[0-9a-f]{64}", str(head)
        ):
            raise ValueError(f"Malformed checkout head for {path}.")
        branch = checkout.get("branch")
        if branch is not None and not isinstance(branch, str):
            raise ValueError(f"Malformed checkout branch for {path}.")
        dirty = checkout.get("dirty")
        if dirty is not None and not isinstance(dirty, bool):
            raise ValueError(f"Malformed checkout dirty state for {path}.")
        dirty_count = checkout.get("dirty_path_count")
        if dirty_count is not None and (
            isinstance(dirty_count, bool)
            or not isinstance(dirty_count, int)
            or dirty_count < 0
        ):
            raise ValueError(f"Malformed checkout dirty_path_count for {path}.")
        bare = checkout.get("bare")
        if bare is not None and not isinstance(bare, bool):
            raise ValueError(f"Malformed checkout bare state for {path}.")
        if checkout.get("state") == "observed" and not isinstance(bare, bool):
            raise ValueError(f"Observed checkout must declare bare state for {path}.")
        if state == "selected":
            if checkout.get("state") != "observed":
                raise ValueError(
                    "Selected checkout authority requires complete observations."
                )
            if bare is False and (dirty is not False or dirty_count != 0):
                raise ValueError(
                    "Selected checkout authority cannot contain local work."
                )

    representative_checkout = next(
        (
            checkout
            for checkout in checkouts
            if checkout["path"] == representative_path
        ),
        None,
    )
    if (
        representative_count != 1
        or representative_checkout is None
        or representative_checkout["relation"] != "representative"
        or (
            state == "selected"
            and (
                representative_checkout["state"] != "observed"
                or representative_checkout["bare"] is not False
            )
        )
    ):
        raise ValueError("Checkout collision requires one observed representative.")
    expected_discarded = [
        checkout
        for checkout in checkouts
        if checkout["path"] != representative_path
    ]
    if discarded != expected_discarded:
        raise ValueError("Discarded checkout evidence does not match the checkout set.")

    declared_paths = authority.get("declared_checkout_paths")
    unresolved_paths = authority.get("unresolved_declared_paths")
    declared_evidence = authority.get("declared_path_evidence")
    if not isinstance(declared_paths, list) or not isinstance(
        unresolved_paths, list
    ):
        raise ValueError("Declared checkout paths must be lists.")
    for path in declared_paths + unresolved_paths:
        _require_relative_path(path, "declared checkout path")
    if not isinstance(declared_evidence, list):
        raise ValueError("Declared path evidence must be a list.")
    for item in declared_evidence:
        if not isinstance(item, Mapping):
            raise ValueError("Declared path evidence must be an object.")
        _require_relative_path(item.get("source_path"), "declared source path")
        target = _require_relative_path(
            item.get("target_checkout_path"), "declared target checkout path"
        )
        if target not in checkout_paths:
            raise ValueError("Declared checkout target is not in the collision group.")
    expected_declared_paths = sorted(
        {item["target_checkout_path"] for item in declared_evidence},
        key=str.lower,
    )
    if declared_paths != expected_declared_paths:
        raise ValueError("Declared checkout paths do not match declared path evidence.")
    topology_failure = (
        state == "unknown"
        and selection.get("reason_code") == "worktree_enumeration_failed"
    )
    if checkout_count == 1 and not (
        declared_evidence or unresolved_paths or topology_failure
    ):
        raise ValueError(
            "Single-checkout authority groups require declaration or "
            "topology-failure evidence."
        )

    return ValidatedCheckoutAuthority(
        origin=origin,
        checkout_count=checkout_count,
        full_clone_count=full_clone_count,
        state=str(state),
        reason_code=str(selection["reason_code"]),
        canonical_project_path=canonical_project_path,
        representative_path=representative_path,
        selected_path=str(selected_path) if selected_path is not None else None,
        discarded_count=len(discarded),
    )


def _require_nonnegative_count(value: Mapping[str, Any], key: str) -> int:
    count = value.get(key)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"{key} must be a non-negative integer.")
    return count


def _require_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must stay workspace-relative.")
    return value


def checkout_authority_blocker(
    project: Any,
    *,
    workspace_root: Path | None = None,
) -> str | None:
    """Return a stable automation blocker for unresolved checkout authority.

    Legacy inputs without topology evidence keep their existing behavior. Fresh
    repository topology fails closed when observation is unknown or multiple
    worktrees lack matching collision authority. Once collision evidence is
    present, malformed, UNKNOWN, or path-mismatched selection also fails closed.
    """
    identity = _project_section(project, "identity")
    repository_state = _project_section(project, "repository_state")
    authority = repository_state.get("checkout_authority")
    if authority is None:
        return _repository_topology_blocker(repository_state, authority=None)
    project_path = str(identity.get("path") or "")
    repo_full_name = str(identity.get("repo_full_name") or "")
    try:
        validated = validate_checkout_authority_envelope(
            authority,
            identity_path=project_path,
            repo_full_name=repo_full_name or None,
        )
    except ValueError:
        return "checkout-authority-malformed"
    if validated.state != "selected":
        return f"checkout-authority-unknown:{validated.reason_code}"
    selected_path = validated.selected_path
    if selected_path is None:
        return "checkout-authority-malformed"

    if workspace_root is not None:
        try:
            resolved_root = workspace_root.resolve()
            resolved_target = (workspace_root / selected_path).resolve()
            resolved_target.relative_to(resolved_root)
        except (OSError, ValueError):
            return "checkout-authority-path-escape"
    return _repository_topology_blocker(repository_state, authority=authority)


def checkout_authority_path(project: Any) -> str:
    """Return the selected checkout path while keeping canonical project identity."""
    identity = _project_section(project, "identity")
    project_path = str(identity.get("path") or "")
    repository_state = _project_section(project, "repository_state")
    authority = repository_state.get("checkout_authority")
    repo_full_name = str(identity.get("repo_full_name") or "")
    try:
        validated = validate_checkout_authority_envelope(
            authority,
            identity_path=project_path,
            repo_full_name=repo_full_name or None,
        )
    except ValueError:
        return project_path
    if validated.state == "selected" and validated.selected_path is not None:
        return validated.selected_path
    return project_path


def _repository_topology_blocker(
    repository_state: Mapping[str, Any],
    *,
    authority: Mapping[str, Any] | None,
) -> str | None:
    state = str(repository_state.get("state") or "")
    if state == "unknown":
        reason_code = str(
            repository_state.get("reason_code") or "repository_observation_failed"
        )
        return f"checkout-topology-unknown:{reason_code}"

    worktrees = repository_state.get("worktrees")
    if worktrees is None:
        return None
    if not isinstance(worktrees, list) or any(
        not isinstance(item, Mapping) for item in worktrees
    ):
        return "checkout-topology-malformed"
    if len(worktrees) <= 1:
        return None
    if authority is None:
        return "checkout-authority-missing:multiple-worktrees"
    if any(item.get("state") not in {"observed", "coordinator"} for item in worktrees):
        return "checkout-topology-unknown:worktree_observation_failed"
    if any(item.get("dirty") is True for item in worktrees):
        return "checkout-topology-local-work-present"

    authority_checkouts = authority.get("checkouts")
    if not isinstance(authority_checkouts, list):
        return "checkout-authority-malformed"
    representative_clone_count = sum(
        isinstance(item, Mapping)
        and item.get("relation") in {"representative", "linked_worktree"}
        for item in authority_checkouts
    )
    if representative_clone_count != len(worktrees):
        return "checkout-authority-topology-mismatch"
    return None


def _project_section(project: Any, name: str) -> Mapping[str, Any]:
    if isinstance(project, Mapping):
        value = project.get(name)
    else:
        value = getattr(project, name, None)
    if isinstance(value, Mapping):
        return value
    if value is not None and hasattr(value, "__dict__"):
        return vars(value)
    return {}
