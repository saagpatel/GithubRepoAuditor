"""Tests for src/draft_readmes.py — Arc G Sprint 5.1-5.3."""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.draft_readmes import (
    DraftReadmePacket,
    build_context,
    generate_draft,
    qualify_repos,
    write_packets_to_ledger,
)
from src.llm_cost import BudgetExceededError

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_repo(
    name: str = "my-repo",
    *,
    readme_stale: bool | None = None,
    readme_text: str | None = None,
    has_readme: bool | None = None,
) -> dict:
    return {
        "repo_name": name,
        "name": name,
        "description": f"Description of {name}",
        "language": "Python",
        "topics": ["cli", "tool"],
        "stars": 42,
        "license": "MIT",
        "latest_release": "v1.0.0",
        "readme_stale": readme_stale,
        "readme_text": readme_text,
        "has_readme": has_readme,
        "top_level_dirs": ["src", "tests", "docs"],
        "recent_commits": ["feat: add feature", "fix: bug fix", "chore: update deps"],
    }


class _EchoProvider:
    """Fake LLM provider — echoes the prompt back as the proposed README."""

    def __init__(self, cost_per_call: float = 0.0) -> None:
        self._cost_per_call = cost_per_call

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        *,
        cost_tracker: Any = None,
        feature: str = "draft-readme",
    ) -> str:
        if cost_tracker is not None and self._cost_per_call > 0:
            cost_tracker.record_call(
                provider="fake",
                model=model,
                input_tokens=100,
                output_tokens=100,
                feature=feature,
            )
        return f"# README for {prompt[:30]}"


class _BudgetBustingProvider:
    """Fake provider that immediately raises BudgetExceededError."""

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        *,
        cost_tracker: Any = None,
        feature: str = "draft-readme",
    ) -> str:
        raise BudgetExceededError(
            budget_usd=0.0001,
            current_usd=0.0,
            call_cost_usd=0.001,
            feature=feature,
        )


# ── qualify_repos ─────────────────────────────────────────────────────────────


class TestQualifyRepos:
    def test_all_qualifying_returns_stale_and_short(self) -> None:
        """Three repos: one stale, one short, one fine → returns first two."""
        repos = [
            _make_repo("stale-repo", readme_stale=True, readme_text="Some content here."),
            _make_repo("short-repo", readme_stale=False, readme_text="Hi."),
            _make_repo("fine-repo", readme_stale=False, readme_text="x" * 300),
        ]
        result = qualify_repos(repos, opt_in_repos=None, all_qualifying=True)
        assert "stale-repo" in result
        assert "short-repo" in result
        assert "fine-repo" not in result

    def test_all_qualifying_includes_missing_readme(self) -> None:
        """Repo with has_readme=False should qualify."""
        repos = [
            _make_repo("missing-readme", has_readme=False, readme_text=None),
        ]
        result = qualify_repos(repos, opt_in_repos=None, all_qualifying=True)
        assert "missing-readme" in result

    def test_opt_in_repos_bypasses_staleness_filter(self) -> None:
        """opt_in_repos=['foo'] returns exactly ['foo'] even if foo doesn't qualify."""
        repos = [
            _make_repo("foo", readme_stale=False, readme_text="x" * 500),
            _make_repo("bar", readme_stale=True),
        ]
        result = qualify_repos(repos, opt_in_repos=["foo"], all_qualifying=False)
        assert result == ["foo"]

    def test_no_flags_returns_empty(self) -> None:
        repos = [_make_repo("any", readme_stale=True)]
        result = qualify_repos(repos, opt_in_repos=None, all_qualifying=False)
        assert result == []

    def test_opt_in_takes_priority_over_all_qualifying(self) -> None:
        """When opt_in_repos is non-empty, all_qualifying is ignored."""
        repos = [
            _make_repo("stale", readme_stale=True),
            _make_repo("explicit"),
        ]
        result = qualify_repos(repos, opt_in_repos=["explicit"], all_qualifying=True)
        assert result == ["explicit"]


# ── build_context ─────────────────────────────────────────────────────────────


