"""Tests for the new audit run / triage / report / serve subcommands.

These tests exercise:
  1. Subcommand parsing routes flags to the right namespace attrs.
  2. Legacy flat invocation still parses and emits DeprecationWarning.
  3. --help flag counts stay within spec limits.
  4. audit serve / --serve still resolves without a username.

All tests use parser.parse_args() directly — no subprocess, no I/O.
Legacy invocation tests go through _rewrite_legacy_argv + parse_args to
mirror what main() does at runtime.
"""

from __future__ import annotations

import io
import re
import warnings

import src.cli as cli_module

_infer_subcommand_from_flags = cli_module._infer_subcommand_from_flags
_rewrite_legacy_argv = cli_module._rewrite_legacy_argv
build_parser = cli_module.build_parser
build_subcommand_parser = cli_module.build_subcommand_parser

# ── Helper ────────────────────────────────────────────────────────────


def _parse(*argv: str):
    """Parse a subcommand-form argv through the subcommand parser."""
    parser = build_subcommand_parser()
    return parser.parse_args(list(argv))


def _parse_legacy(*argv: str):
    """Simulate main()'s legacy rewrite + parse path."""
    rewritten, _ = _rewrite_legacy_argv(list(argv))
    parser = build_subcommand_parser()
    return parser.parse_args(rewritten)


def _help_text(subcommand: str) -> str:
    """Return the --help output for a subcommand as a string."""
    parser = build_subcommand_parser()
    buf = io.StringIO()
    import contextlib

    with contextlib.suppress(SystemExit):
        with contextlib.redirect_stdout(buf):
            parser.parse_args([subcommand, "--help"])
    return buf.getvalue()


def _count_flags_in_help(text: str) -> int:
    """Count '--flag' lines in help output, excluding global flags."""
    global_flags = {"--token", "--output-dir", "--config", "--verbose"}
    flags = set(re.findall(r"  (--[a-z][a-z0-9-]*)", text))
    non_global = flags - global_flags
    return len(non_global)


# ── 1. `audit run username --flag` dispatches correctly ──────────────


class TestRunSubcommand:
    def test_basic_run_subcommand(self):
        args = _parse("run", "myuser")
        assert args._subcommand == "run"
        assert args.username == "myuser"

    def test_run_with_html_flag(self):
        args = _parse("run", "myuser", "--html")
        assert args._subcommand == "run"
        assert args.username == "myuser"
        assert args.html is True

    def test_run_with_skip_forks(self):
        args = _parse("run", "myuser", "--skip-forks", "--no-cache")
        assert args.skip_forks is True
        assert args.no_cache is True

    def test_run_with_incremental(self):
        args = _parse("run", "myuser", "--incremental")
        assert args.incremental is True

    def test_run_with_repos(self):
        args = _parse("run", "myuser", "--repos", "repoA", "repoB")
        assert args.repos == ["repoA", "repoB"]

    def test_run_scoring_profile(self):
        args = _parse("run", "myuser", "--scoring-profile", "strict")
        assert args.scoring_profile == "strict"

    def test_run_watch(self):
        args = _parse("run", "myuser", "--watch")
        assert args.watch is True

    def test_run_resume(self):
        args = _parse("run", "myuser", "--resume")
        assert args.resume is True


# ── 2. Legacy `audit username --flag` still works + emits DeprecationWarning ──


