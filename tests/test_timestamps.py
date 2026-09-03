from __future__ import annotations

from datetime import datetime, timezone

import pytest

from github_repo_auditor.timestamps import parse_utc_timestamp


def test_z_suffix_is_treated_as_utc() -> None:
    assert parse_utc_timestamp("2026-09-02T12:34:56Z") == datetime(
        2026, 9, 2, 12, 34, 56, tzinfo=timezone.utc
    )


def test_explicit_offset_is_converted_to_utc() -> None:
    assert parse_utc_timestamp("2026-09-02T01:30:00+02:30") == datetime(
        2026, 9, 1, 23, 0, tzinfo=timezone.utc
    )


def test_naive_timestamp_is_rejected_by_default() -> None:
    assert parse_utc_timestamp("2026-09-02T12:34:56") is None


def test_naive_timestamp_can_be_assumed_utc() -> None:
    assert parse_utc_timestamp(
        "2026-09-02T12:34:56", naive="assume_utc"
    ) == datetime(2026, 9, 2, 12, 34, 56, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", [None, "", "   "])
@pytest.mark.parametrize("coerce", [False, True])
def test_empty_values_return_none(value: object, coerce: bool) -> None:
    assert parse_utc_timestamp(value, coerce=coerce) is None


def test_non_string_is_rejected_without_coercion() -> None:
    value = datetime(2026, 9, 2, 12, 34, 56, tzinfo=timezone.utc)

    assert parse_utc_timestamp(value) is None


def test_non_string_can_be_coerced_before_parsing() -> None:
    value = datetime(2026, 9, 2, 12, 34, 56, tzinfo=timezone.utc)

    assert parse_utc_timestamp(value, coerce=True) == value


def test_invalid_string_returns_none() -> None:
    assert parse_utc_timestamp("not-a-timestamp") is None