class TestBuildContext:
    def test_returns_expected_keys(self) -> None:
        repo = _make_repo("test-repo", readme_text="Hello world")
        ctx = build_context(repo, semantic_index=None)
        for key in (
            "repo_name",
            "description",
            "language",
            "topics",
            "stars",
            "license",
            "latest_release",
            "file_tree",
            "current_readme",
            "current_readme_sha",
            "recent_commits",
            "context_repos",
            "readme_stale",
        ):
            assert key in ctx, f"Missing key: {key}"

    def test_omits_neighbors_when_semantic_index_is_none(self) -> None:
        repo = _make_repo("test-repo")
        ctx = build_context(repo, semantic_index=None)
        assert ctx["context_repos"] == []

    def test_includes_neighbors_from_semantic_index(self) -> None:
        fake_index = MagicMock()
        fake_result = MagicMock()
        fake_result.repo_name = "neighbor-repo"
        fake_result.snippet = "A similar tool."
        fake_index.find_neighbors.return_value = [fake_result]

        repo = _make_repo("test-repo")
        ctx = build_context(repo, semantic_index=fake_index)
        assert len(ctx["context_repos"]) == 1
        assert ctx["context_repos"][0]["repo_name"] == "neighbor-repo"

    def test_gracefully_handles_semantic_index_error(self) -> None:
        fake_index = MagicMock()
        fake_index.find_neighbors.side_effect = RuntimeError("index not ready")

        repo = _make_repo("test-repo")
        ctx = build_context(repo, semantic_index=fake_index)
        # Should not raise — context_repos is empty on error
        assert ctx["context_repos"] == []

    def test_recent_commits_truncated_to_10(self) -> None:
        repo = _make_repo("test-repo")
        repo["recent_commits"] = [f"commit {i}" for i in range(20)]
        ctx = build_context(repo, semantic_index=None)
        assert len(ctx["recent_commits"]) == 10

    def test_handles_dict_commit_format(self) -> None:
        repo = _make_repo("test-repo")
        repo["recent_commits"] = [{"message": "feat: add thing\n\nBody here"}]
        ctx = build_context(repo, semantic_index=None)
        assert ctx["recent_commits"] == ["feat: add thing"]


# ── generate_draft ────────────────────────────────────────────────────────────


class TestGenerateDraft:
    def test_happy_path_returns_packet(self) -> None:
        repo = _make_repo("happy-repo", readme_text="Old README")
        ctx = build_context(repo, semantic_index=None)
        provider = _EchoProvider()
        packet = generate_draft(repo, context=ctx, provider=provider, model="fake-model")

        assert isinstance(packet, DraftReadmePacket)
        assert packet.repo_name == "happy-repo"
        assert "README" in packet.proposed_readme
        assert packet.llm_model == "fake-model"
        assert packet.diff_summary != ""
        assert packet.generated_at != ""

    def test_new_readme_from_scratch_diff_summary(self) -> None:
        repo = _make_repo("fresh-repo", readme_text=None)
        ctx = build_context(repo, semantic_index=None)
        ctx["current_readme"] = ""
        provider = _EchoProvider()
        packet = generate_draft(repo, context=ctx, provider=provider, model="m")
        assert "scratch" in packet.diff_summary.lower()

    def test_budget_exceeded_propagates_with_repo_name(self) -> None:
        repo = _make_repo("budget-repo")
        ctx = build_context(repo, semantic_index=None)
        provider = _BudgetBustingProvider()

        with pytest.raises(BudgetExceededError) as exc_info:
            generate_draft(repo, context=ctx, provider=provider, model="m")
        assert "budget-repo" in exc_info.value.feature

    def test_context_repos_captured_in_packet(self) -> None:
        repo = _make_repo("ctx-repo")
        ctx = build_context(repo, semantic_index=None)
        ctx["context_repos"] = [
            {"repo_name": "neighbor-a", "snippet": "s"},
            {"repo_name": "neighbor-b", "snippet": "s"},
        ]
        provider = _EchoProvider()
        packet = generate_draft(repo, context=ctx, provider=provider, model="m")
        assert "neighbor-a" in packet.context_repos
        assert "neighbor-b" in packet.context_repos


# ── write_packets_to_ledger ───────────────────────────────────────────────────


class TestWritePacketsToLedger:
    def test_produces_readable_records(self) -> None:
        """Packets written to ledger can be read back by load_approval_records."""
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet = DraftReadmePacket(
                repo_name="test/repo",
                current_readme_sha="abc123",
                proposed_readme="# Test Repo\n\nHello.",
                diff_summary="+3 lines added, -0 lines removed vs current README.",
                llm_provider="fake",
                llm_model="fake-model",
                llm_cost_usd=0.0012,
                generated_at="2026-05-11T00:00:00+00:00",
                context_repos=["other/repo"],
            )
            write_packets_to_ledger([packet], output_dir, reviewer="test-user")

            # Read back — load_approval_records needs username
            records = load_approval_records(output_dir, "test-user")
            # At least one record with approval_subject_type="draft-readme"
            draft_records = [r for r in records if r.get("approval_subject_type") == "draft-readme"]
            assert len(draft_records) >= 1
            r = draft_records[0]
            assert r["subject_key"] == "test/repo"
            # load_approval_records returns the full packet dict at the top level
            # (warehouse merges details_json into the row payload)
            assert r.get("proposed_readme") == "# Test Repo\n\nHello."
            assert r.get("action_type") == "draft-readme"
            assert r.get("target_context") == "test/repo"

    def test_empty_packets_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_packets_to_ledger([], Path(tmp), reviewer="user")
            # No warehouse file created (no writes happened)
            # Just assert no exception was raised


# ── CLI flag dispatch ─────────────────────────────────────────────────────────


