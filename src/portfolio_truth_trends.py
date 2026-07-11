from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_HISTORY_RUNS = 8
DEFAULT_HISTORY_DIR = Path("output/history")

_ACTIVITY_ORDER = {"active": 0, "recent": 1, "stale": 2, "archived": 3}
_ATTENTION_ORDER = {
    "active-product": 0,
    "active-infra": 1,
    "manual-only": 2,
    "decision-needed": 3,
    "parked": 4,
    "archived": 5,
}
_RISK_ORDER = {"baseline": 0, "moderate": 1, "elevated": 2, "deferred": 3}


@dataclass(frozen=True)
class _TruthSnapshot:
    generated_at: str
    projects: dict[str, dict[str, str]]

    @property
    def date(self) -> str:
        return self.generated_at.split("T", 1)[0] if self.generated_at else "unknown"


def load_portfolio_truth_history(
    history_dir: Path = DEFAULT_HISTORY_DIR,
    *,
    max_runs: int = DEFAULT_HISTORY_RUNS,
) -> list[dict[str, Any]]:
    """Load the last N valid truth snapshots in chronological history order.

    The returned records intentionally contain only the state dimensions needed for
    movement reporting. Invalid or incomplete artifacts are ignored so one damaged
    historical file cannot make the weekly digest disappear.
    """
    if max_runs <= 0 or not history_dir.is_dir():
        return []

    snapshots: list[_TruthSnapshot] = []
    for path in sorted(history_dir.glob("portfolio-truth-*.json")):
        snapshot = _load_snapshot(path)
        if snapshot is not None:
            snapshots.append(snapshot)

    snapshots.sort(key=lambda snapshot: (snapshot.generated_at, sorted(snapshot.projects)))
    return [
        {
            "generated_at": snapshot.generated_at,
            "projects": snapshot.projects,
        }
        for snapshot in snapshots[-max_runs:]
    ]


def build_truth_movement(
    history_dir: Path = DEFAULT_HISTORY_DIR,
    *,
    max_runs: int = DEFAULT_HISTORY_RUNS,
) -> dict[str, Any]:
    """Build report-only movement facts from recent portfolio-truth artifacts."""
    snapshots = [
        _snapshot_from_record(record)
        for record in load_portfolio_truth_history(history_dir, max_runs=max_runs)
    ]
    repo_names = sorted({name for snapshot in snapshots for name in snapshot.projects})
    repos = [
        {
            "repo": repo,
            "attention_lane_transitions": _build_transitions(
                snapshots, repo, lambda state: state.get("attention_state")
            ),
            "activity_status_transitions": _build_transitions(
                snapshots, repo, lambda state: state.get("activity_status")
            ),
            "activity_status_streaks": _build_streaks(
                snapshots, repo, lambda state: state.get("activity_status")
            ),
            "risk_tier_changes": _build_transitions(
                snapshots, repo, lambda state: state.get("risk_tier")
            ),
        }
        for repo in repo_names
    ]
    highlights = _build_highlights(repos)
    return {
        "history_window_runs": len(snapshots),
        "summary": _summary_text(highlights, len(snapshots)),
        "highlights": highlights,
        "repos": repos,
    }


def _load_snapshot(path: Path) -> _TruthSnapshot | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    generated_at = _text(payload.get("generated_at")) or path.stem.removeprefix("portfolio-truth-")
    projects: dict[str, dict[str, str]] = {}
    for project in payload.get("projects") or []:
        if not isinstance(project, dict):
            continue
        name = _project_name(project)
        if not name:
            continue
        projects[name] = {
            "attention_state": _state_value(project, "derived", "attention_state"),
            "activity_status": _state_value(project, "derived", "activity_status"),
            "risk_tier": _state_value(project, "risk", "risk_tier"),
        }
    return _TruthSnapshot(generated_at=generated_at, projects=projects)


def _snapshot_from_record(record: Mapping[str, Any]) -> _TruthSnapshot:
    projects = {
        str(name): {str(key): str(value) for key, value in state.items()}
        for name, state in (record.get("projects") or {}).items()
        if isinstance(state, Mapping)
    }
    return _TruthSnapshot(
        generated_at=_text(record.get("generated_at")),
        projects=projects,
    )


