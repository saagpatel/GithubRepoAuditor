"""Stable artifact path builders for operator-facing outputs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def control_center_paths(
    output_dir: Path, username: str, generated_at: datetime
) -> tuple[Path, Path]:
    stamp = generated_at.strftime("%Y-%m-%d")
    return (
        output_dir / f"operator-control-center-{username}-{stamp}.json",
        output_dir / f"operator-control-center-{username}-{stamp}.md",
    )


def weekly_command_center_paths(
    output_dir: Path, username: str, generated_at: datetime
) -> tuple[Path, Path]:
    stamp = generated_at.strftime("%Y-%m-%d")
    return (
        output_dir / f"weekly-command-center-{username}-{stamp}.json",
        output_dir / f"weekly-command-center-{username}-{stamp}.md",
    )


def approval_center_paths(
    output_dir: Path, username: str, generated_at: datetime
) -> tuple[Path, Path]:
    stamp = generated_at.strftime("%Y-%m-%d")
    return (
        output_dir / f"approval-center-{username}-{stamp}.json",
        output_dir / f"approval-center-{username}-{stamp}.md",
    )


def approval_receipt_paths(
    output_dir: Path, username: str, generated_at: datetime
) -> tuple[Path, Path]:
    stamp = generated_at.strftime("%Y-%m-%d")
    return (
        output_dir / f"approval-receipt-{username}-{stamp}.json",
        output_dir / f"approval-receipt-{username}-{stamp}.md",
    )


def followup_review_receipt_paths(
    output_dir: Path, username: str, generated_at: datetime
) -> tuple[Path, Path]:
    stamp = generated_at.strftime("%Y-%m-%d")
    return (
        output_dir / f"approval-followup-receipt-{username}-{stamp}.json",
        output_dir / f"approval-followup-receipt-{username}-{stamp}.md",
    )
