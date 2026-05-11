from __future__ import annotations

import json

from src.operator_acknowledgments import (
    acknowledgments_path,
    build_acknowledgment_record,
    directional_signature,
    find_matching_change,
    is_change_acknowledged,
    load_acknowledgments,
    save_acknowledgment,
)


def _make_change(
    *,
    change_type: str = "security-change",
    repo_name: str = "RepoA",
    title: str = "RepoA security posture changed",
    details: dict | None = None,
) -> dict:
    return {
        "change_key": f"key-{change_type}-{repo_name}",
        "change_type": change_type,
        "repo_name": repo_name,
        "severity": 0.5,
        "title": title,
        "summary": "summary",
        "recommended_next_step": "next",
        "details": details or {},
    }


def test_load_acknowledgments_missing_file_returns_empty(tmp_path):
    assert load_acknowledgments(tmp_path, "alice") == []


def test_save_acknowledgment_round_trip(tmp_path):
    ack = build_acknowledgment_record(
        _make_change(details={"old_label": "watch", "new_label": "healthy"}),
        reviewer="alice",
        note="reviewed",
    )

    path = save_acknowledgment(tmp_path, "alice", ack)

    assert path == acknowledgments_path(tmp_path, "alice")
    payload = json.loads(path.read_text())
    assert payload["version"] == 1
    assert payload["username"] == "alice"
    assert payload["acknowledgments"] == [ack]
    assert load_acknowledgments(tmp_path, "alice") == [ack]


def test_save_acknowledgment_replaces_existing_change_key(tmp_path):
    change = _make_change(details={"old_label": "watch", "new_label": "healthy"})
    first = build_acknowledgment_record(change, reviewer="alice", note="first")
    second = build_acknowledgment_record(change, reviewer="bob", note="updated")

    save_acknowledgment(tmp_path, "alice", first)
    save_acknowledgment(tmp_path, "alice", second)

    stored = load_acknowledgments(tmp_path, "alice")
    assert len(stored) == 1
    assert stored[0]["reviewer"] == "bob"
    assert stored[0]["note"] == "updated"


def test_directional_signature_security_change_uses_labels():
    change = _make_change(details={"old_label": "watch", "new_label": "healthy"})
    assert directional_signature(change) == {
        "old_label": "watch",
        "new_label": "healthy",
    }


def test_directional_signature_lens_delta_uses_lens_and_sign():
    change = _make_change(
        change_type="lens-delta",
        details={"lens": "security_posture", "delta": 0.077},
    )
    assert directional_signature(change) == {
        "lens": "security_posture",
        "delta_sign": 1,
    }


def test_directional_signature_lens_delta_falls_back_to_lens_deltas_map():
    change = _make_change(
        change_type="lens-delta",
        details={
            "lens": "security_posture",
            "delta": 0.0,
            "lens_deltas": {"security_posture": 0.077, "momentum": 0.0},
        },
    )
    assert directional_signature(change) == {
        "lens": "security_posture",
        "delta_sign": 1,
    }


def test_directional_signature_unknown_type_returns_empty():
    change = _make_change(change_type="campaign-drift", details={"foo": "bar"})
    assert directional_signature(change) == {}


def test_is_change_acknowledged_matches_same_signature():
    change = _make_change(details={"old_label": "watch", "new_label": "healthy"})
    ack = build_acknowledgment_record(change, reviewer="alice", note="reviewed")

    assert is_change_acknowledged(change, [ack]) is True


def test_is_change_acknowledged_rejects_regression_in_opposite_direction():
    healthy_change = _make_change(details={"old_label": "watch", "new_label": "healthy"})
    ack = build_acknowledgment_record(healthy_change, reviewer="alice", note="reviewed")

    regression = _make_change(details={"old_label": "healthy", "new_label": "watch"})

    assert is_change_acknowledged(regression, [ack]) is False


def test_is_change_acknowledged_rejects_lens_delta_with_opposite_sign():
    improvement = _make_change(
        change_type="lens-delta",
        details={"lens": "security_posture", "delta": 0.077},
    )
    ack = build_acknowledgment_record(improvement, reviewer="alice", note="reviewed")

    regression = _make_change(
        change_type="lens-delta",
        details={"lens": "security_posture", "delta": -0.077},
    )

    assert is_change_acknowledged(regression, [ack]) is False


def test_is_change_acknowledged_rejects_unrelated_change():
    change = _make_change()
    other = _make_change(repo_name="RepoB")
    ack = build_acknowledgment_record(change, reviewer="alice", note="reviewed")

    assert is_change_acknowledged(other, [ack]) is False


def test_is_change_acknowledged_handles_empty_acknowledgments():
    change = _make_change()
    assert is_change_acknowledged(change, []) is False
    assert is_change_acknowledged(change, None) is False  # type: ignore[arg-type]


def test_find_matching_change_returns_first_match():
    target = _make_change(details={"old_label": "watch", "new_label": "healthy"})
    other = _make_change(repo_name="RepoB")

    found = find_matching_change(
        repo_name="RepoA",
        change_kind="security-change",
        material_changes=[other, target],
    )

    assert found is target


def test_find_matching_change_returns_none_when_missing():
    found = find_matching_change(
        repo_name="RepoZ",
        change_kind="security-change",
        material_changes=[_make_change()],
    )
    assert found is None
