"""Tests for src/plan_campaign.py — Arc G Sprint 6.1-6.2."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.llm_cost import BudgetExceededError, CostTracker
from src.plan_campaign import (
    ACTION_TYPES,
    CampaignAction,
    CampaignPlanPacket,
    generate_action_for_repo,
    generate_plan,
    narrow_candidates,
    write_packet_to_ledger,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_repo(name: str = "my-repo", **kwargs: Any) -> dict:
    return {
        "repo_name": name,
        "name": name,
        "description": f"Description of {name}",
        "primary_language": "Python",
        "topics": ["cli"],
        "stars": 5,
        "has_readme": True,
        "has_license": True,
        "archived": False,
        **kwargs,
    }


def _make_repos(names: list[str]) -> list[dict]:
    return [_make_repo(n) for n in names]


def _valid_json_response(
    *,
    qualifies: bool = True,
    action_type: str = "add_topics",
    target: str = "python, cli",
    rationale: str = "Needs better discoverability",
    expected_impact: str | None = "Better search ranking",
) -> str:
    return json.dumps(
        {
            "qualifies": qualifies,
            "action_type": action_type,
            "target": target,
            "rationale": rationale,
            "expected_impact": expected_impact,
        }
    )


class _FakeProvider:
    """Fake LLM provider returning a pre-configured response."""

    def __init__(self, response: str, cost_per_call: float = 0.001) -> None:
        self._response = response
        self._cost_per_call = cost_per_call

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        *,
        cost_tracker: Any = None,
        feature: str = "plan-campaign",
    ) -> str:
        if cost_tracker is not None:
            cost_tracker.record_call(
                provider="fake",
                model=model,
                input_tokens=50,
                output_tokens=50,
                feature=feature,
            )
        return self._response


class _BudgetBustingProvider:
    """Fake provider that immediately raises BudgetExceededError."""

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        *,
        cost_tracker: Any = None,
        feature: str = "plan-campaign",
    ) -> str:
        raise BudgetExceededError(
            budget_usd=0.0001,
            current_usd=0.0,
            call_cost_usd=0.001,
            feature=feature,
        )


# ── narrow_candidates ─────────────────────────────────────────────────────────


class TestNarrowCandidates:
    def test_no_semantic_index_returns_alphabetical_up_to_max(self) -> None:
        repos = _make_repos(["zebra", "alpha", "mango", "beta", "cherry"])
        result = narrow_candidates(
            repos, goal="archive dead repos", semantic_index=None, max_repos=3
        )
        assert len(result) == 3
        names = [r["repo_name"] for r in result]
        assert names == ["alpha", "beta", "cherry"]

    def test_no_semantic_index_returns_all_when_fewer_than_max(self) -> None:
        repos = _make_repos(["b-repo", "a-repo"])
        result = narrow_candidates(repos, goal="test", semantic_index=None, max_repos=50)
        assert len(result) == 2
        assert result[0]["repo_name"] == "a-repo"

    def test_empty_audit_results_returns_empty(self) -> None:
        result = narrow_candidates([], goal="test", semantic_index=None, max_repos=10)
        assert result == []

    def test_with_mock_semantic_index_calls_search(self) -> None:
        from src.semantic_index import SearchResult

        repos = _make_repos(["alpha", "beta", "gamma"])

        mock_index = MagicMock()
        mock_index.search.return_value = [
            SearchResult(repo_name="gamma", score=0.1, snippet=""),
            SearchResult(repo_name="alpha", score=0.2, snippet=""),
        ]

        result = narrow_candidates(
            repos, goal="find archived repos", semantic_index=mock_index, max_repos=5
        )
        mock_index.search.assert_called_once_with("find archived repos", k=5)
        # semantic results come first in order
        assert result[0]["repo_name"] == "gamma"
        assert result[1]["repo_name"] == "alpha"
        # remaining repo fills in alphabetically
        assert result[2]["repo_name"] == "beta"

    def test_semantic_index_failure_falls_back_to_alphabetical(self) -> None:
        repos = _make_repos(["c-repo", "a-repo", "b-repo"])
        mock_index = MagicMock()
        mock_index.search.side_effect = RuntimeError("index unavailable")

        result = narrow_candidates(repos, goal="test", semantic_index=mock_index, max_repos=2)
        assert len(result) == 2
        assert result[0]["repo_name"] == "a-repo"


# ── generate_action_for_repo ──────────────────────────────────────────────────


class TestGenerateActionForRepo:
    def test_valid_json_returns_campaign_action(self) -> None:
        provider = _FakeProvider(_valid_json_response())
        repo = _make_repo("my-repo")
        action = generate_action_for_repo(
            repo, goal="improve discoverability", provider=provider, model="fake-model"
        )
        assert action is not None
        assert isinstance(action, CampaignAction)
        assert action.repo_name == "my-repo"
        assert action.action_type == "add_topics"
        assert action.target == "python, cli"
        assert "discoverability" in action.rationale.lower()
        assert action.expected_impact is not None

    def test_qualifies_false_returns_none(self) -> None:
        provider = _FakeProvider(
            _valid_json_response(qualifies=False, action_type="", target="", rationale="")
        )
        action = generate_action_for_repo(
            _make_repo(), goal="test", provider=provider, model="fake-model"
        )
        assert action is None

    def test_malformed_json_returns_none(self) -> None:
        provider = _FakeProvider("This is not valid JSON at all!!!")
        action = generate_action_for_repo(
            _make_repo(), goal="test", provider=provider, model="fake-model"
        )
        assert action is None

    def test_empty_response_returns_none(self) -> None:
        provider = _FakeProvider("")
        action = generate_action_for_repo(
            _make_repo(), goal="test", provider=provider, model="fake-model"
        )
        assert action is None

    def test_unknown_action_type_forced_to_pending_human_action(self) -> None:
        provider = _FakeProvider(
            _valid_json_response(action_type="delete_repo")  # not in ACTION_TYPES
        )
        action = generate_action_for_repo(
            _make_repo(), goal="test", provider=provider, model="fake-model"
        )
        assert action is not None
        assert action.action_type == "pending_human_action"

    def test_all_valid_action_types_pass_through(self) -> None:
        for at in ACTION_TYPES:
            provider = _FakeProvider(_valid_json_response(action_type=at))
            action = generate_action_for_repo(
                _make_repo(), goal="test", provider=provider, model="m"
            )
            assert action is not None
            assert action.action_type == at

    def test_budget_exceeded_propagates_with_repo_name(self) -> None:
        provider = _BudgetBustingProvider()
        with pytest.raises(BudgetExceededError) as exc_info:
            generate_action_for_repo(
                _make_repo("budget-repo"), goal="test", provider=provider, model="m"
            )
        assert "budget-repo" in exc_info.value.feature

    def test_expected_impact_none_preserved(self) -> None:
        provider = _FakeProvider(_valid_json_response(expected_impact=None))
        action = generate_action_for_repo(_make_repo(), goal="test", provider=provider, model="m")
        assert action is not None
        assert action.expected_impact is None

    def test_json_inside_markdown_fence_parsed(self) -> None:
        """Provider wraps JSON in a ```json ... ``` fence — should still parse."""
        inner = _valid_json_response()
        fenced = f"```json\n{inner}\n```"
        provider = _FakeProvider(fenced)
        action = generate_action_for_repo(_make_repo(), goal="test", provider=provider, model="m")
        assert action is not None
        assert action.action_type == "add_topics"


# ── generate_plan ─────────────────────────────────────────────────────────────


class TestGeneratePlan:
    def test_walks_candidates_and_builds_packet(self) -> None:
        repos = _make_repos(["repo-a", "repo-b", "repo-c"])
        provider = _FakeProvider(_valid_json_response())
        packet = generate_plan(repos, goal="add topics to everything", provider=provider, model="m")
        assert isinstance(packet, CampaignPlanPacket)
        assert packet.candidate_count == 3
        assert packet.qualified_count == 3
        assert len(packet.actions) == 3
        assert packet.goal == "add topics to everything"

    def test_skips_repos_where_prefs_suppressed(self) -> None:
        repos = _make_repos(["repo-a", "suppressed-repo", "repo-c"])
        provider = _FakeProvider(_valid_json_response())
        prefs = {
            "suppressions": [
                {
                    "action_type": "campaign-plan",
                    "target_context": "suppressed-repo",
                    "rejection_count": 5,
                    "last_rejected_at": "2026-01-01T00:00:00",
                    "suppressed_at": "2026-01-01T00:00:00",
                    "manual": False,
                }
            ]
        }
        packet = generate_plan(repos, goal="test", provider=provider, model="m", prefs=prefs)
        assert packet.candidate_count == 3
        assert packet.qualified_count == 2
        repo_names = [a.repo_name for a in packet.actions]
        assert "suppressed-repo" not in repo_names

    def test_qualifies_false_repo_not_in_actions(self) -> None:
        def _provider_for_repo(prompt: str, model: str, max_tokens: int, **_kw: Any) -> str:
            # Only qualify repos containing "good" in the prompt
            qualifies = "good-repo" in prompt
            return _valid_json_response(qualifies=qualifies)

        class _SelectiveProvider:
            def generate(self, prompt: str, model: str, max_tokens: int, **kw: Any) -> str:
                return _provider_for_repo(prompt, model, max_tokens, **kw)

        repos = _make_repos(["bad-repo", "good-repo"])
        packet = generate_plan(repos, goal="test", provider=_SelectiveProvider(), model="m")
        assert packet.qualified_count == 1
        assert packet.actions[0].repo_name == "good-repo"

    def test_empty_candidates_returns_zero_qualified(self) -> None:
        provider = _FakeProvider(_valid_json_response())
        packet = generate_plan([], goal="test", provider=provider, model="m")
        assert packet.candidate_count == 0
        assert packet.qualified_count == 0
        assert packet.actions == []

    def test_cost_tracked_in_packet(self) -> None:
        repos = _make_repos(["repo-a"])
        cost_tracker = CostTracker(budget_usd=None, output_path=None)
        provider = _FakeProvider(_valid_json_response(), cost_per_call=0.001)
        packet = generate_plan(
            repos, goal="test", provider=provider, model="m", cost_tracker=cost_tracker
        )
        assert packet.llm_cost_usd > 0


# ── write_packet_to_ledger ────────────────────────────────────────────────────


class TestWritePacketToLedger:
    def _make_packet(self, goal: str = "archive dead repos") -> CampaignPlanPacket:
        actions = [
            CampaignAction(
                repo_name="old-repo",
                action_type="archive",
                target="archive",
                rationale="No commits in 3 years",
                expected_impact="Cleaner portfolio",
            )
        ]
        return CampaignPlanPacket(
            goal=goal,
            actions=actions,
            candidate_count=5,
            qualified_count=1,
            llm_provider="fake",
            llm_model="fake-model",
            llm_cost_usd=0.001,
            generated_at="2026-05-12T00:00:00+00:00",
        )

    def test_returns_record_id_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet = self._make_packet()
            record_id = write_packet_to_ledger(packet, output_dir=output_dir, reviewer="tester")
            assert isinstance(record_id, str)
            assert record_id.startswith("cp-")

    def test_record_can_be_read_back_from_ledger(self) -> None:
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet = self._make_packet()
            record_id = write_packet_to_ledger(packet, output_dir=output_dir, reviewer="tester")

            records = load_approval_records(output_dir, username="", limit=10)
            matching = [r for r in records if r.get("approval_id") == record_id]
            assert len(matching) == 1
            rec = matching[0]
            assert rec["approval_subject_type"] == "campaign-plan"
            assert rec["goal"] == "archive dead repos"
            assert len(rec["actions"]) == 1
            assert rec["actions"][0]["repo_name"] == "old-repo"

    def test_different_goals_produce_different_record_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            p1 = self._make_packet("goal one")
            p2 = CampaignPlanPacket(
                goal="goal two",
                actions=[],
                candidate_count=0,
                qualified_count=0,
                llm_provider="fake",
                llm_model="m",
                llm_cost_usd=0.0,
                generated_at="2026-05-12T00:00:01+00:00",
            )
            id1 = write_packet_to_ledger(p1, output_dir=output_dir, reviewer="r")
            id2 = write_packet_to_ledger(p2, output_dir=output_dir, reviewer="r")
            assert id1 != id2


# ── CLI dispatch ──────────────────────────────────────────────────────────────


class TestCLIDispatch:
    """Integration-style tests for the --plan-campaign CLI wiring."""

    def _make_truth_file(self, output_dir: Path, repos: list[dict]) -> None:
        truth = {"repos": repos}
        (output_dir / "portfolio-truth-latest.json").write_text(json.dumps(truth))

    def test_report_subcommand_calls_run_plan_campaign_mode(self) -> None:
        """audit report --plan-campaign 'goal' someuser → dispatches _run_plan_campaign_mode."""
        with patch("src.cli._run_plan_campaign_mode") as mock_dispatch:
            with patch(
                "sys.argv",
                [
                    "audit",
                    "report",
                    "someuser",
                    "--plan-campaign",
                    "archive dead repos",
                    "--output-dir",
                    "/tmp",
                ],
            ):
                try:
                    from src.cli import main

                    main()
                except SystemExit:
                    pass
                except Exception:  # noqa: BLE001
                    pass
        mock_dispatch.assert_called_once()

    def test_legacy_cli_plan_campaign_flag_parsed(self) -> None:
        """Legacy flat form: audit someuser --plan-campaign 'goal' parses correctly."""
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["someuser", "--plan-campaign", "my goal"])
        assert args.plan_campaign == "my goal"

    def test_legacy_invocation_emits_deprecation_warning(self) -> None:
        """audit someuser --plan-campaign 'goal' via legacy path calls _emit_legacy_deprecation_warning."""
        with patch("src.cli._run_plan_campaign_mode"):
            with patch("src.cli._emit_legacy_deprecation_warning") as mock_warn:
                with patch(
                    "sys.argv",
                    [
                        "audit",
                        "someuser",
                        "--plan-campaign",
                        "test goal",
                        "--output-dir",
                        "/tmp",
                    ],
                ):
                    try:
                        from src.cli import main

                        main()
                    except SystemExit:
                        pass
                    except Exception:  # noqa: BLE001
                        pass
                mock_warn.assert_called_once()

    def test_boot_no_truth_file_exits_cleanly(self) -> None:
        """--plan-campaign with no portfolio-truth-latest.json exits with meaningful message."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            # No truth file

            captured_output: list[str] = []
            with patch("src.cli.print_info", side_effect=lambda msg: captured_output.append(msg)):
                with patch(
                    "sys.argv",
                    [
                        "audit",
                        "report",
                        "someuser",
                        "--plan-campaign",
                        "test goal",
                        "--output-dir",
                        str(output_dir),
                    ],
                ):
                    try:
                        from src.cli import main

                        main()
                    except SystemExit:
                        pass
                    except Exception:  # noqa: BLE001
                        pass

            # Should have printed a meaningful message about missing truth file
            all_output = " ".join(captured_output).lower()
            assert any(
                kw in all_output
                for kw in ["portfolio-truth", "truth", "not found", "missing", "run"]
            ), f"Expected truth-file message, got: {all_output!r}"
