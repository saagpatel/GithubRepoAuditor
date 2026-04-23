from __future__ import annotations

from argparse import Namespace

import pytest

from src.cli_mode_validation import CliModeState, validate_cli_mode_args


def _make_args(**overrides) -> Namespace:
    defaults = {
        "registry": None,
        "notion_registry": False,
        "sync_registry": False,
        "portfolio_truth": False,
        "portfolio_context_recovery": False,
        "apply_context_recovery": False,
        "context_recovery_limit": None,
        "control_center": False,
        "approval_center": False,
        "campaign": None,
        "writeback_apply": False,
        "writeback_target": None,
        "github_projects": False,
        "doctor": False,
        "upload_badges": False,
        "badges": False,
        "notion_sync": False,
        "notion": False,
        "approve_packet": False,
        "review_packet": False,
        "approve_governance": False,
        "review_governance": False,
        "auto_apply_approved": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _raising_error(message: str) -> None:
    raise ValueError(message)


def test_validate_cli_mode_args_returns_portfolio_state() -> None:
    args = _make_args(portfolio_truth=True)

    state = validate_cli_mode_args(args, _raising_error)

    assert state == CliModeState(
        portfolio_truth_mode=True,
        portfolio_context_recovery_mode=False,
        standalone_portfolio_modes=True,
    )


def test_validate_cli_mode_args_applies_implied_flags() -> None:
    args = _make_args(upload_badges=True, notion_sync=True)

    validate_cli_mode_args(args, _raising_error)

    assert args.badges is True
    assert args.notion is True


def test_validate_cli_mode_args_rejects_standalone_portfolio_mode_combinations() -> None:
    args = _make_args(portfolio_truth=True, control_center=True)

    with pytest.raises(ValueError) as exc:
        validate_cli_mode_args(args, _raising_error)

    assert "standalone workspace modes" in str(exc.value)


def test_validate_cli_mode_args_rejects_action_sync_without_campaign() -> None:
    args = _make_args(writeback_target="github")

    with pytest.raises(ValueError) as exc:
        validate_cli_mode_args(args, _raising_error)

    assert "Action Sync mode" in str(exc.value)


def test_validate_cli_mode_args_rejects_read_only_mode_with_writeback_flags() -> None:
    args = _make_args(approval_center=True, campaign="security-review", writeback_target="github")

    with pytest.raises(ValueError) as exc:
        validate_cli_mode_args(args, _raising_error)

    assert "read-only approval view" in str(exc.value)