class TestLegacyFlatInvocation:
    def test_legacy_html_parses(self):
        args = _parse_legacy("myuser", "--html")
        # After rewrite, _subcommand="run", username="myuser"
        assert args._subcommand == "run"
        assert args.username == "myuser"
        assert args.html is True

    def test_legacy_rewriter_detects_legacy(self):
        rewritten, is_legacy = _rewrite_legacy_argv(["myuser", "--html"])
        assert is_legacy is True
        assert rewritten == ["run", "myuser", "--html"]

    def test_legacy_rewriter_leaves_subcommand_form_unchanged(self):
        rewritten, is_legacy = _rewrite_legacy_argv(["run", "myuser", "--html"])
        assert is_legacy is False
        assert rewritten == ["run", "myuser", "--html"]

    def test_legacy_rewriter_leaves_serve_flag_unchanged(self):
        rewritten, is_legacy = _rewrite_legacy_argv(["--serve", "--port", "9876"])
        assert is_legacy is False

    def test_legacy_emits_deprecation_warning(self):
        cli_module._LEGACY_WARNING_EVENTS.clear()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cli_module._emit_legacy_deprecation_warning("run")
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        assert any("audit run" in str(w.message) for w in caught)
        cli_module._LEGACY_WARNING_EVENTS.clear()

    def test_legacy_warning_emits_once(self):
        cli_module._LEGACY_WARNING_EVENTS.clear()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cli_module._emit_legacy_deprecation_warning("run")
            cli_module._emit_legacy_deprecation_warning("run")
            cli_module._emit_legacy_deprecation_warning("triage")
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) == 1
        cli_module._LEGACY_WARNING_EVENTS.clear()

    def test_legacy_skip_forks(self):
        args = _parse_legacy("myuser", "--skip-forks")
        assert args.username == "myuser"
        assert args.skip_forks is True

    def test_legacy_control_center_infers_triage(self):
        rewritten, is_legacy = _rewrite_legacy_argv(["myuser", "--control-center"])
        assert is_legacy is True
        assert rewritten[0] == "triage"
        args = _parse_legacy("myuser", "--control-center")
        assert args.username == "myuser"
        assert args.control_center is True

    def test_legacy_portfolio_truth_infers_report(self):
        rewritten, is_legacy = _rewrite_legacy_argv(["myuser", "--portfolio-truth"])
        assert is_legacy is True
        assert rewritten[0] == "report"
        args = _parse_legacy("myuser", "--portfolio-truth")
        assert args.username == "myuser"
        assert args.portfolio_truth is True

    def test_legacy_campaign_infers_report(self):
        args = _parse_legacy(
            "myuser", "--campaign", "security-review", "--writeback-target", "github"
        )
        assert args.campaign == "security-review"
        assert args.writeback_target == "github"


# ── 3. `audit triage username --control-center` works ────────────────


class TestTriageSubcommand:
    def test_triage_control_center(self):
        args = _parse("triage", "myuser", "--control-center")
        assert args._subcommand == "triage"
        assert args.username == "myuser"
        assert args.control_center is True

    def test_triage_approval_center(self):
        args = _parse("triage", "myuser", "--approval-center")
        assert args._subcommand == "triage"
        assert args.approval_center is True

    def test_triage_auto_apply_approved(self):
        args = _parse("triage", "myuser", "--auto-apply-approved", "--dry-run")
        assert args.auto_apply_approved is True
        assert args.dry_run is True

    def test_triage_semantic_search(self):
        args = _parse("triage", "myuser", "--semantic-search", "ML projects")
        assert args.semantic_search == "ML projects"

    def test_triage_reset_prefs(self):
        args = _parse("triage", "myuser", "--reset-prefs")
        assert args.reset_prefs is True

    def test_triage_view_filter(self):
        args = _parse("triage", "myuser", "--triage-view", "urgent")
        assert args.triage_view == "urgent"


# ── 4. `audit report username --portfolio-truth` works ───────────────


class TestReportSubcommand:
    def test_report_portfolio_truth(self):
        args = _parse("report", "myuser", "--portfolio-truth")
        assert args._subcommand == "report"
        assert args.username == "myuser"
        assert args.portfolio_truth is True

    def test_report_campaign(self):
        args = _parse("report", "myuser", "--campaign", "security-review")
        assert args.campaign == "security-review"

    def test_report_writeback(self):
        args = _parse(
            "report", "myuser", "--campaign", "promotion-push", "--writeback-target", "github"
        )
        assert args.writeback_target == "github"

    def test_report_excel_mode(self):
        args = _parse("report", "myuser", "--excel-mode", "template")
        assert args.excel_mode == "template"

    def test_report_generate_manifest(self):
        args = _parse("report", "myuser", "--generate-manifest")
        assert args.generate_manifest is True

    def test_report_apply_context_recovery(self):
        args = _parse(
            "report", "myuser", "--portfolio-context-recovery", "--apply-context-recovery"
        )
        assert args.portfolio_context_recovery is True
        assert args.apply_context_recovery is True


# ── 5. `audit serve` / `audit --serve` still works ───────────────────


