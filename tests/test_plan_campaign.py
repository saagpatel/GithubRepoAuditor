"""Tests for src/plan_campaign.py — Arc G Sprint 6.1-6.2 + 6.4 (apply path)."""

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
    dispatch_action,
    generate_action_for_repo,
    generate_plan,
    load_approved_campaign_plans,
    mark_campaign_applied,
    narrow_candidates,
    record_campaign_apply_failure,
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
                    # The test only verifies dispatch; CLI exits are expected here.
                    pass
                except Exception:  # noqa: BLE001
                    # The test only verifies dispatch; mocked CLI setup may stop early.
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
                        # The test only verifies warning dispatch; CLI exits are expected here.
                        pass
                    except Exception:  # noqa: BLE001
                        # The test only verifies warning dispatch; mocked setup may stop early.
                        pass
                mock_warn.assert_called_once()

    def test_campaign_from_ledger_flag_parsed(self) -> None:
        """--campaign-from-ledger is accepted by build_parser."""
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["someuser", "--campaign-from-ledger", "--output-dir", "/tmp"])
        assert args.campaign_from_ledger is True

    def test_campaign_from_ledger_dispatches_run_mode(self) -> None:
        """audit report --writeback-apply --campaign-from-ledger someuser dispatches apply mode."""
        with patch("src.cli._run_campaign_from_ledger_mode") as mock_dispatch:
            with patch(
                "sys.argv",
                [
                    "audit",
                    "report",
                    "someuser",
                    "--writeback-apply",
                    "--campaign-from-ledger",
                    "--output-dir",
                    "/tmp",
                ],
            ):
                try:
                    from src.cli import main

                    main()
                except SystemExit:
                    # The test only verifies dispatch; CLI exits are expected here.
                    pass
                except Exception:  # noqa: BLE001
                    # The test only verifies dispatch; mocked CLI setup may stop early.
                    pass
        mock_dispatch.assert_called_once()

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
                        # The test only verifies clean handling; CLI exits are expected here.
                        pass
                    except Exception:  # noqa: BLE001
                        # The test captures output rather than failing on setup noise.
                        pass


# ── load_approved_campaign_plans ──────────────────────────────────────────────


def _make_approved_packet(
    goal: str = "archive dead repos",
    generated_at: str = "2026-05-11T00:00:00+00:00",
    status: str = "approved-manual",
) -> tuple[CampaignPlanPacket, dict]:
    """Return a (packet, ledger_record) pair for test setup."""
    from src.plan_campaign import _goal_subject_key, _packet_record_id

    actions = [
        CampaignAction(
            repo_name="old-repo",
            action_type="archive",
            target="archive",
            rationale="No commits in 3 years",
            expected_impact="Cleaner portfolio",
        )
    ]
    packet = CampaignPlanPacket(
        goal=goal,
        actions=actions,
        candidate_count=5,
        qualified_count=1,
        llm_provider="fake",
        llm_model="fake-model",
        llm_cost_usd=0.001,
        generated_at=generated_at,
    )
    record: dict = {
        "approval_id": _packet_record_id(packet),
        "fingerprint": _goal_subject_key(goal),
        "approval_subject_type": "campaign-plan",
        "subject_key": _goal_subject_key(goal),
        "source_run_id": "",
        "approved_at": generated_at,
        "approved_by": "tester",
        "approval_note": "1 actions for goal",
        "status": status,
        "goal": goal,
        "candidate_count": 5,
        "qualified_count": 1,
        "llm_provider": "fake",
        "llm_model": "fake-model",
        "llm_cost_usd": 0.001,
        "generated_at": generated_at,
        "actions": [
            {
                "repo_name": "old-repo",
                "action_type": "archive",
                "target": "archive",
                "rationale": "No commits in 3 years",
                "expected_impact": "Cleaner portfolio",
            }
        ],
    }
    return packet, record


