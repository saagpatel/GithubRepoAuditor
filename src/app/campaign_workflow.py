"""Campaign planning, ledger execution, and README drafting flows.

Function-local imports deliberately preserve optional integration behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.cli_output import print_info
from src.portfolio_truth_types import truth_latest_path


def _run_campaign_from_ledger_mode(args) -> None:
    """Dispatch for --campaign-from-ledger [--writeback-apply] [--dry-run].

    Loads approved campaign-plan packets from the ledger and executes each
    action via the existing apply executor map.  Dry-run mode prints what would
    be executed without calling the GitHub API.
    """
    from src.cache import ResponseCache
    from src.github_client import GitHubClient
    from src.plan_campaign import (
        dispatch_action,
        load_approved_campaign_plans,
        mark_campaign_applied,
        record_campaign_apply_failure,
    )

    output_dir = Path(args.output_dir)
    dry_run = getattr(args, "dry_run", False)
    username = getattr(args, "username", "") or ""

    cache = None if args.no_cache else ResponseCache()
    client = GitHubClient(token=args.token, cache=cache)

    packets = load_approved_campaign_plans(output_dir)

    if not packets:
        print_info("campaign-from-ledger: 0 approved packets found — nothing to apply.")
        return

    verb = "preview" if dry_run else "apply"
    print_info(f"campaign-from-ledger: {len(packets)} approved packet(s) to {verb}.")

    for packet in packets:
        print_info(f"  packet goal: {packet.goal[:80]!r} ({len(packet.actions)} actions)")

        action_results: list[tuple[bool, str]] = []
        for action in packet.actions:
            # 7B.5 — only dispatch actions that have been explicitly approved;
            # skip pending and rejected actions.
            action_state = getattr(action, "state", "pending") or "pending"
            if action_state != "approved":
                skip_label = "rejected" if action_state == "rejected" else "pending"
                print_info(f"    [skip:{skip_label}] {action.action_type} {action.repo_name}")
                action_results.append((True, f"skipped ({skip_label})"))
                continue

            if dry_run:
                # Dry-run: print preview, record as success for state purposes
                msg = (
                    f"would execute: {action.action_type} {action.repo_name}"
                    f" (target={action.target!r}, rationale={action.rationale[:60]!r})"
                )
                print_info(f"    [dry-run] {msg}")
                action_results.append((True, msg))
            else:
                ok, msg = dispatch_action(
                    action,
                    client=client,
                    owner=username,
                    dry_run=False,
                )
                status = "ok" if ok else "FAIL"
                print_info(f"    [{status}] {action.action_type} {action.repo_name}: {msg}")
                action_results.append((ok, msg))

        if dry_run:
            # Do not mutate ledger state on dry-run
            continue

        # 7B.5 — only mark applied when every action is terminal (approved+applied or rejected).
        # If any action is still pending, leave as approved-manual for the operator to revisit.
        has_pending = any(
            (getattr(a, "state", "pending") or "pending") == "pending" for a in packet.actions
        )
        if has_pending:
            print_info(
                "  packet kept approved-manual — some actions still pending per-action review"
            )
            continue

        # Determine overall packet success:
        # "applied" only when every supported action succeeded AND every
        # unsupported/pending action is in the packet as pending_human_action.
        # Mixed-result packets (a supported action failed) stay approved-manual
        # with a failure event listing the failed actions.
        supported_results = [
            (ok, msg)
            for (ok, msg), action in zip(action_results, packet.actions)
            if action.action_type
            not in ("pending_human_action", "add_license", "add_codeowners", "enable_dependabot")
            and (getattr(action, "state", "pending") or "pending") != "rejected"
        ]
        unsupported_results = [
            (ok, msg)
            for (ok, msg), action in zip(action_results, packet.actions)
            if action.action_type in ("add_license", "add_codeowners", "enable_dependabot")
        ]

        # Unimplemented-handler actions are expected failures — don't penalise the packet
        # as long as no genuinely-supported action failed.
        failed_supported = [(ok, msg) for ok, msg in supported_results if not ok]

        if not failed_supported:
            mark_campaign_applied(packet, output_dir)
            print_info(
                f"  packet marked applied "
                f"(supported={len(supported_results)}, skipped={len(unsupported_results)})"
            )
        else:
            error_summary = "; ".join(msg for _, msg in failed_supported)
            record_campaign_apply_failure(packet, error_summary, output_dir)
            print_info(
                f"  packet kept approved-manual — {len(failed_supported)} failure(s): {error_summary[:120]}"
            )

def _run_plan_campaign_mode(args) -> None:
    """Dispatch for --plan-campaign: generate a goal-driven campaign plan packet."""
    from src.approval_ledger import default_approval_reviewer as _default_reviewer
    from src.llm_cost import BudgetExceededError, CostTracker
    from src.narrative import _resolve_provider
    from src.operator_prefs import load_prefs, prefs_path
    from src.plan_campaign import generate_plan, narrow_candidates, write_packet_to_ledger
    from src.warehouse import WAREHOUSE_FILENAME

    output_dir = Path(args.output_dir)
    goal: str = str(args.plan_campaign).strip()
    max_repos: int = int(getattr(args, "max_repos", 50) or 50)
    reviewer: str = getattr(args, "approval_reviewer", None) or _default_reviewer()

    # ── Load audit results from portfolio-truth-latest.json ───────────────────
    truth_path = truth_latest_path(output_dir)
    if not truth_path.exists():
        print_info(
            f"portfolio-truth-latest.json not found in {output_dir}. "
            "Run `audit report --portfolio-truth` first to generate repo data. "
            "--plan-campaign requires a truth snapshot to select candidates."
        )
        return

    try:
        raw = json.loads(truth_path.read_text(encoding="utf-8"))
        audit_results: list[dict] = list(raw.get("repos", raw.get("results", [])))
    except (OSError, json.JSONDecodeError) as exc:
        print_info(f"Error reading portfolio-truth-latest.json: {exc}")
        return

    # ── Semantic index (optional — fallback to alphabetical if unavailable) ────
    semantic_index = None
    warehouse_path = output_dir / WAREHOUSE_FILENAME
    if warehouse_path.exists():
        try:
            from src.semantic_index import SemanticIndex

            semantic_index = SemanticIndex(output_dir)
        except Exception as exc:  # noqa: BLE001
            print_info(
                f"Warning: could not load SemanticIndex: {exc} — using alphabetical fallback."
            )

    # ── LLM provider ──────────────────────────────────────────────────────────
    provider_result = _resolve_provider(
        getattr(args, "narrative_provider", None),
        getattr(args, "narrative_model", None),
        getattr(args, "token", None),
    )
    if provider_result is None:
        print_info(
            "No LLM provider available for --plan-campaign. "
            "Set ANTHROPIC_API_KEY or GITHUB_TOKEN, or pass --narrative-provider."
        )
        return
    provider, model = provider_result

    # ── Cost tracker ──────────────────────────────────────────────────────────
    budget_usd = getattr(args, "max_llm_spend", None)
    cost_tracker: CostTracker = CostTracker(budget_usd=budget_usd, output_path=output_dir)

    # ── Operator prefs ────────────────────────────────────────────────────────
    pref_file = prefs_path(output_dir)
    prefs = load_prefs(pref_file)

    # ── Narrow candidates ─────────────────────────────────────────────────────
    candidates = narrow_candidates(
        audit_results,
        goal=goal,
        semantic_index=semantic_index,
        max_repos=max_repos,
    )
    if not candidates:
        print_info("No candidate repos found. Check that portfolio-truth-latest.json has data.")
        return

    # ── Generate plan ─────────────────────────────────────────────────────────
    import sys

    try:
        packet = generate_plan(
            candidates,
            goal=goal,
            provider=provider,
            model=model,
            cost_tracker=cost_tracker,
            prefs=prefs,
        )
    except BudgetExceededError as exc:
        print(f"\nERROR: LLM budget exceeded during campaign planning: {exc}", file=sys.stderr)
        return

    # ── Persist packet to ledger ──────────────────────────────────────────────
    record_id = write_packet_to_ledger(packet, output_dir=output_dir, reviewer=reviewer)

    cost_tracker.write_telemetry()

    pending_count = sum(1 for a in packet.actions if a.action_type == "pending_human_action")
    print_info(
        f"Goal: {goal}. "
        f"Considered {packet.candidate_count}. "
        f"Qualified {packet.qualified_count}. "
        f"{pending_count} pending human review. "
        f"LLM cost: ${packet.llm_cost_usd:.4f}. "
        f"Packet ID: {record_id}."
    )

def _run_draft_readmes_mode(args) -> None:
    """Dispatch for --draft-readmes: generate LLM-authored README draft packets."""
    import sys

    from src.approval_ledger import default_approval_reviewer as _default_reviewer
    from src.draft_readmes import (
        build_context,
        generate_draft,
        qualify_repos,
        write_packets_to_ledger,
    )
    from src.llm_cost import BudgetExceededError, CostTracker
    from src.narrative import _resolve_provider
    from src.operator_prefs import (
        is_suppressed,
        load_prefs,
        post_process_approval_session,
        prefs_path,
    )

    output_dir = Path(args.output_dir)
    opt_in_repos: list[str] = list(getattr(args, "draft_readmes_repos", None) or [])
    all_qualifying: bool = bool(getattr(args, "draft_readmes_all", False))
    reviewer: str = getattr(args, "approval_reviewer", None) or _default_reviewer()

    if not opt_in_repos and not all_qualifying:
        print_info(
            "--draft-readmes requires --draft-readmes-all or at least one --draft-readmes-repo. "
            "No repos selected."
        )
        return

    # ── Load audit results (portfolio-truth-latest.json or warehouse) ─────────
    audit_results: list[dict] = []
    truth_path = truth_latest_path(output_dir)
    if truth_path.exists():
        try:
            raw = json.loads(truth_path.read_text(encoding="utf-8"))
            audit_results = list(raw.get("repos", raw.get("results", [])))
        except (OSError, json.JSONDecodeError) as exc:
            print_info(f"Warning: could not read portfolio-truth-latest.json: {exc}")
    else:
        print_info(
            f"portfolio-truth-latest.json not found in {output_dir}. "
            "Run `audit report --portfolio-truth` first to populate repo data. "
            "Proceeding with empty repo list — only explicit --draft-readmes-repo repos will be drafted."
        )

    # ── Qualify repos ──────────────────────────────────────────────────────────
    repo_names = qualify_repos(
        audit_results, opt_in_repos=opt_in_repos, all_qualifying=all_qualifying
    )
    if not repo_names:
        print_info("No repos qualify for --draft-readmes with current flags.")
        return

    # Build a name → dict lookup for fast access
    repo_by_name: dict[str, dict] = {
        str(r.get("repo_name") or r.get("name") or ""): r for r in audit_results
    }
    # Repos requested via --draft-readmes-repo may not exist in audit_results — create stubs
    for name in repo_names:
        if name not in repo_by_name:
            repo_by_name[name] = {"repo_name": name, "name": name}

    # ── Semantic index (optional — proceed without neighbors if unavailable) ────
    semantic_index = None
    warehouse_path = output_dir / "portfolio-warehouse.db"
    if warehouse_path.exists():
        try:
            from src.semantic_index import SemanticIndex

            semantic_index = SemanticIndex(output_dir)
        except Exception as exc:  # noqa: BLE001
            print_info(
                f"Warning: could not load SemanticIndex: {exc} — proceeding without neighbors."
            )

    # ── LLM provider ──────────────────────────────────────────────────────────
    provider_result = _resolve_provider(
        getattr(args, "narrative_provider", None),
        getattr(args, "narrative_model", None),
        getattr(args, "token", None),
    )
    if provider_result is None:
        print_info(
            "No LLM provider available for --draft-readmes. "
            "Set ANTHROPIC_API_KEY or GITHUB_TOKEN, or pass --narrative-provider."
        )
        return
    provider, model = provider_result

    # ── Cost tracker ──────────────────────────────────────────────────────────
    cost_tracker: CostTracker | None = None
    budget_usd = getattr(args, "max_llm_spend", None)
    if budget_usd is not None or True:  # always track telemetry
        cost_tracker = CostTracker(budget_usd=budget_usd, output_path=output_dir)

    # ── Operator prefs ────────────────────────────────────────────────────────
    pref_file = prefs_path(output_dir)
    prefs = load_prefs(pref_file)

    # ── Main loop ─────────────────────────────────────────────────────────────
    packets = []
    skipped_suppressed = 0
    skipped_budget = 0
    errors = 0

    for repo_name in repo_names:
        # 5.3 — suppression check
        if is_suppressed(prefs, action_type="draft-readme", target_context=repo_name):
            print_info(f"  skip {repo_name}: suppressed by operator prefs")
            skipped_suppressed += 1
            continue

        repo = repo_by_name[repo_name]
        context = build_context(repo, semantic_index=semantic_index)

        try:
            packet = generate_draft(
                repo, context=context, provider=provider, model=model, cost_tracker=cost_tracker
            )
            packets.append(packet)
            print_info(f"  drafted {repo_name} ({packet.diff_summary})")
        except BudgetExceededError as exc:
            print(f"\nERROR: LLM budget exceeded at {repo_name}: {exc}", file=sys.stderr)
            skipped_budget = len(repo_names) - len(packets) - skipped_suppressed - 1
            break
        except Exception as exc:  # noqa: BLE001
            print_info(f"  error drafting {repo_name}: {exc}")
            errors += 1

    # ── Persist packets ────────────────────────────────────────────────────────
    if packets:
        write_packets_to_ledger(packets, output_dir, reviewer)

    # ── Refresh suppressions from rejection history ────────────────────────────
    # We pass an empty list here — newly-generated drafts have no decision yet,
    # so detect_suppressions would find zero consecutive rejections. The real
    # suppression update happens when the operator rejects via approval_request_reject.
    # Calling post_process_approval_session with [] is a no-op but keeps the prefs
    # file consistent and auto-prunes stale hints if any exist.
    if pref_file.parent.exists():
        try:
            post_process_approval_session([], output_dir)
        except Exception as exc:  # noqa: BLE001
            print_info(f"Warning: could not refresh suppression hints: {exc}")

    if cost_tracker is not None:
        cost_tracker.write_telemetry()

    total_cost = cost_tracker.total_usd() if cost_tracker is not None else 0.0
    print_info(
        f"Drafted {len(packets)} packet(s) for {len(packets)} repo(s). "
        f"{skipped_suppressed} skipped (prefs). "
        f"{skipped_budget} skipped (budget). "
        f"{errors} error(s). "
        f"LLM cost: ${total_cost:.4f}."
    )
