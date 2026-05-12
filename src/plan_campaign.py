"""Campaign planner — goal-driven authoring of repo-level action packets.

Arc G Sprint 6.1 — pure functions, mockable provider, no I/O except provider call
and ledger persistence.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm_cost import CostTracker
    from src.narrative import NarrativeProvider
    from src.semantic_index import SemanticIndex

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTION_TYPES = frozenset(
    [
        "archive",
        "unarchive",
        "add_license",
        "add_topics",
        "update_description",
        "apply_readme",
        "add_codeowners",
        "enable_dependabot",
        "pending_human_action",
    ]
)

#: Max tokens we ask the LLM to produce per repo classification.
_MAX_ACTION_TOKENS = 512

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignAction:
    repo_name: str
    action_type: str  # must be in ACTION_TYPES
    target: str
    rationale: str
    expected_impact: str | None = None
    # Per-action approval state (7B.1) — default "pending" for backwards compat
    state: str = "pending"
    rejected_reason: str | None = None
    decided_at: str | None = None


@dataclass(frozen=True)
class CampaignPlanPacket:
    goal: str
    actions: list[CampaignAction]
    candidate_count: int
    qualified_count: int
    llm_provider: str
    llm_model: str
    llm_cost_usd: float
    generated_at: str


# ---------------------------------------------------------------------------
# Candidate narrowing
# ---------------------------------------------------------------------------


def narrow_candidates(
    audit_results: list[dict],
    *,
    goal: str,
    semantic_index: "SemanticIndex | None",
    max_repos: int = 50,
) -> list[dict]:
    """Return up to *max_repos* repos most relevant to *goal*.

    Strategy:
      1. If *semantic_index* is available, use ``search(goal, k=max_repos)``
         to retrieve the top-k candidates by semantic similarity.
      2. Otherwise fall back to the first *max_repos* repos sorted
         alphabetically by ``repo_name``.
      3. Results are deduplicated by ``repo_name``; order is preserved.
    """
    if not audit_results:
        return []

    repo_by_name: dict[str, dict] = {}
    for r in audit_results:
        name = str(r.get("repo_name") or r.get("name") or "")
        if name and name not in repo_by_name:
            repo_by_name[name] = r

    if semantic_index is not None:
        try:
            results = semantic_index.search(goal, k=max_repos)
            ordered: list[dict] = []
            seen: set[str] = set()
            for sr in results:
                # SearchResult has a .repo_name attribute
                rname = getattr(sr, "repo_name", None) or str(sr)
                if rname and rname not in seen and rname in repo_by_name:
                    ordered.append(repo_by_name[rname])
                    seen.add(rname)
            # Fill remaining slots if semantic search returned fewer than max_repos
            if len(ordered) < max_repos:
                for name, repo in sorted(repo_by_name.items()):
                    if name not in seen:
                        ordered.append(repo)
                        seen.add(name)
                        if len(ordered) >= max_repos:
                            break
            return ordered[:max_repos]
        except Exception as exc:  # noqa: BLE001
            logger.warning("narrow_candidates: semantic search failed (%s) — using fallback", exc)

    # Alphabetical fallback
    sorted_repos = sorted(
        repo_by_name.values(), key=lambda r: str(r.get("repo_name") or r.get("name") or "")
    )
    return sorted_repos[:max_repos]


# ---------------------------------------------------------------------------
# Per-repo action generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a GitHub portfolio analyst. Given a repository summary and a campaign goal,
decide whether this repo qualifies for the campaign and, if so, recommend a single
concrete action.

Return ONLY valid JSON with these keys:
  qualifies      — boolean
  action_type    — one of: archive, unarchive, add_license, add_topics,
                   update_description, apply_readme, add_codeowners,
                   enable_dependabot, pending_human_action
  target         — short string describing the specific change (e.g., a topic slug,
                   license SPDX ID, description text, or "archive")
  rationale      — 1-2 sentence explanation
  expected_impact — brief user-facing benefit, or null

If qualifies is false, the other fields may be empty strings.
"""