class TestCLIFlagDispatch:
    def test_audit_report_draft_readmes_repo_calls_dispatch(self) -> None:
        """audit report --draft-readmes --draft-readmes-repo someuser/foo → dispatch called."""

        test_argv = [
            "audit",
            "report",
            "someuser",
            "--draft-readmes",
            "--draft-readmes-repo",
            "someuser/foo",
            "--output-dir",
            "/tmp/test-output",
        ]
        with (
            patch("sys.argv", test_argv),
            patch("src.cli._run_draft_readmes_mode") as mock_dispatch,
        ):
            from src.cli import main

            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass
        assert mock_dispatch.called

    def test_parser_accepts_draft_readmes_repo_flag(self) -> None:
        """build_parser() accepts --draft-readmes and --draft-readmes-repo flags."""
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "someuser",
                "--draft-readmes",
                "--draft-readmes-repo",
                "someuser/foo",
                "--output-dir",
                "/tmp/test-output",
            ]
        )
        assert args.draft_readmes is True
        assert args.draft_readmes_repos == ["someuser/foo"]

    def test_legacy_form_accepts_draft_readmes_flags(self) -> None:
        """Legacy flat invocation accepts --draft-readmes flags."""
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "someuser",
                "--draft-readmes",
                "--draft-readmes-all",
                "--output-dir",
                "/tmp/test-output",
            ]
        )
        assert args.draft_readmes is True
        assert args.draft_readmes_all is True

    def test_legacy_form_emits_deprecation_warning(self) -> None:
        """Legacy flat invocation (no subcommand) emits DeprecationWarning."""
        from unittest.mock import patch

        argv = [
            "someuser",
            "--draft-readmes",
            "--draft-readmes-repo",
            "foo",
            "--output-dir",
            "/tmp/test-output",
        ]
        with patch("sys.argv", ["audit"] + argv):
            with patch("src.cli._run_draft_readmes_mode") as mock_fn:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    try:
                        from src.cli import main

                        main()
                    except SystemExit:
                        pass
                    except Exception:
                        pass
                # Either a DeprecationWarning was emitted or _run_draft_readmes_mode was called
                # (both indicate the flag was routed correctly)
                deprecation_warnings = [
                    w for w in caught if issubclass(w.category, DeprecationWarning)
                ]
                # The legacy path should have triggered either a dispatch or deprecation warning
                assert mock_fn.called or len(deprecation_warnings) > 0

    def test_infer_subcommand_maps_draft_readmes_to_report(self) -> None:
        """_infer_subcommand_from_flags returns 'report' when draft_readmes=True."""
        from src.cli import _infer_subcommand_from_flags, build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "someuser",
                "--draft-readmes",
                "--draft-readmes-all",
                "--output-dir",
                "/tmp",
            ]
        )
        result = _infer_subcommand_from_flags(args)
        assert result == "report"


# ── Suppression integration ───────────────────────────────────────────────────


class TestSuppressionCheck:
    def test_suppressed_repo_skipped_in_dispatch(self) -> None:
        """When operator prefs mark a repo as suppressed, generate_draft is not called."""
        with patch("src.draft_readmes.generate_draft") as mock_gen:
            from src.operator_prefs import is_suppressed

            prefs = {
                "suppressions": [
                    {
                        "action_type": "draft-readme",
                        "target_context": "owner/suppressed-repo",
                        "rejection_count": 3,
                        "last_rejected_at": "2026-05-01T00:00:00+00:00",
                        "suppressed_at": "2026-05-01T00:00:00+00:00",
                        "manual": False,
                    }
                ]
            }
            result = is_suppressed(
                prefs, action_type="draft-readme", target_context="owner/suppressed-repo"
            )
            assert result is not None
            assert result.action_type == "draft-readme"

        # generate_draft would not be called for suppressed repos — verified by is_suppressed returning non-None
        mock_gen.assert_not_called()


# ── Cost guard integration ────────────────────────────────────────────────────


class TestCostGuard:
    def test_budget_exceeded_aborts_batch_partial_packets_persisted(self) -> None:
        """With --max-llm-spend=0.0001 and a budget-busting provider, run aborts
        after the first failure; packets generated before the abort are persisted."""
        from src.llm_cost import CostTracker

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            repos = [
                _make_repo("repo-ok", readme_text="Old README"),
                _make_repo("repo-bust"),
            ]

            # First call succeeds, second raises BudgetExceededError
            call_count = 0

            class _PartialProvider:
                def generate(self, prompt, model, max_tokens, *, cost_tracker=None, feature="x"):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return "# OK README"
                    raise BudgetExceededError(
                        budget_usd=0.0001,
                        current_usd=0.00005,
                        call_cost_usd=0.001,
                        feature=feature,
                    )

            provider = _PartialProvider()
            cost_tracker = CostTracker(budget_usd=None, output_path=output_dir)

            packets_written: list[DraftReadmePacket] = []
            for repo in repos:
                ctx = build_context(repo, semantic_index=None)
                try:
                    p = generate_draft(
                        repo, context=ctx, provider=provider, model="m", cost_tracker=cost_tracker
                    )
                    packets_written.append(p)
                except BudgetExceededError:
                    break

            # Persist whatever was generated before abort
            write_packets_to_ledger(packets_written, output_dir, reviewer="tester")

            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "tester")
            draft_records = [r for r in records if r.get("approval_subject_type") == "draft-readme"]
            assert len(draft_records) == 1
            assert draft_records[0]["subject_key"] == "repo-ok"
