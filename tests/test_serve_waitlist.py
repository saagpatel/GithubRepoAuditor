"""Tests for src/serve/waitlist.py — email capture store + validation."""

from __future__ import annotations

import pytest

from src.serve.waitlist import (
    SqliteWaitlistStore,
    build_waitlist_store,
    is_valid_email,
)


@pytest.mark.parametrize(
    "email", ["a@b.co", "first.last@example.com", "dev+tag@sub.domain.io"]
)
def test_valid_emails(email: str) -> None:
    assert is_valid_email(email) is True


@pytest.mark.parametrize(
    "email",
    [
        "",
        "no-at-sign",
        "a@b",
        "a b@c.com",
        "a@@example.com",
        "@example.com",
        "a@.com",
        "a@example..com",
    ],
)
def test_invalid_emails(email: str) -> None:
    assert is_valid_email(email) is False


def test_email_length_capped() -> None:
    assert is_valid_email("a" * 250 + "@example.com") is False


def test_store_add_and_count(tmp_path) -> None:
    store = SqliteWaitlistStore(str(tmp_path / "wl.db"))
    assert store.add("dev@example.com") is True
    assert store.count() == 1


def test_store_creates_missing_parent_dir(tmp_path) -> None:
    # Parent dir does not exist yet — the store must create it, not crash.
    store = SqliteWaitlistStore(str(tmp_path / "nested" / "dir" / "wl.db"))
    assert store.add("a@b.co") is True


def test_store_dedupes_case_insensitively(tmp_path) -> None:
    store = SqliteWaitlistStore(str(tmp_path / "wl.db"))
    assert store.add("Dev@Example.com") is True
    assert store.add("dev@example.com") is False  # same email, normalized
    assert store.count() == 1


def test_store_persists_across_instances(tmp_path) -> None:
    path = str(tmp_path / "wl.db")
    SqliteWaitlistStore(path).add("a@b.co", source="octocat")
    # A fresh instance over the same file sees the prior write.
    assert SqliteWaitlistStore(path).count() == 1


def test_builder_prefers_env(tmp_path, monkeypatch) -> None:
    target = str(tmp_path / "from-env.db")
    monkeypatch.setenv("GHRA_WAITLIST_DB", target)
    store = build_waitlist_store(default_dir=tmp_path / "ignored")
    store.add("a@b.co")
    assert (tmp_path / "from-env.db").exists()


def test_builder_uses_default_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GHRA_WAITLIST_DB", raising=False)
    store = build_waitlist_store(default_dir=tmp_path)
    store.add("a@b.co")
    assert (tmp_path / "waitlist.db").exists()