def _build_action_prompt(repo: dict, *, goal: str) -> str:
    repo_name = str(repo.get("repo_name") or repo.get("name") or "unknown")
    description = str(repo.get("description") or "")
    language = str(repo.get("primary_language") or repo.get("language") or "")
    topics = repo.get("topics") or []
    if isinstance(topics, list):
        topics_str = ", ".join(str(t) for t in topics) if topics else "none"
    else:
        topics_str = str(topics)
    has_readme = bool(repo.get("has_readme") or repo.get("readme_exists"))
    has_license = bool(repo.get("has_license") or repo.get("license"))
    stars = int(repo.get("stars") or repo.get("stargazers_count") or 0)
    archived = bool(repo.get("archived") or repo.get("is_archived"))

    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Campaign goal: {goal}\n\n"
        f"Repository: {repo_name}\n"
        f"Description: {description or '(none)'}\n"
        f"Language: {language or '(unknown)'}\n"
        f"Topics: {topics_str}\n"
        f"Has README: {has_readme}\n"
        f"Has license: {has_license}\n"
        f"Stars: {stars}\n"
        f"Archived: {archived}\n\n"
        "JSON response:"
    )


def generate_action_for_repo(
    repo: dict,
    *,
    goal: str,
    provider: "NarrativeProvider",
    model: str,
    cost_tracker: "CostTracker | None" = None,
) -> CampaignAction | None:
    """Call the LLM, parse the response. Return None if the repo doesn't qualify.

    The LLM must return JSON:
      {qualifies: bool, action_type: str, target: str, rationale: str,
       expected_impact: str | null}

    If ``action_type`` is not in ACTION_TYPES, forces it to
    ``"pending_human_action"`` (plan-doc constraint).

    Catches :class:`BudgetExceededError` and re-raises with ``repo_name``
    context added to the feature field.
    Robustly handles non-JSON or malformed responses by returning ``None``
    and logging a warning.
    """
    from src.llm_cost import BudgetExceededError

    repo_name = str(repo.get("repo_name") or repo.get("name") or "unknown")
    prompt = _build_action_prompt(repo, goal=goal)

    try:
        raw = provider.generate(
            prompt,
            model,
            _MAX_ACTION_TOKENS,
            cost_tracker=cost_tracker,
            feature=f"plan-campaign:{repo_name}",
        )
    except BudgetExceededError as exc:
        raise BudgetExceededError(
            budget_usd=exc.budget_usd,
            current_usd=exc.current_usd,
            call_cost_usd=exc.call_cost_usd,
            feature=f"plan-campaign:{repo_name}",
        ) from exc
    except TypeError:
        # Provider doesn't accept cost_tracker/feature kwargs (e.g. Protocol stub in tests)
        try:
            raw = provider.generate(prompt, model, _MAX_ACTION_TOKENS)
        except BudgetExceededError as exc:
            raise BudgetExceededError(
                budget_usd=exc.budget_usd,
                current_usd=exc.current_usd,
                call_cost_usd=exc.call_cost_usd,
                feature=f"plan-campaign:{repo_name}",
            ) from exc

    # Parse JSON — be robust against fenced code blocks or extra text
    parsed: dict | None = None
    try:
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        # Find the first { ... } block
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("plan_campaign: malformed JSON from provider for %s: %s", repo_name, exc)
        return None

    if parsed is None:
        logger.warning("plan_campaign: no JSON found in provider response for %s", repo_name)
        return None

    if not parsed.get("qualifies"):
        return None

    raw_action_type = str(parsed.get("action_type") or "pending_human_action")
    action_type = raw_action_type if raw_action_type in ACTION_TYPES else "pending_human_action"
    if action_type != raw_action_type:
        logger.warning(
            "plan_campaign: unknown action_type %r for %s — forcing pending_human_action",
            raw_action_type,
            repo_name,
        )

    return CampaignAction(
        repo_name=repo_name,
        action_type=action_type,
        target=str(parsed.get("target") or ""),
        rationale=str(parsed.get("rationale") or ""),
        expected_impact=parsed.get("expected_impact") or None,
    )


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------