def _project_name(project: Mapping[str, Any]) -> str:
    identity = project.get("identity")
    if isinstance(identity, Mapping):
        return _text(identity.get("display_name")) or _text(identity.get("name"))
    return _text(project.get("name"))


def _state_value(project: Mapping[str, Any], section: str, key: str) -> str:
    nested = project.get(section)
    if isinstance(nested, Mapping):
        value = _text(nested.get(key))
        if value:
            return value
    return _text(project.get(key))


def _build_transitions(
    snapshots: list[_TruthSnapshot],
    repo: str,
    state_for: Callable[[dict[str, str]], str],
) -> list[dict[str, str]]:
    transitions: list[dict[str, str]] = []
    for previous, current in zip(snapshots, snapshots[1:]):
        previous_state = previous.projects.get(repo)
        current_state = current.projects.get(repo)
        if previous_state is None or current_state is None:
            continue
        from_state = state_for(previous_state)
        to_state = state_for(current_state)
        if from_state and to_state and from_state != to_state:
            transitions.append(
                {
                    "from": from_state,
                    "to": to_state,
                    "date": current.date,
                }
            )
    return transitions


def _build_streaks(
    snapshots: list[_TruthSnapshot],
    repo: str,
    state_for: Callable[[dict[str, str]], str],
) -> list[dict[str, Any]]:
    streaks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for snapshot in snapshots:
        state = snapshot.projects.get(repo)
        value = state_for(state) if state is not None else ""
        if not value:
            _close_streak(streaks, current)
            current = None
            continue
        if current is not None and current["status"] == value:
            current["end_date"] = snapshot.date
            current["runs"] += 1
            continue
        _close_streak(streaks, current)
        current = {
            "status": value,
            "start_date": snapshot.date,
            "end_date": snapshot.date,
            "runs": 1,
        }
    _close_streak(streaks, current)
    return streaks


def _close_streak(streaks: list[dict[str, Any]], current: dict[str, Any] | None) -> None:
    if current is not None:
        streaks.append(current)


def _build_highlights(repos: list[dict[str, Any]]) -> list[str]:
    groups: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    for repo in repos:
        name = str(repo["repo"])
        for key, kind in (
            ("attention_lane_transitions", "attention"),
            ("activity_status_transitions", "activity"),
            ("risk_tier_changes", "risk"),
        ):
            events = repo.get(key) or []
            for event in events:
                groups[(kind, str(event["from"]), str(event["to"]))].add(name)

    ordered = sorted(
        groups.items(),
        key=lambda item: (
            {"activity": 0, "attention": 1, "risk": 2}[item[0][0]],
            item[0][1],
            item[0][2],
        ),
    )
    highlights: list[str] = []
    for (kind, from_state, to_state), repo_names in ordered:
        direction = _movement_direction(kind, from_state, to_state)
        if kind == "risk":
            verb = "risk rose" if direction == "worsened" else "risk eased" if direction == "improved" else "risk changed"
        else:
            verb = "slid" if direction == "worsened" else "recovered" if direction == "improved" else "moved"
        noun = "repo" if len(repo_names) == 1 else "repos"
        highlights.append(f"{len(repo_names)} {noun} {verb} {from_state}→{to_state}")
    return highlights


def _movement_direction(kind: str, from_state: str, to_state: str) -> str:
    order = {
        "activity": _ACTIVITY_ORDER,
        "attention": _ATTENTION_ORDER,
        "risk": _RISK_ORDER,
    }[kind]
    from_rank = order.get(from_state)
    to_rank = order.get(to_state)
    if from_rank is None or to_rank is None or from_rank == to_rank:
        return "changed"
    return "improved" if to_rank < from_rank else "worsened"


def _summary_text(highlights: list[str], run_count: int) -> str:
    if not highlights:
        return f"No movement in the last {run_count} snapshot(s)."
    return "; ".join(highlights) + "."


def _text(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""
