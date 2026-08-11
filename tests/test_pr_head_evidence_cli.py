from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.cli as cli_module
from src.app.pr_head_evidence import run_pr_head_evidence_mode

FIXTURES = Path(__file__).parent / "fixtures" / "pr_head_evidence"


def _run_fixture(name: str, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    run_pr_head_evidence_mode(SimpleNamespace(snapshot=str(FIXTURES / name)))
    return json.loads(capsys.readouterr().out)


def test_pr_evidence_parser_is_local_and_minimal() -> None:
    args = cli_module.build_pr_head_evidence_parser().parse_args(
        [str(FIXTURES / "current.json")]
    )

    assert args.snapshot.endswith("current.json")
    assert not hasattr(args, "token")
    assert not hasattr(args, "output_dir")


def test_current_fixture_exits_zero_and_emits_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    verdict = _run_fixture("current.json", capsys)

    assert verdict["state"] == "current"
    assert verdict["current"] is True


@pytest.mark.parametrize(
    ("fixture", "state"),
    [
        ("stale.json", "stale"),
        ("comment_only.json", "missing"),
        ("dismissed.json", "missing"),
    ],
)
def test_non_current_fixture_exits_one(
    fixture: str,
    state: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        run_pr_head_evidence_mode(SimpleNamespace(snapshot=str(FIXTURES / fixture)))

    verdict = json.loads(capsys.readouterr().out)
    assert exc.value.code == 1
    assert verdict["state"] == state
    assert verdict["current"] is False


def test_incomplete_fixture_exits_two_as_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        run_pr_head_evidence_mode(
            SimpleNamespace(snapshot=str(FIXTURES / "incomplete.json"))
        )

    verdict = json.loads(capsys.readouterr().out)
    assert exc.value.code == 2
    assert verdict["state"] == "unknown"
    assert "reviews_pagination_truncated" in verdict["reasons"]


def test_malformed_fixture_exits_two_with_versioned_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        run_pr_head_evidence_mode(
            SimpleNamespace(snapshot=str(FIXTURES / "malformed.json"))
        )

    verdict = json.loads(capsys.readouterr().out)
    assert exc.value.code == 2
    assert verdict["schema_version"] == "PRHeadEvidenceVerdictV1"
    assert verdict["state"] == "unknown"
    assert verdict["reasons"] == ["snapshot_malformed"]
    assert verdict["validation_errors"]


def test_main_intercepts_pr_evidence_before_auth_token_lookup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _unexpected_auth_lookup() -> str:
        raise AssertionError("pr-evidence must not consult GitHub auth")

    monkeypatch.setattr(cli_module, "_gh_auth_token", _unexpected_auth_lookup)
    monkeypatch.setattr(
        sys,
        "argv",
        ["audit", "pr-evidence", str(FIXTURES / "current.json")],
    )

    cli_module.main()

    verdict = json.loads(capsys.readouterr().out)
    assert verdict["state"] == "current"


def test_cli_does_not_modify_snapshot_or_fixture_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot = FIXTURES / "current.json"
    before_bytes = snapshot.read_bytes()
    before_names = sorted(path.name for path in FIXTURES.iterdir())

    _run_fixture("current.json", capsys)

    assert snapshot.read_bytes() == before_bytes
    assert sorted(path.name for path in FIXTURES.iterdir()) == before_names
