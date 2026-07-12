"""Read-side trends for the canonical portfolio-truth snapshot history.

The producer owns the truth artifact schema.  This module only reads existing
``portfolio-truth-*.json`` snapshots and derives movement, so it cannot change
scores, verdicts, rollups, or the producer's output contract.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_HISTORY_DIR = Path("output/history")
DEFAULT_MAX_SNAPSHOTS = 8
CONTRACT_VERSION = "portfolio_truth_trends_v1"
_TREND_FIELDS = ("attention_state", "activity_status", "risk_tier")


def load_portfolio_truth_history(
    history_dir: Path = DEFAULT_HISTORY_DIR,
    *,
    max_snapshots: int = DEFAULT_MAX_SNAPSHOTS,
) -> list[dict[str, Any]]:
    """Load the last ``max_snapshots`` valid truth artifacts chronologically.

    The current producer has emitted dated artifacts directly under ``output``
    while the original history contract names ``output/history``.  Both layouts
    are read, with the conventional ``portfolio-truth-latest.json`` pointer
    excluded because it is not a historical observation.
    """
    if max_snapshots < 1:
        return []

    candidates: dict[Path, dict[str, Any]] = {}
    for directory in _history_directories(history_dir):
        if not directory.is_dir():
            continue
        for path in directory.glob("portfolio-truth-*.json"):
            if path.name == "portfolio-truth-latest.json":
                continue
            payload = _read_mapping(path)
            if payload is None:
                continue
            generated_at = _text(payload.get("generated_at"))
            candidates[path.resolve()] = {
                "path": str(path),
                "generated_at": generated_at,
                "projects": list(payload.get("projects") or [])
                if isinstance(payload.get("projects"), list)
                else [],
            }

    snapshots = sorted(
        candidates.values(),
        key=lambda item: (item["generated_at"], item["path"]),
    )
    return snapshots[-max_snapshots:]


def build_verdict_transition_ledger(
    history_dir: Path = DEFAULT_HISTORY_DIR,
    *,
    max_snapshots: int = DEFAULT_MAX_SNAPSHOTS,
    current_snapshot: Mapping[str, Any] | None = None,
    current_path: Path | None = None,
) -> dict[str, Any]:
    """Derive truth-layer transitions from existing snapshot history.

    ``current_snapshot`` is useful to callers that have already loaded the
    canonical ``portfolio-truth-latest.json`` pointer.  It is merged into the
    read window by generated timestamp and does not get written anywhere.
    """
    snapshots = load_portfolio_truth_history(history_dir, max_snapshots=max_snapshots)
    if current_snapshot is not None and max_snapshots > 0:
        snapshots = _with_current_snapshot(
            snapshots,
            current_snapshot,
            current_path=current_path,
            max_snapshots=max_snapshots,
        )

    observations = [_snapshot_observations(snapshot) for snapshot in snapshots]
    transitions = _build_transitions(snapshots, observations)
    activity_streaks = _build_activity_streaks(snapshots, observations)
    attention_transitions = [
        item for item in transitions if item["kind"] == "attention_state"
    ]
    activity_transitions = [
        item for item in transitions if item["kind"] == "activity_status"
    ]
    risk_changes = [item for item in transitions if item["kind"] == "risk_tier"]
    lifecycle_events = [
        item for item in transitions if item["kind"] == "repo_lifecycle"
    ]

    return {
        "contract_version": CONTRACT_VERSION,
        "snapshot_count": len(snapshots),
        "window_size": max_snapshots,
        "from_generated_at": snapshots[0]["generated_at"] if snapshots else "",
        "to_generated_at": snapshots[-1]["generated_at"] if snapshots else "",
        "transitions": transitions,
        "attention_state_transitions": attention_transitions,
        "activity_status_transitions": activity_transitions,
        "activity_status_streaks": activity_streaks,
        "risk_tier_changes": risk_changes,
        "repo_lifecycle_events": lifecycle_events,
        "summary": {
            "transition_count": len(transitions),
            "attention_state_transition_count": len(attention_transitions),
            "activity_status_transition_count": len(activity_transitions),
            "risk_tier_change_count": len(risk_changes),
            "repo_appeared_count": sum(
                item["to"] == "present" for item in lifecycle_events
            ),
            "repo_disappeared_count": sum(
                item["to"] == "absent" for item in lifecycle_events
            ),
        },
    }


def render_movement_summary(ledger: Mapping[str, Any]) -> str:
    """Render a compact human-readable summary for the weekly digest."""
    transitions = list(ledger.get("transitions") or [])
    if not transitions:
        return "No verdict movement is recorded across the available truth snapshots."

    grouped: dict[tuple[str, str, str], int] = defaultdict(int)
    for item in transitions:
        kind = _text(item.get("kind"))
        if kind == "repo_lifecycle":
            grouped[(kind, _text(item.get("from")), _text(item.get("to")))] += 1
        else:
            grouped[(kind, _text(item.get("from")), _text(item.get("to")))] += 1

    clauses: list[str] = []
    for (kind, previous, current), count in sorted(grouped.items()):
        transition = f"{previous}→{current}"
        if kind == "repo_lifecycle":
            verb = "appeared" if current == "present" else "disappeared"
            clauses.append(f"{count} repo{'s' if count != 1 else ''} {verb}")
        elif kind == "activity_status":
            verb = _movement_verb(previous, current)
            clauses.append(f"{count} repo{'s' if count != 1 else ''} {verb} {transition}")
        elif kind == "attention_state":
            verb = _movement_verb(previous, current)
            clauses.append(f"{count} repo{'s' if count != 1 else ''} {verb} {transition}")
        elif kind == "risk_tier":
            clauses.append(
                f"{count} risk-tier change{'s' if count != 1 else ''} {transition}"
            )

    return "; ".join(clauses) + "."


def _history_directories(history_dir: Path) -> list[Path]:
    directories = [history_dir]
    if history_dir.name != "history":
        directories.append(history_dir / "history")
    else:
        directories.append(history_dir.parent)
    return list(dict.fromkeys(directory for directory in directories))


def _with_current_snapshot(
    snapshots: Sequence[dict[str, Any]],
    current_snapshot: Mapping[str, Any],
    *,
    current_path: Path | None,
    max_snapshots: int,
) -> list[dict[str, Any]]:
    generated_at = _text(current_snapshot.get("generated_at"))
    if not generated_at:
        return list(snapshots)[-max_snapshots:]
    current = {
        "path": str(current_path) if current_path else "<current>",
        "generated_at": generated_at,
        "projects": list(current_snapshot.get("projects") or [])
        if isinstance(current_snapshot.get("projects"), list)
        else [],
    }
    merged = [snapshot for snapshot in snapshots if snapshot["generated_at"] != generated_at]
    merged.append(current)
    merged.sort(key=lambda item: (item["generated_at"], item["path"]))
    return merged[-max_snapshots:]


def _snapshot_observations(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for project in snapshot.get("projects") or []:
        if not isinstance(project, Mapping):
            continue
        identity = _mapping(project.get("identity"))
        derived = _mapping(project.get("derived"))
        risk = _mapping(project.get("risk"))
        project_key = (
            _text(identity.get("project_key"))
            or _text(identity.get("repo_full_name"))
            or _text(identity.get("display_name"))
        )
        if not project_key:
            continue
        observations[project_key] = {
            "repo": _text(identity.get("display_name")) or project_key,
            "project_key": project_key,
            "attention_state": _value(derived.get("attention_state")),
            "activity_status": _value(derived.get("activity_status")),
            "risk_tier": _value(risk.get("risk_tier")),
        }
    return observations


def _build_transitions(
    snapshots: Sequence[Mapping[str, Any]],
    observations: Sequence[dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for index in range(1, len(snapshots)):
        previous = observations[index - 1]
        current = observations[index]
        previous_at = _text(snapshots[index - 1].get("generated_at"))
        current_at = _text(snapshots[index].get("generated_at"))
        for project_key in sorted(set(previous) | set(current)):
            before = previous.get(project_key)
            after = current.get(project_key)
            if before is None or after is None:
                transitions.append(
                    _transition(
                        project_key=project_key,
                        repo=(after or before)["repo"],
                        kind="repo_lifecycle",
                        previous="present" if before else "absent",
                        current="present" if after else "absent",
                        previous_at=previous_at,
                        current_at=current_at,
                    )
                )
                continue
            for field in _TREND_FIELDS:
                if before[field] == after[field]:
                    continue
                transitions.append(
                    _transition(
                        project_key=project_key,
                        repo=after["repo"],
                        kind=field,
                        previous=before[field],
                        current=after[field],
                        previous_at=previous_at,
                        current_at=current_at,
                    )
                )
    transitions.sort(
        key=lambda item: (
            item["to_generated_at"],
            item["repo"].lower(),
            item["kind"],
        )
    )
    return transitions


def _build_activity_streaks(
    snapshots: Sequence[Mapping[str, Any]],
    observations: Sequence[dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    keys = sorted({project_key for snapshot in observations for project_key in snapshot})
    streaks: list[dict[str, Any]] = []
    for project_key in keys:
        present = [
            (index, snapshot[project_key])
            for index, snapshot in enumerate(observations)
            if project_key in snapshot
        ]
        if not present:
            continue
        latest_index, latest = present[-1]
        if latest_index != len(observations) - 1:
            status = "disappeared"
            run_count = 1
            since_index = latest_index
        else:
            status = latest["activity_status"] or "unknown"
            run_count = 0
            since_index = latest_index
            for index, observation in reversed(present):
                if index != since_index or observation["activity_status"] != status:
                    break
                run_count += 1
                since_index = index - 1
            since_index += 1
        streaks.append(
            {
                "repo": latest["repo"],
                "project_key": project_key,
                "status": status,
                "run_count": run_count,
                "consecutive_snapshots": run_count,
                "since_generated_at": (
                    _text(snapshots[since_index].get("generated_at"))
                    if snapshots
                    else ""
                ),
                "through_generated_at": (
                    _text(snapshots[-1].get("generated_at")) if snapshots else ""
                ),
            }
        )
    return streaks


def _transition(
    *,
    project_key: str,
    repo: str,
    kind: str,
    previous: str | None,
    current: str | None,
    previous_at: str,
    current_at: str,
) -> dict[str, Any]:
    return {
        "repo": repo,
        "project_key": project_key,
        "kind": kind,
        "from": previous,
        "to": current,
        "from_date": previous_at[:10],
        "to_date": current_at[:10],
        "from_generated_at": previous_at,
        "to_generated_at": current_at,
    }


def _movement_verb(previous: str, current: str) -> str:
    if previous in {"active", "recent", "active-product", "active-infra"} and current in {
        "stale",
        "archived",
        "manual-only",
    }:
        return "slid"
    if previous in {"stale", "archived", "manual-only", "decision-needed"} and current in {
        "active",
        "recent",
        "active-product",
        "active-infra",
    }:
        return "recovered"
    return "changed"


def _read_mapping(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _value(value: Any) -> str | None:
    text = _text(value)
    return text or None