def generate_plan(
    candidates: list[dict],
    *,
    goal: str,
    provider: "NarrativeProvider",
    model: str,
    cost_tracker: "CostTracker | None" = None,
    prefs: dict | None = None,
) -> CampaignPlanPacket:
    """Walk *candidates*, build actions, return a :class:`CampaignPlanPacket`.

    Respects operator prefs via :func:`is_suppressed` for action_type
    ``"campaign-plan"`` with the repo name as ``target_context``.
    """
    from src.operator_prefs import is_suppressed

    actions: list[CampaignAction] = []
    candidate_count = len(candidates)

    spend_before = cost_tracker.total_usd() if cost_tracker is not None else 0.0

    for repo in candidates:
        repo_name = str(repo.get("repo_name") or repo.get("name") or "")
        if prefs and is_suppressed(prefs, "campaign-plan", repo_name):
            logger.debug("plan_campaign: skipping %s (suppressed by prefs)", repo_name)
            continue

        action = generate_action_for_repo(
            repo,
            goal=goal,
            provider=provider,
            model=model,
            cost_tracker=cost_tracker,
        )
        if action is not None:
            actions.append(action)

    spend_after = cost_tracker.total_usd() if cost_tracker is not None else 0.0
    total_cost = round(spend_after - spend_before, 8)

    # Detect provider/model from tracker telemetry if possible
    llm_provider_name = "unknown"
    llm_model_name = model
    if cost_tracker is not None:
        records = cost_tracker.records()
        campaign_records = [r for r in records if "plan-campaign" in getattr(r, "feature", "")]
        if campaign_records:
            last = campaign_records[-1]
            llm_provider_name = getattr(last, "provider", "unknown")
            llm_model_name = getattr(last, "model", model)

    return CampaignPlanPacket(
        goal=goal,
        actions=actions,
        candidate_count=candidate_count,
        qualified_count=len(actions),
        llm_provider=llm_provider_name,
        llm_model=llm_model_name,
        llm_cost_usd=total_cost,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Ledger persistence
# ---------------------------------------------------------------------------


def _packet_record_id(packet: CampaignPlanPacket) -> str:
    """Stable record ID for a campaign-plan packet (goal + timestamp)."""
    material = f"campaign-plan:{packet.goal}:{packet.generated_at}"
    return "cp-" + hashlib.sha256(material.encode()).hexdigest()[:16]


def _goal_subject_key(goal: str) -> str:
    """Short hash of goal used as subject_key (plan-doc §Schema)."""
    return hashlib.sha256(goal.encode()).hexdigest()[:16]


def write_packet_to_ledger(
    packet: CampaignPlanPacket,
    *,
    output_dir: Path,
    reviewer: str,
) -> str:
    """Persist packet as an approval record with ``approval_subject_type='campaign-plan'``.

    Schema mapping (mirrors draft_readmes pattern):
      - approval_subject_type → "campaign-plan"
      - subject_key           → sha256(goal)[:16]
      - details_json          → full packet dict (actions serialised as dicts)
      - approval_note         → "{qualified_count} actions for goal"

    Returns the ``record_id`` string.
    """
    from src.warehouse import save_approval_record

    record_id = _packet_record_id(packet)
    subject_key = _goal_subject_key(packet.goal)

    # Serialise actions to plain dicts for JSON
    actions_dicts = [
        {
            "repo_name": a.repo_name,
            "action_type": a.action_type,
            "target": a.target,
            "rationale": a.rationale,
            "expected_impact": a.expected_impact,
        }
        for a in packet.actions
    ]

    details: dict = {
        "approval_id": record_id,
        "fingerprint": subject_key,
        "approval_subject_type": "campaign-plan",
        "subject_key": subject_key,
        "source_run_id": "",
        "approved_at": packet.generated_at,
        "approved_by": reviewer,
        "approval_note": f"{packet.qualified_count} actions for goal: {packet.goal[:80]}",
        # campaign-plan specific fields
        "action_type": "campaign-plan",
        "target_context": packet.goal,
        # full packet fields
        "goal": packet.goal,
        "candidate_count": packet.candidate_count,
        "qualified_count": packet.qualified_count,
        "llm_provider": packet.llm_provider,
        "llm_model": packet.llm_model,
        "llm_cost_usd": packet.llm_cost_usd,
        "generated_at": packet.generated_at,
        "actions": actions_dicts,
    }

    save_approval_record(output_dir, details)
    return record_id


# ---------------------------------------------------------------------------
# Apply path — load, dispatch, state transitions
# ---------------------------------------------------------------------------

_STALE_DAYS = 30


def load_approved_campaign_plans(warehouse_path: Path) -> list[CampaignPlanPacket]:
    """Read approval records where approval_subject_type='campaign-plan' AND status='approved-manual'.

    Hydrates the CampaignPlanPacket dataclass from the stored fields.
    Skips records older than 30 days.
    """
    from src.warehouse import load_approval_records

    all_records = load_approval_records(warehouse_path, "", limit=500)
    cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    packets: list[CampaignPlanPacket] = []

    for record in all_records:
        if record.get("approval_subject_type") != "campaign-plan":
            continue
        if record.get("status") != "approved-manual":
            continue

        ts_str = str(record.get("approved_at") or record.get("generated_at") or "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = (cutoff - ts).days
                if age_days > _STALE_DAYS:
                    logger.debug(
                        "load_approved_campaign_plans: skipping stale packet (age=%d days, goal=%.40s)",
                        age_days,
                        record.get("goal", ""),
                    )
                    continue
            except ValueError:
                pass  # Unparseable timestamp — keep the record

        raw_actions = record.get("actions") or []
        try:
            actions = [
                CampaignAction(
                    repo_name=str(a.get("repo_name") or ""),
                    action_type=str(a.get("action_type") or "pending_human_action"),
                    target=str(a.get("target") or ""),
                    rationale=str(a.get("rationale") or ""),
                    expected_impact=a.get("expected_impact") or None,
                    # 7B.1: hydrate per-action state; default "pending" for pre-7B packets
                    state=str(a.get("state") or "pending"),
                    rejected_reason=a.get("rejected_reason") or None,
                    decided_at=a.get("decided_at") or None,
                )
                for a in raw_actions
                if isinstance(a, dict)
            ]
        except (TypeError, ValueError) as exc:
            logger.warning(
                "load_approved_campaign_plans: could not hydrate actions for goal=%.40s: %s",
                record.get("goal", ""),
                exc,
            )
            continue

        try:
            packet = CampaignPlanPacket(
                goal=str(record.get("goal") or ""),
                actions=actions,
                candidate_count=int(record.get("candidate_count") or 0),
                qualified_count=int(record.get("qualified_count") or 0),
                llm_provider=str(record.get("llm_provider") or ""),
                llm_model=str(record.get("llm_model") or ""),
                llm_cost_usd=float(record.get("llm_cost_usd") or 0.0),
                generated_at=str(record.get("generated_at") or record.get("approved_at") or ""),
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "load_approved_campaign_plans: could not hydrate packet for goal=%.40s: %s",
                record.get("goal", ""),
                exc,
            )
            continue

        if not packet.goal:
            logger.debug("load_approved_campaign_plans: skipping packet with empty goal")
            continue

        packets.append(packet)

    return packets


def mark_campaign_applied(packet: CampaignPlanPacket, output_dir: Path) -> None:
    """Update the ledger record state from 'approved-manual' to 'applied'."""
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)
    record_id = _packet_record_id(packet)

    matching = [
        r
        for r in records
        if r.get("approval_id") == record_id
        and r.get("approval_subject_type") == "campaign-plan"
        and r.get("status") == "approved-manual"
    ]

    if not matching:
        logger.warning(
            "mark_campaign_applied: no approved-manual record found for id=%s — skipping",
            record_id,
        )
        return

    for record in matching:
        updated = dict(record)
        updated["status"] = "applied"
        updated["applied_at"] = datetime.now(timezone.utc).isoformat()
        save_approval_record(output_dir, updated)


# ---------------------------------------------------------------------------
# 7B.2 — Per-action approve / reject
# ---------------------------------------------------------------------------


def approve_action(packet_id: str, action_idx: int, output_dir: Path) -> None:
    """Set state='approved', decided_at=now on actions[action_idx] of packet packet_id.

    Raises ValueError if the packet is not found.
    Raises IndexError if action_idx is out of range.
    """
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)
    matching = [
        r
        for r in records
        if r.get("approval_id") == packet_id and r.get("approval_subject_type") == "campaign-plan"
    ]

    if not matching:
        raise ValueError(f"approve_action: no campaign-plan record found for id={packet_id!r}")

    for record in matching:
        actions: list[dict] = list(record.get("actions") or [])
        if action_idx < 0 or action_idx >= len(actions):
            raise IndexError(
                f"approve_action: action_idx={action_idx} out of range "
                f"for packet {packet_id!r} (len={len(actions)})"
            )
        updated_actions = [dict(a) for a in actions]
        updated_actions[action_idx]["state"] = "approved"
        updated_actions[action_idx]["decided_at"] = datetime.now(timezone.utc).isoformat()
        # Clear any prior rejection reason
        updated_actions[action_idx]["rejected_reason"] = None

        updated = dict(record)
        updated["actions"] = updated_actions
        save_approval_record(output_dir, updated)