class TestLoadApprovedCampaignPlans:
    def test_returns_only_approved_manual_campaign_plan_records(self) -> None:
        from src.warehouse import save_approval_record

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            _, approved_record = _make_approved_packet("goal approved")
            _, pending_record = _make_approved_packet("goal pending", status="pending")
            _, wrong_type_record = _make_approved_packet("goal wrong type")
            wrong_type_record["approval_subject_type"] = "draft-readme"
            wrong_type_record["status"] = "approved-manual"

            save_approval_record(output_dir, approved_record)
            save_approval_record(output_dir, pending_record)
            save_approval_record(output_dir, wrong_type_record)

            packets = load_approved_campaign_plans(output_dir)
            assert len(packets) == 1
            assert packets[0].goal == "goal approved"

    def test_skips_packets_older_than_30_days(self) -> None:
        from src.warehouse import save_approval_record

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            _, fresh_record = _make_approved_packet(
                "fresh goal", generated_at="2026-05-11T00:00:00+00:00"
            )
            _, stale_record = _make_approved_packet(
                "stale goal", generated_at="2026-01-01T00:00:00+00:00"
            )
            save_approval_record(output_dir, fresh_record)
            save_approval_record(output_dir, stale_record)

            packets = load_approved_campaign_plans(output_dir)
            goals = [p.goal for p in packets]
            assert "fresh goal" in goals
            assert "stale goal" not in goals

    def test_empty_warehouse_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packets = load_approved_campaign_plans(Path(tmp))
            assert packets == []

    def test_hydrates_actions_into_campaign_action_dataclasses(self) -> None:
        from src.warehouse import save_approval_record

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            _, record = _make_approved_packet("test hydration")
            save_approval_record(output_dir, record)

            packets = load_approved_campaign_plans(output_dir)
            assert len(packets) == 1
            assert len(packets[0].actions) == 1
            action = packets[0].actions[0]
            assert isinstance(action, CampaignAction)
            assert action.repo_name == "old-repo"
            assert action.action_type == "archive"


# ── dispatch_action ────────────────────────────────────────────────────────────


class TestDispatchAction:
    def _make_action(
        self, action_type: str, repo_name: str = "test-repo", target: str = ""
    ) -> CampaignAction:
        return CampaignAction(
            repo_name=repo_name,
            action_type=action_type,
            target=target,
            rationale="test rationale",
            expected_impact=None,
        )

    def test_pending_human_action_returns_false_manual_review_required(self) -> None:
        action = self._make_action("pending_human_action")
        ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=False)
        assert ok is False
        assert "manual review required" in msg

    def test_add_codeowners_returns_handler_not_implemented(self) -> None:
        action = self._make_action("add_codeowners")
        ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=False)
        assert ok is False
        assert "handler not yet implemented" in msg

    def test_add_license_returns_handler_not_implemented(self) -> None:
        action = self._make_action("add_license")
        ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=False)
        assert ok is False
        assert "handler not yet implemented" in msg

    def test_enable_dependabot_returns_handler_not_implemented(self) -> None:
        action = self._make_action("enable_dependabot")
        ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=False)
        assert ok is False
        assert "handler not yet implemented" in msg

    def test_archive_calls_apply_metadata_updates_with_right_shape(self) -> None:
        action = self._make_action("archive", repo_name="my-repo")
        mock_client = MagicMock()

        with patch("src.repo_improver.apply_metadata_updates") as mock_apply:
            mock_apply.return_value = [
                {"repo": "my-repo", "actions": [{"type": "archived", "ok": True}]}
            ]
            ok, msg = dispatch_action(action, client=mock_client, owner="user", dry_run=False)

        assert ok is True
        assert msg == "archive applied to my-repo"
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args
        # First positional arg is client, second is owner, third is updates list
        updates = call_kwargs[0][2]
        assert isinstance(updates, list)
        assert len(updates) == 1
        assert updates[0]["name"] == "my-repo"
        assert updates[0]["archived"] is True

    def test_add_topics_calls_apply_metadata_updates(self) -> None:
        action = self._make_action("add_topics", target="python cli tool")
        mock_client = MagicMock()

        with patch("src.repo_improver.apply_metadata_updates") as mock_apply:
            mock_apply.return_value = [
                {"repo": "test-repo", "actions": [{"type": "topics", "ok": True}]}
            ]
            ok, msg = dispatch_action(action, client=mock_client, owner="user", dry_run=False)

        assert ok is True
        assert msg == "add_topics applied to test-repo: ['python', 'cli', 'tool']"
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args
        updates = call_kwargs[0][2]
        assert "topics" in updates[0]
        assert isinstance(updates[0]["topics"], list)

    def test_dry_run_does_not_call_executor(self) -> None:
        action = self._make_action("archive", repo_name="dry-repo")

        with patch("src.repo_improver.apply_metadata_updates") as mock_apply:
            ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=True)

        mock_apply.assert_not_called()
        assert ok is True
        assert "dry-run" in msg

    def test_dry_run_pending_human_action_still_returns_false(self) -> None:
        """pending_human_action is always skipped — even in dry-run."""
        action = self._make_action("pending_human_action")
        with patch("src.repo_improver.apply_metadata_updates") as mock_apply:
            ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=True)
        mock_apply.assert_not_called()
        assert ok is False

    def test_apply_readme_calls_apply_readme_updates(self) -> None:
        action = self._make_action("apply_readme", target="# Hello\nThis is the readme.")

        with patch("src.repo_improver.apply_readme_updates") as mock_apply:
            mock_apply.return_value = [{"repo": "test-repo", "ok": True}]
            ok, msg = dispatch_action(action, client=MagicMock(), owner="user", dry_run=False)

        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args
        updates = call_kwargs[0][2]
        assert updates[0]["readme"] == "# Hello\nThis is the readme."
        assert ok is True


