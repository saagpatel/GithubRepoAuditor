from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.cli import _run_security_gate_mode, build_subcommand_parser
from src.portfolio_security_gate import (
    build_security_gate_report,
    render_security_gate_markdown,
)


def _project(
    name: str,
    *,
    alerts_available: bool = True,
    critical: int = 0,
    high: int = 0,
    risk_tier: str = "baseline",
) -> dict:
    return {
        "identity": {"display_name": name, "path": name},
        "risk": {"risk_tier": risk_tier},
        "security": {
            "alerts_available": alerts_available,
            "dependabot_critical": critical,
            "dependabot_high": high,
        },
    }


def test_security_gate_passes_when_scanned_repos_are_clear() -> None:
    report = build_security_gate_report(
        {
            "generated_at": "2026-07-04T11:04:28+00:00",
            "projects": [
                _project("RepoA"),
                _project("RepoB", critical=0, high=0),
            ],
        }
    )

    assert report.passed is True
    assert report.status == "pass"
    assert report.scanned_count == 2
    assert report.repos_with_open_high_critical == 0
    assert "All scanned repos are clear" in render_security_gate_markdown(report)


def test_security_gate_passes_when_snapshot_is_fresh_enough() -> None:
    report = build_security_gate_report(
        {
            "generated_at": "2026-07-04T11:00:00+00:00",
            "projects": [_project("RepoA")],
        },
        max_age_hours=24,
        now=datetime(2026, 7, 4, 12, 30, tzinfo=timezone.utc),
    )

    assert report.passed is True
    assert report.status == "pass"
    assert report.source_age_hours == 1.5
    assert report.max_age_hours == 24


def test_security_gate_marks_old_snapshot_stale() -> None:
    report = build_security_gate_report(
        {
            "generated_at": "2026-07-01T11:00:00+00:00",
            "projects": [_project("RepoA")],
        },
        max_age_hours=24,
        now=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )

    assert report.passed is False
    assert report.status == "stale"
    assert report.source_age_hours == 73
    assert "beyond the 24h freshness threshold" in render_security_gate_markdown(report)


def test_security_gate_marks_invalid_generated_at_stale() -> None:
    report = build_security_gate_report(
        {
            "generated_at": "not-a-date",
            "projects": [_project("RepoA")],
        },
        max_age_hours=24,
        now=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )

    assert report.passed is False
    assert report.status == "stale"
    assert report.freshness_error == "invalid generated_at: not-a-date"
    assert "could not be verified" in render_security_gate_markdown(report)


def test_security_gate_fails_and_ranks_open_high_critical_repos() -> None:
    report = build_security_gate_report(
        {
            "projects": [
                _project("HighOnly", high=2, risk_tier="moderate"),
                _project("Critical", critical=1, risk_tier="elevated"),
                _project("Clear"),
            ],
        }
    )

    assert report.passed is False
    assert report.status == "fail"
    assert report.scanned_count == 3
    assert report.total_open_critical == 1
    assert report.total_open_high == 2
    assert [item.repo for item in report.flagged_repos] == ["Critical", "HighOnly"]
    rendered = render_security_gate_markdown(report)
    assert "| Critical | elevated | 1 | 0 |" in rendered
    assert "| HighOnly | moderate | 0 | 2 |" in rendered


def test_security_gate_treats_missing_overlay_as_unknown_not_pass() -> None:
    report = build_security_gate_report(
        {
            "projects": [
                _project("Unscanned", alerts_available=False),
                {"identity": {"display_name": "NoSecurityBlock"}},
            ]
        }
    )

    assert report.passed is False
    assert report.status == "unknown"
    assert report.scanned_count == 0
    assert "Security overlay was not present" in render_security_gate_markdown(report)


def test_security_gate_subcommand_parses() -> None:
    parser = build_subcommand_parser()
    args = parser.parse_args(
        ["security-gate", "--output-dir", "out", "--json", "--max-age-hours", "24"]
    )

    assert args._subcommand == "security-gate"
    assert args.output_dir == "out"
    assert args.json is True
    assert args.max_age_hours == 24


def test_security_gate_cli_json_exits_zero_on_clear_snapshot(tmp_path, capsys) -> None:
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps({"projects": [_project("Clear")]}),
        encoding="utf-8",
    )

    _run_security_gate_mode(SimpleNamespace(output_dir=str(tmp_path), json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["scanned_count"] == 1


def test_security_gate_cli_exits_nonzero_on_stale_snapshot(tmp_path) -> None:
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps({"generated_at": "2026-07-01T11:00:00+00:00", "projects": [_project("Clear")]}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        _run_security_gate_mode(
            SimpleNamespace(output_dir=str(tmp_path), json=True, max_age_hours=24)
        )

    assert exc.value.code == 1


def test_security_gate_cli_exits_nonzero_on_open_alerts(tmp_path) -> None:
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps({"projects": [_project("Open", high=1)]}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        _run_security_gate_mode(SimpleNamespace(output_dir=str(tmp_path), json=False))

    assert exc.value.code == 1