def reject_action(packet_id: str, action_idx: int, output_dir: Path, reason: str = "") -> None:
    """Set state='rejected', rejected_reason=reason, decided_at=now on actions[action_idx].

    Raises ValueError if the packet is not found.
    Raises IndexError if action_idx is out of range.
    """
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)
    matching = [
        r
        for r in records
        if r.get("approval_id") == packet_id and r.get("approval_subject_type") == "campaign-plan"
    ]

    if not matching:
        raise ValueError(f"reject_action: no campaign-plan record found for id={packet_id!r}")

    for record in matching:
        actions: list[dict] = list(record.get("actions") or [])
        if action_idx < 0 or action_idx >= len(actions):
            raise IndexError(
                f"reject_action: action_idx={action_idx} out of range "
                f"for packet {packet_id!r} (len={len(actions)})"
            )
        updated_actions = [dict(a) for a in actions]
        updated_actions[action_idx]["state"] = "rejected"
        updated_actions[action_idx]["rejected_reason"] = reason or None
        updated_actions[action_idx]["decided_at"] = datetime.now(timezone.utc).isoformat()

        updated = dict(record)
        updated["actions"] = updated_actions
        save_approval_record(output_dir, updated)


def record_campaign_apply_failure(
    packet: CampaignPlanPacket,
    error: str,
    output_dir: Path,
) -> None:
    """Append a failure event so the operator can retry.

    The record stays 'approved-manual' to allow retries.
    """
    import uuid

    from src.warehouse import save_approval_followup_event

    record_id = _packet_record_id(packet)
    event = {
        "event_id": "cf-" + str(uuid.uuid4())[:16],
        "approval_id": record_id,
        "fingerprint": _goal_subject_key(packet.goal),
        "approval_subject_type": "campaign-plan",
        "subject_key": _goal_subject_key(packet.goal),
        "source_run_id": "",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": "system",
        "review_note": f"apply-failure: {error}",
        "cadence_days": 0,
        "event_type": "apply-failure",
        "error": error,
    }
    save_approval_followup_event(output_dir, event)