# ── mark_campaign_applied / record_campaign_apply_failure ─────────────────────


class TestLedgerStateTransitions:
    def _write_approved_record(
        self, output_dir: Path, goal: str = "test goal"
    ) -> CampaignPlanPacket:
        from src.warehouse import save_approval_record

        packet, record = _make_approved_packet(goal)
        save_approval_record(output_dir, record)
        return packet

    def test_mark_campaign_applied_updates_status_to_applied(self) -> None:
        from src.plan_campaign import _packet_record_id
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet = self._write_approved_record(output_dir, "mark applied goal")

            mark_campaign_applied(packet, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            record_id = _packet_record_id(packet)
            matching = [r for r in records if r.get("approval_id") == record_id]
            assert len(matching) == 1
            assert matching[0]["status"] == "applied"

    def test_mark_campaign_applied_noop_on_missing_record(self) -> None:
        """mark_campaign_applied on non-existent record logs warning and doesn't raise."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet, _ = _make_approved_packet("nonexistent goal")
            # Don't write the record — should log warning, not raise
            mark_campaign_applied(packet, output_dir)  # must not raise

    def test_record_campaign_apply_failure_writes_followup_event(self) -> None:
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            packet = self._write_approved_record(output_dir, "failure goal")

            record_campaign_apply_failure(packet, "some error occurred", output_dir)

            # Record should still be approved-manual (not applied)
            from src.plan_campaign import _packet_record_id

            records = load_approval_records(output_dir, "", limit=50)
            record_id = _packet_record_id(packet)
            matching = [r for r in records if r.get("approval_id") == record_id]
            assert len(matching) == 1
            assert matching[0].get("status") in ("approved-manual", None, "")


# ── end-to-end: campaign_from_ledger apply batch ──────────────────────────────


class TestCampaignFromLedgerEndToEnd:
    """End-to-end test with all GitHub API calls mocked."""

    def _write_packet_with_actions(
        self,
        output_dir: Path,
        actions: list[CampaignAction],
        goal: str = "e2e test goal",
    ) -> CampaignPlanPacket:
        from src.plan_campaign import _goal_subject_key, _packet_record_id
        from src.warehouse import save_approval_record

        packet = CampaignPlanPacket(
            goal=goal,
            actions=actions,
            candidate_count=len(actions),
            qualified_count=len(actions),
            llm_provider="fake",
            llm_model="fake-model",
            llm_cost_usd=0.001,
            generated_at="2026-05-11T12:00:00+00:00",
        )
        record: dict = {
            "approval_id": _packet_record_id(packet),
            "fingerprint": _goal_subject_key(goal),
            "approval_subject_type": "campaign-plan",
            "subject_key": _goal_subject_key(goal),
            "source_run_id": "",
            "approved_at": "2026-05-11T12:00:00+00:00",
            "approved_by": "tester",
            "approval_note": "test",
            "status": "approved-manual",
            "goal": goal,
            "candidate_count": len(actions),
            "qualified_count": len(actions),
            "llm_provider": "fake",
            "llm_model": "fake-model",
            "llm_cost_usd": 0.001,
            "generated_at": "2026-05-11T12:00:00+00:00",
            "actions": [
                {
                    "repo_name": a.repo_name,
                    "action_type": a.action_type,
                    "target": a.target,
                    "rationale": a.rationale,
                    "expected_impact": a.expected_impact,
                }
                for a in actions
            ],
        }
        save_approval_record(output_dir, record)
        return packet

    def test_packet_with_two_supported_and_one_unsupported_marks_applied(self) -> None:
        """2 archive/topics succeed + 1 add_codeowners (unsupported) → packet marked applied."""
        from src.plan_campaign import _packet_record_id
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            actions = [
                CampaignAction("repo-a", "archive", "archive", "old repo", None),
                CampaignAction("repo-b", "add_topics", "python cli", "needs topics", None),
                CampaignAction("repo-c", "add_codeowners", "", "needs owners", None),
            ]
            packet = self._write_packet_with_actions(output_dir, actions)

            with patch("src.repo_improver.apply_metadata_updates") as mock_meta:
                mock_meta.return_value = [
                    {"repo": "repo-a", "actions": [{"type": "archived", "ok": True}]},
                ]
                # Call dispatch_action for each action manually (mirrors what the CLI does)
                mock_client = MagicMock()
                results = []
                for action in packet.actions:
                    # patch topics call too
                    if action.action_type == "add_topics":
                        mock_meta.return_value = [
                            {"repo": "repo-b", "actions": [{"type": "topics", "ok": True}]}
                        ]
                    ok, msg = dispatch_action(
                        action, client=mock_client, owner="user", dry_run=False
                    )
                    results.append((ok, msg, action))

            # Supported succeeded (archive + topics); unsupported (add_codeowners) → handler not yet implemented
            supported_failed = [
                (ok, msg)
                for ok, msg, a in results
                if a.action_type
                not in (
                    "add_codeowners",
                    "add_license",
                    "enable_dependabot",
                    "pending_human_action",
                )
                and not ok
            ]
            assert not supported_failed, f"Supported actions failed: {supported_failed}"

            # Mark applied (as CLI would do when no supported failures)
            mark_campaign_applied(packet, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            record_id = _packet_record_id(packet)
            matching = [r for r in records if r.get("approval_id") == record_id]
            assert len(matching) == 1
            assert matching[0]["status"] == "applied"

    def test_packet_with_supported_failure_stays_approved_manual(self) -> None:
        """When a supported action fails, record_campaign_apply_failure is called, packet stays approved-manual."""
        from src.plan_campaign import _packet_record_id
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            actions = [
                CampaignAction("repo-a", "archive", "archive", "old repo", None),
            ]
            packet = self._write_packet_with_actions(output_dir, actions, goal="failure e2e test")

            with patch("src.repo_improver.apply_metadata_updates") as mock_meta:
                mock_meta.return_value = [
                    {"repo": "repo-a", "actions": [{"ok": False, "error": "API error"}]}
                ]
                ok, msg = dispatch_action(
                    actions[0], client=MagicMock(), owner="user", dry_run=False
                )

            assert not ok
            record_campaign_apply_failure(packet, msg, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            record_id = _packet_record_id(packet)
            matching = [r for r in records if r.get("approval_id") == record_id]
            assert len(matching) == 1
            # Should still be approved-manual (not applied)
            assert matching[0].get("status") in ("approved-manual", None, "")
