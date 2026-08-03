from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.portfolio_truth_types import CHECKOUT_COLLISION_SCHEMA_VERSION


def checkout_authority_blocker(
    project: Any,
    *,
    workspace_root: Path | None = None,
) -> str | None:
    """Return a stable automation blocker for unresolved checkout authority.

    Projects without collision evidence are single-checkout/legacy inputs and keep
    their existing behavior. Once collision evidence is present, malformed,
    UNKNOWN, or path-mismatched selection fails closed.
    """
    identity = _project_section(project, "identity")
    repository_state = _project_section(project, "repository_state")
    authority = repository_state.get("checkout_authority")
    if authority is None:
        return None
    if not isinstance(authority, Mapping):
        return "checkout-authority-malformed"
    if authority.get("schema_version") != CHECKOUT_COLLISION_SCHEMA_VERSION:
        return "checkout-authority-malformed"
    selection = authority.get("selection")
    if not isinstance(selection, Mapping):
        return "checkout-authority-malformed"

    state = str(selection.get("state") or "unknown")
    reason_code = str(selection.get("reason_code") or "unspecified")
    if state != "selected":
        return f"checkout-authority-unknown:{reason_code}"

    project_path = str(identity.get("path") or "")
    selected_path = str(selection.get("selected_path") or "")
    representative_path = str(selection.get("representative_path") or "")
    if (
        not project_path
        or selected_path != project_path
        or representative_path != project_path
    ):
        return "checkout-authority-path-mismatch"

    checkouts = authority.get("checkouts")
    if not isinstance(checkouts, list):
        return "checkout-authority-malformed"
    selected_checkouts = [
        checkout
        for checkout in checkouts
        if isinstance(checkout, Mapping) and checkout.get("path") == selected_path
    ]
    if len(selected_checkouts) != 1:
        return "checkout-authority-malformed"
    selected_checkout = selected_checkouts[0]
    if (
        selected_checkout.get("state") != "observed"
        or selected_checkout.get("relation") != "representative"
    ):
        return "checkout-authority-malformed"

    if workspace_root is not None:
        try:
            resolved_root = workspace_root.resolve()
            resolved_target = (workspace_root / project_path).resolve()
            resolved_target.relative_to(resolved_root)
        except (OSError, ValueError):
            return "checkout-authority-path-escape"
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