class TestServeSubcommand:
    def test_serve_subcommand_parses(self):
        args = _parse("serve")
        assert args._subcommand == "serve"

    def test_serve_with_port(self):
        args = _parse("serve", "--port", "9876")
        assert args._subcommand == "serve"
        assert args.port == 9876

    def test_serve_with_host(self):
        args = _parse("serve", "--host", "0.0.0.0")
        assert args.host == "0.0.0.0"

    def test_legacy_serve_flag(self):
        # --serve at the top level (legacy Sprint 4.1 form) still parses
        # via the legacy build_parser() which retains --serve as a flat flag
        parser = build_parser()
        args = parser.parse_args(["--serve"])
        assert getattr(args, "_subcommand", None) is None
        assert args.serve is True

    def test_legacy_serve_with_port(self):
        parser = build_parser()
        args = parser.parse_args(["--serve", "--port", "9876"])
        assert args.serve is True
        assert args.port == 9876

    def test_legacy_parser_accepts_arc_h_report_flags(self):
        parser = build_parser()
        args = parser.parse_args(["saagpatel", "--context-triage", "--tier-recalibration-report"])
        assert args.context_triage is True
        assert args.tier_recalibration_report is True


# ── 6/7/8. --help flag counts ≤ limits ───────────────────────────────


class TestHelpFlagCounts:
    def test_run_help_flag_count(self):
        text = _help_text("run")
        count = _count_flags_in_help(text)
        assert count <= 20, (
            f"audit run --help shows {count} non-global flags (limit 20).\n"
            f"Flags found: {sorted(set(re.findall(r'  (--[a-z][a-z0-9-]*)', text)))}"
        )

    def test_triage_help_flag_count(self):
        text = _help_text("triage")
        count = _count_flags_in_help(text)
        assert count <= 31, (
            f"audit triage --help shows {count} non-global flags (limit 31, raised in Arc G S12.1 for --dismiss-expires-days/--expire-dismissals/--dismissal-history).\n"
            f"Flags found: {sorted(set(re.findall(r'  (--[a-z][a-z0-9-]*)', text)))}"
        )

    def test_report_help_flag_count(self):
        text = _help_text("report")
        count = _count_flags_in_help(text)
        assert count <= 35, (
            f"audit report --help shows {count} non-global flags (limit 35, raised in Arc H for --tier-recalibration-report/--context-triage).\n"
            f"Flags found: {sorted(set(re.findall(r'  (--[a-z][a-z0-9-]*)', text)))}"
        )


# ── 9. _infer_subcommand_from_flags correctness ───────────────────────


class TestInferSubcommand:
    def _ns(self, **kw):
        from argparse import Namespace

        defaults = {
            "control_center": False,
            "approval_center": False,
            "triage_view": "all",
            "approve_governance": False,
            "approve_packet": False,
            "review_governance": False,
            "review_packet": False,
            "auto_apply_approved": False,
            "reset_prefs": False,
            "acknowledge_target": None,
            "acknowledge_kind": None,
            "semantic_search": None,
            "ask": None,
            "portfolio_truth": False,
            "portfolio_context_recovery": False,
            "apply_context_recovery": False,
            "generate_manifest": False,
            "apply_metadata": False,
            "apply_readmes": False,
            "upload_badges": False,
            "notion_sync": False,
            "campaign": None,
            "writeback_target": None,
        }
        defaults.update(kw)
        return Namespace(**defaults)

    def test_infer_run_default(self):
        assert _infer_subcommand_from_flags(self._ns()) == "run"

    def test_infer_triage_control_center(self):
        assert _infer_subcommand_from_flags(self._ns(control_center=True)) == "triage"

    def test_infer_triage_approval_center(self):
        assert _infer_subcommand_from_flags(self._ns(approval_center=True)) == "triage"

    def test_infer_triage_acknowledge(self):
        assert _infer_subcommand_from_flags(self._ns(acknowledge_target="myrepo")) == "triage"

    def test_infer_report_portfolio_truth(self):
        assert _infer_subcommand_from_flags(self._ns(portfolio_truth=True)) == "report"

    def test_infer_report_campaign(self):
        assert _infer_subcommand_from_flags(self._ns(campaign="security-review")) == "report"

    def test_infer_report_writeback(self):
        assert _infer_subcommand_from_flags(self._ns(writeback_target="github")) == "report"