def dispatch_action(
    action: CampaignAction,
    *,
    client: object,
    owner: str,
    dry_run: bool,
) -> tuple[bool, str]:
    """Route a CampaignAction to its executor handler.

    Returns (success, message).

    Mapping:
      archive, unarchive, update_description → apply_metadata_updates (archived/description)
      add_topics                              → apply_metadata_updates (topics)
      apply_readme                            → apply_readme_updates
      add_license, add_codeowners,
        enable_dependabot                     → (False, "handler not yet implemented")
      pending_human_action                    → (False, "manual review required")
    """
    from src.repo_improver import apply_metadata_updates, apply_readme_updates

    action_type = action.action_type

    if action_type == "pending_human_action":
        return False, "manual review required"

    if action_type in ("add_license", "add_codeowners", "enable_dependabot"):
        return False, "handler not yet implemented"

    if dry_run:
        return (
            True,
            f"[dry-run] would execute: {action_type} {action.repo_name} (target={action.target!r})",
        )

    if action_type in ("archive", "unarchive", "update_description"):
        # Build a metadata update dict understood by apply_metadata_updates
        update: dict = {"name": action.repo_name}
        if action_type == "archive":
            update["archived"] = True
        elif action_type == "unarchive":
            update["archived"] = False
        elif action_type == "update_description":
            update["description"] = action.target

        results = apply_metadata_updates(client, owner, [update], dry_run=False)  # type: ignore[arg-type]
        if results:
            r = results[0]
            actions_ok = [a for a in r.get("actions", []) if a.get("ok") or a.get("dry_run")]
            if actions_ok:
                return True, f"{action_type} applied to {action.repo_name}"
            # No actions dispatched — likely unsupported field (e.g. archive via REST)
            errors = [str(a.get("error", "")) for a in r.get("actions", []) if a.get("error")]
            err_msg = "; ".join(errors) if errors else "no actions executed"
            return False, f"{action_type} failed for {action.repo_name}: {err_msg}"
        return (
            False,
            f"{action_type}: apply_metadata_updates returned no results for {action.repo_name}",
        )

    if action_type == "add_topics":
        raw_topics = action.target
        topics = [t.strip() for t in raw_topics.replace(",", " ").split() if t.strip()]
        update_t: dict = {"name": action.repo_name, "topics": topics}
        results = apply_metadata_updates(client, owner, [update_t], dry_run=False)  # type: ignore[arg-type]
        if results:
            r = results[0]
            actions_ok = [a for a in r.get("actions", []) if a.get("ok") or a.get("dry_run")]
            if actions_ok:
                return True, f"add_topics applied to {action.repo_name}: {topics}"
            errors = [str(a.get("error", "")) for a in r.get("actions", []) if a.get("error")]
            err_msg = "; ".join(errors) if errors else "no actions executed"
            return False, f"add_topics failed for {action.repo_name}: {err_msg}"
        return (
            False,
            f"add_topics: apply_metadata_updates returned no results for {action.repo_name}",
        )

    if action_type == "apply_readme":
        readme_content = action.target
        update_r: dict = {"name": action.repo_name, "readme": readme_content}
        results = apply_readme_updates(client, owner, [update_r], dry_run=False)  # type: ignore[arg-type]
        if results:
            r = results[0]
            if r.get("ok") or r.get("dry_run"):
                return True, f"apply_readme pushed to {action.repo_name}"
            error = str(r.get("error") or "unknown error")
            return False, f"apply_readme failed for {action.repo_name}: {error}"
        return (
            False,
            f"apply_readme: apply_readme_updates returned no results for {action.repo_name}",
        )

    return False, f"unrecognised action_type: {action_type!r}"
