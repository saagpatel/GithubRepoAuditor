"""Agentic README authoring — composes semantic index + LLM provider into draft packets.

Arc G Sprint 5.1 — core module.  Pure functions where possible so they're easy
to unit-test without spinning up a real LLM.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm_cost import CostTracker
    from src.narrative import NarrativeProvider
    from src.semantic_index import SemanticIndex

logger = logging.getLogger(__name__)

# Threshold: README shorter than this (after stripping badges/headings) is "trivially short".
README_SHORT_THRESHOLD = 200

# Number of semantic neighbours to include in context.
CONTEXT_NEIGHBORS_K = 3

# Max tokens we'll ask the LLM to produce for a draft README.
MAX_README_TOKENS = 2048


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class DraftReadmePacket:
    repo_name: str
    current_readme_sha: str | None
    proposed_readme: str
    diff_summary: str
    llm_provider: str
    llm_model: str
    llm_cost_usd: float
    generated_at: str
    context_repos: list[str] = field(default_factory=list)


# ── Qualification ─────────────────────────────────────────────────────────────


def _readme_is_trivially_short(repo: dict) -> bool:
    """Return True when the README exists but has < README_SHORT_THRESHOLD non-decoration chars."""
    readme_text: str = str(repo.get("readme_text") or repo.get("readme_content") or "")
    if not readme_text:
        return False
    # Strip markdown badges (![...](...)  or  [![...](...)...)) and heading lines
    import re

    stripped = re.sub(r"!\[.*?\]\(.*?\)", "", readme_text)
    stripped = re.sub(r"^#{1,6}\s.*$", "", stripped, flags=re.MULTILINE)
    stripped = stripped.strip()
    return len(stripped) < README_SHORT_THRESHOLD


def _readme_is_missing(repo: dict) -> bool:
    """Return True when no README is present."""
    # Audit results store None or empty string when README is absent.
    has_readme: object = repo.get("has_readme", None)
    if has_readme is False:
        return True
    readme_text: str = str(repo.get("readme_text") or repo.get("readme_content") or "")
    if not readme_text and has_readme is None:
        # Fallback: check the readme dimension fields
        readme_score = repo.get("readme_score", None)
        if readme_score is not None and float(readme_score) == 0.0:
            return True
    return False


def qualify_repos(
    audit_results: list[dict],
    *,
    opt_in_repos: list[str] | None,
    all_qualifying: bool,
) -> list[str]:
    """Return repo names eligible for draft authoring.

    Rules:
      - If opt_in_repos non-empty: return exactly those (no other filtering).
      - If all_qualifying: return repos where readme_stale=True OR readme missing
        OR readme trivially short (< 200 chars after stripping badges/headings).
      - Else: return [] (no-op).
    """
    if opt_in_repos:
        return list(opt_in_repos)

    if not all_qualifying:
        return []

    qualified: list[str] = []
    for repo in audit_results:
        name: str = str(repo.get("repo_name") or repo.get("name") or "")
        if not name:
            continue
        if repo.get("readme_stale") is True:
            qualified.append(name)
        elif _readme_is_missing(repo):
            qualified.append(name)
        elif _readme_is_trivially_short(repo):
            qualified.append(name)

    return qualified


# ── Context building ──────────────────────────────────────────────────────────


def build_context(
    repo: dict,
    *,
    semantic_index: SemanticIndex | None,
) -> dict:
    """Bundle metadata, file tree (top 2 levels), neighbours, current readme, recent commits.

    Returns a dict with keys:
      - repo_name, description, language, topics, stars, license, latest_release,
        file_tree, current_readme, current_readme_sha, recent_commits,
        context_repos (list of {repo_name, snippet} dicts), readme_stale
    """
    repo_name: str = str(repo.get("repo_name") or repo.get("name") or "")

    # Metadata
    description: str = str(repo.get("description") or "")
    language: str = str(repo.get("language") or "")
    topics: list[str] = list(repo.get("topics") or [])
    stars: int = int(repo.get("stars") or repo.get("stargazers_count") or 0)
    license_name: str = str(repo.get("license") or "")
    latest_release: str = str(repo.get("latest_release") or "")

    # File tree (stored in structure analyzer details or top_level_dirs field)
    file_tree: list[str] = list(repo.get("top_level_dirs") or repo.get("file_tree") or [])

    # README content
    current_readme: str = str(repo.get("readme_text") or repo.get("readme_content") or "")
    current_readme_sha: str | None = repo.get("readme_sha") or None

    # Recent commits (list of strings or dicts with "message" key)
    raw_commits: object = repo.get("recent_commits") or []
    recent_commits: list[str] = []
    for c in raw_commits:  # type: ignore[union-attr]
        if isinstance(c, str):
            recent_commits.append(c)
        elif isinstance(c, dict):
            msg = str(c.get("message") or c.get("subject") or "")
            if msg:
                recent_commits.append(msg.splitlines()[0])
    recent_commits = recent_commits[:10]

    # Semantic neighbours
    context_repos: list[dict[str, str]] = []
    if semantic_index is not None and repo_name:
        try:
            neighbors = semantic_index.find_neighbors(repo_name, CONTEXT_NEIGHBORS_K)
            for n in neighbors:
                context_repos.append({"repo_name": n.repo_name, "snippet": n.snippet})
        except Exception as exc:  # noqa: BLE001
            logger.debug("draft_readmes: find_neighbors failed for %s: %s", repo_name, exc)

    return {
        "repo_name": repo_name,
        "description": description,
        "language": language,
        "topics": topics,
        "stars": stars,
        "license": license_name,
        "latest_release": latest_release,
        "file_tree": file_tree,
        "current_readme": current_readme,
        "current_readme_sha": current_readme_sha,
        "recent_commits": recent_commits,
        "context_repos": context_repos,
        "readme_stale": repo.get("readme_stale"),
    }


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_readme_prompt(context: dict) -> str:
    """Compose the LLM prompt for README authoring from the context dict."""
    repo_name = context["repo_name"]
    description = context["description"] or "(no description)"
    language = context["language"] or "unknown"
    topics = ", ".join(context["topics"]) if context["topics"] else "none"
    stars = context["stars"]
    license_name = context["license"] or "unknown"
    file_tree = "\n".join(f"  {f}" for f in context["file_tree"][:30]) or "  (unavailable)"
    current_readme = context["current_readme"]
    recent_commits = "\n".join(f"  - {c}" for c in context["recent_commits"]) or "  (unavailable)"

    neighbors_block = ""
    for nb in context["context_repos"]:
        neighbors_block += f"\n### {nb['repo_name']}\n{nb['snippet']}\n"

    if_existing = ""
    if current_readme:
        trimmed = current_readme[:3000]
        if_existing = f"""
## Current README (improve this — don't wholesale replace unless it's trivially short)

```
{trimmed}
```
"""

    neighbor_section = ""
    if neighbors_block:
        neighbor_section = f"""
## Similar repos in this portfolio (use as style reference)
{neighbors_block}
"""

    return f"""You are a developer writing a README for a GitHub repository.

## Repository: {repo_name}
- Description: {description}
- Language: {language}
- Topics: {topics}
- Stars: {stars}
- License: {license_name}

## Top-level file tree
{file_tree}

## Recent commits (last 10)
{recent_commits}
{if_existing}{neighbor_section}
## Task
Write a complete, professional README.md for this repository. Include:
1. Project title and short description
2. Key features / what it does
3. Installation and usage instructions (infer from file tree and language)
4. Any requirements or prerequisites
5. License

Keep the tone technical but concise. Use Markdown headers, code blocks where appropriate.
Do NOT include placeholder text like "[your name here]". Make reasonable assumptions from the context above.
Output ONLY the raw Markdown content — no preamble, no "Here is the README:" prefix.
""".strip()


# ── Draft generation ──────────────────────────────────────────────────────────


def generate_draft(
    repo: dict,
    *,
    context: dict,
    provider: NarrativeProvider,
    model: str,
    cost_tracker: CostTracker | None = None,
) -> DraftReadmePacket:
    """Call the provider, build the packet.

    Catches BudgetExceededError and re-raises with repo context added to the message.
    """
    from src.llm_cost import BudgetExceededError

    repo_name: str = context["repo_name"]
    prompt = _build_readme_prompt(context)

    spend_before: float = 0.0
    if cost_tracker is not None:
        spend_before = cost_tracker.total_usd()

    try:
        proposed_readme = provider.generate(
            prompt,
            model,
            MAX_README_TOKENS,
            cost_tracker=cost_tracker,
            feature="draft-readme",
        )
    except BudgetExceededError as exc:
        raise BudgetExceededError(
            budget_usd=exc.budget_usd,
            current_usd=exc.current_usd,
            call_cost_usd=exc.call_cost_usd,
            feature=f"draft-readme:{repo_name}",
        ) from exc
    except TypeError:
        # Provider doesn't accept cost_tracker/feature kwargs (e.g. Protocol stub)
        proposed_readme = provider.generate(prompt, model, MAX_README_TOKENS)

    spend_after: float = spend_before
    if cost_tracker is not None:
        spend_after = cost_tracker.total_usd()
    call_cost = round(spend_after - spend_before, 8)

    # Simple diff summary
    current_readme = context.get("current_readme") or ""
    if not current_readme:
        diff_summary = "Created new README from scratch."
    else:
        diff_summary = _summarise_diff(current_readme, proposed_readme)

    provider_name = type(provider).__name__.replace("Provider", "").lower()

    return DraftReadmePacket(
        repo_name=repo_name,
        current_readme_sha=context.get("current_readme_sha"),
        proposed_readme=proposed_readme,
        diff_summary=diff_summary,
        llm_provider=provider_name,
        llm_model=model,
        llm_cost_usd=call_cost,
        generated_at=datetime.now(timezone.utc).isoformat(),
        context_repos=[nb["repo_name"] for nb in context.get("context_repos", [])],
    )


def _summarise_diff(before: str, after: str) -> str:
    """Produce a short human-readable diff summary."""
    before_lines = set(before.splitlines())
    after_lines = set(after.splitlines())
    added = len(after_lines - before_lines)
    removed = len(before_lines - after_lines)
    return f"+{added} lines added, -{removed} lines removed vs current README."


# ── Ledger persistence ────────────────────────────────────────────────────────


def write_packets_to_ledger(
    packets: list[DraftReadmePacket],
    ledger_path: Path,
    reviewer: str,
) -> None:
    """Persist packets as action_type='draft-readme' records via the approval-ledger schema.

    Schema adaptation note: the warehouse `approval_records` table uses
    `approval_subject_type` and `subject_key` as its primary classifiers.
    We map:
      - approval_subject_type  → "draft-readme"  (action_type alias)
      - subject_key            → packet.repo_name (target_context alias)

    The full DraftReadmePacket fields (including `action_type` and `target_context`)
    are stored verbatim in `details_json` so the operator_prefs suppression logic —
    which reads those fields from the raw dict — works correctly.

    `ledger_path` is the OUTPUT DIRECTORY (not a file path) because
    `save_approval_record` from warehouse.py expects the directory.
    """
    from src.warehouse import save_approval_record

    output_dir = Path(ledger_path)

    for packet in packets:
        packet_dict = {
            # warehouse schema fields
            "approval_id": _packet_id(packet),
            "fingerprint": _packet_fingerprint(packet),
            "approval_subject_type": "draft-readme",
            "subject_key": packet.repo_name,
            "source_run_id": "",
            "approved_at": packet.generated_at,
            "approved_by": reviewer,
            "approval_note": packet.diff_summary,
            # operator_prefs suppression fields (detect_suppressions reads these)
            "action_type": "draft-readme",
            "target_context": packet.repo_name,
            "decision": "",  # blank = pending review, not yet decided
            "timestamp": packet.generated_at,
            "status": "ready-for-review",
            # full packet payload
            "repo_name": packet.repo_name,
            "current_readme_sha": packet.current_readme_sha,
            "proposed_readme": packet.proposed_readme,
            "diff_summary": packet.diff_summary,
            "llm_provider": packet.llm_provider,
            "llm_model": packet.llm_model,
            "llm_cost_usd": packet.llm_cost_usd,
            "generated_at": packet.generated_at,
            "context_repos": packet.context_repos,
        }
        save_approval_record(output_dir, packet_dict)


def _packet_id(packet: DraftReadmePacket) -> str:
    """Stable per-repo packet ID (deterministic: same repo → same id within a run)."""
    material = f"draft-readme:{packet.repo_name}:{packet.generated_at}"
    return "dr-" + hashlib.sha1(material.encode()).hexdigest()[:16]


def _packet_fingerprint(packet: DraftReadmePacket) -> str:
    """Content fingerprint for deduplication."""
    material = f"{packet.repo_name}:{packet.proposed_readme[:500]}"
    return hashlib.sha1(material.encode()).hexdigest()[:16]


# ── Ledger readback ───────────────────────────────────────────────────────────

_STALE_DAYS = 30


def load_approved_drafts(
    warehouse_path: Path,
    username: str | None = None,
) -> list[DraftReadmePacket]:
    """Read approval records where approval_subject_type='draft-readme' AND status='approved-manual'.

    Hydrates each record's details_json back into a DraftReadmePacket.
    Skips records older than 30 days (likely stale).
    """
    from src.warehouse import load_approval_records

    all_records = load_approval_records(warehouse_path, username or "", limit=500)

    cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    packets: list[DraftReadmePacket] = []

    for record in all_records:
        if record.get("approval_subject_type") != "draft-readme":
            continue
        if record.get("status") != "approved-manual":
            continue

        # Staleness check — approved_at or generated_at
        ts_str: str = str(record.get("approved_at") or record.get("generated_at") or "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = (cutoff - ts).days
                if age_days > _STALE_DAYS:
                    logger.debug(
                        "load_approved_drafts: skipping stale packet for %s (age=%d days)",
                        record.get("subject_key"),
                        age_days,
                    )
                    continue
            except ValueError:
                pass  # Unparseable timestamp — keep the record

        try:
            packet = DraftReadmePacket(
                repo_name=str(record.get("repo_name") or record.get("subject_key") or ""),
                current_readme_sha=record.get("current_readme_sha") or None,
                proposed_readme=str(record.get("proposed_readme") or ""),
                diff_summary=str(record.get("diff_summary") or record.get("approval_note") or ""),
                llm_provider=str(record.get("llm_provider") or ""),
                llm_model=str(record.get("llm_model") or ""),
                llm_cost_usd=float(record.get("llm_cost_usd") or 0.0),
                generated_at=str(record.get("generated_at") or record.get("approved_at") or ""),
                context_repos=list(record.get("context_repos") or []),
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "load_approved_drafts: could not hydrate packet for %s: %s",
                record.get("subject_key"),
                exc,
            )
            continue

        if not packet.repo_name or not packet.proposed_readme:
            logger.debug(
                "load_approved_drafts: skipping incomplete packet for subject_key=%s",
                record.get("subject_key"),
            )
            continue

        packets.append(packet)

    return packets


def mark_draft_applied(
    output_dir: Path,
    packet: DraftReadmePacket,
    *,
    apply_result: dict,
) -> None:
    """Update the ledger record for *packet* to status='applied'.

    Re-saves the existing record with status mutated to 'applied' and an
    apply_result embedded so the operator can see what happened.
    Uses INSERT OR REPLACE semantics — safe to call multiple times.
    On failure (missing warehouse), logs a warning rather than raising.
    """
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)

    # Find the matching record by subject_key + approval_subject_type
    matching = [
        r
        for r in records
        if r.get("approval_subject_type") == "draft-readme"
        and r.get("subject_key") == packet.repo_name
        and r.get("status") == "approved-manual"
    ]

    if not matching:
        logger.warning(
            "mark_draft_applied: no approved-manual record found for %s — skipping state update",
            packet.repo_name,
        )
        return

    for record in matching:
        updated = dict(record)
        updated["status"] = "applied"
        updated["apply_result"] = apply_result
        updated["applied_at"] = datetime.now(timezone.utc).isoformat()
        save_approval_record(output_dir, updated)


def record_draft_apply_failure(
    output_dir: Path,
    packet: DraftReadmePacket,
    *,
    error: str,
) -> None:
    """Append a failure event to the ledger without changing the record state.

    The record stays 'approved-manual' so the operator can retry.
    Writes a new approval_followup_event with event_type='apply-failure'.
    """
    import uuid

    from src.warehouse import save_approval_followup_event

    event = {
        "event_id": "af-" + str(uuid.uuid4())[:16],
        "approval_id": "dr-"
        + hashlib.sha1(
            f"draft-readme:{packet.repo_name}:{packet.generated_at}".encode()
        ).hexdigest()[:16],
        "fingerprint": _packet_fingerprint(packet),
        "approval_subject_type": "draft-readme",
        "subject_key": packet.repo_name,
        "source_run_id": "",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": "system",
        "review_note": f"apply-failure: {error}",
        "cadence_days": 0,
        "event_type": "apply-failure",
        "error": error,
    }
    save_approval_followup_event(output_dir, event)


# ── Per-section approval (Arc G Sprint 8.5) ──────────────────────────────────


def split_readme_sections(text: str) -> list[tuple[str, str]]:
    """Split *text* at top-level ``## `` headings into (heading, body) tuples.

    Rules:
    - Content before the first ``## `` heading is paired with heading ``"(intro)"``.
    - Only top-level ``## `` lines (not ``### `` or deeper) split the document.
    - ``## `` lines inside fenced code blocks (```…```) are ignored.
    - Empty input → ``[]``.
    - No ``## `` headings → ``[("(intro)", text)]``.

    Each returned body includes everything up to (but not including) the next
    top-level heading, preserving nested headings (``###``, etc.) verbatim.
    """
    if not text:
        return []

    sections: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    in_fence: bool = False

    for line in text.splitlines(keepends=True):
        # Track code-fence state (``` only — indented fences not handled)
        stripped = line.rstrip("\n\r")
        if re.match(r"^```", stripped):
            in_fence = not in_fence

        if not in_fence and re.match(r"^## ", line):
            # Flush the previous section
            if current_heading is not None or current_lines:
                heading = current_heading if current_heading is not None else "(intro)"
                sections.append((heading, "".join(current_lines)))
            current_heading = stripped[3:]  # strip leading "## "
            current_lines = []
        else:
            current_lines.append(line)

    # Flush the last section
    if current_heading is not None or current_lines:
        heading = current_heading if current_heading is not None else "(intro)"
        body = "".join(current_lines)
        sections.append((heading, body))

    return sections


def _section_approval_id(repo_name: str, heading: str, section_idx: int) -> str:
    """Stable approval_id for a (repo, heading) pair."""
    digest = hashlib.sha256(f"{repo_name}:{heading}".encode()).hexdigest()[:12]
    return f"drs-{section_idx:02d}-{digest}"


def _section_subject_key(repo_name: str, heading: str) -> str:
    """Stable subject_key for a (repo, heading) pair (16 hex chars)."""
    return hashlib.sha256(f"{repo_name}:{heading}".encode()).hexdigest()[:16]


def _packet_id_for_repo(repo_name: str, generated_at: str) -> str:
    """Shared packet_id across all section sub-records for one repo+run."""
    material = f"drs-pkt:{repo_name}:{generated_at}"
    return "drs-pkt-" + hashlib.sha256(material.encode()).hexdigest()[:16]


def write_section_packets_to_ledger(
    packets: list[DraftReadmePacket],
    ledger_path: Path,
    reviewer: str,
) -> None:
    """Persist per-section sub-records for each packet.

    Each ``## `` heading in the proposed README becomes one
    ``approval_subject_type="draft-readme-section"`` record with its own
    ``approval_id`` and a shared ``packet_id`` across all sections of the
    same repo+run.

    Callers that want the old single-record behaviour should use
    ``write_packets_to_ledger`` instead.  Both can coexist.
    """
    from src.warehouse import save_approval_record

    output_dir = Path(ledger_path)

    for packet in packets:
        sections = split_readme_sections(packet.proposed_readme)
        if not sections:
            # Nothing to write — proposed README was empty
            continue

        shared_packet_id = _packet_id_for_repo(packet.repo_name, packet.generated_at)

        for section_idx, (heading, body) in enumerate(sections):
            approval_id = _section_approval_id(packet.repo_name, heading, section_idx)
            subject_key = _section_subject_key(packet.repo_name, heading)

            record: dict = {
                # warehouse schema fields
                "approval_id": approval_id,
                "fingerprint": hashlib.sha256(
                    f"{packet.repo_name}:{heading}:{body[:200]}".encode()
                ).hexdigest()[:16],
                "approval_subject_type": "draft-readme-section",
                "subject_key": subject_key,
                "source_run_id": "",
                "approved_at": packet.generated_at,
                "approved_by": reviewer,
                "approval_note": f"section {section_idx}: {heading}",
                "action_type": "draft-readme-section",
                "target_context": packet.repo_name,
                "decision": "",
                "timestamp": packet.generated_at,
                "status": "ready-for-review",
                # section payload
                "section_heading": heading,
                "section_body": body,
                "section_idx": section_idx,
                "packet_id": shared_packet_id,
                "state": "pending",
                "rejected_reason": None,
                "decided_at": None,
                # carry-through packet metadata for the diff view
                "repo_name": packet.repo_name,
                "current_readme_sha": packet.current_readme_sha,
                "diff_summary": packet.diff_summary,
                "llm_provider": packet.llm_provider,
                "llm_model": packet.llm_model,
                "llm_cost_usd": packet.llm_cost_usd,
                "generated_at": packet.generated_at,
            }
            save_approval_record(output_dir, record)


def approve_section(record_id: str, output_dir: Path) -> None:
    """Set ``state='approved'``, ``decided_at=now`` on the sub-record.

    Raises ``ValueError`` if the record is not found.
    """
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)
    matching = [
        r
        for r in records
        if r.get("approval_id") == record_id
        and r.get("approval_subject_type") == "draft-readme-section"
    ]
    if not matching:
        raise ValueError(
            f"approve_section: no draft-readme-section record found for id={record_id!r}"
        )
    for record in matching:
        updated = dict(record)
        updated["state"] = "approved"
        updated["decided_at"] = datetime.now(timezone.utc).isoformat()
        updated["rejected_reason"] = None
        save_approval_record(output_dir, updated)


def reject_section(record_id: str, output_dir: Path, reason: str = "") -> None:
    """Set ``state='rejected'``, persist *reason*, set ``decided_at=now``.

    Raises ``ValueError`` if the record is not found.
    """
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)
    matching = [
        r
        for r in records
        if r.get("approval_id") == record_id
        and r.get("approval_subject_type") == "draft-readme-section"
    ]
    if not matching:
        raise ValueError(
            f"reject_section: no draft-readme-section record found for id={record_id!r}"
        )
    for record in matching:
        updated = dict(record)
        updated["state"] = "rejected"
        updated["rejected_reason"] = reason or None
        updated["decided_at"] = datetime.now(timezone.utc).isoformat()
        save_approval_record(output_dir, updated)


def load_approved_sectioned_packets(
    warehouse_path: Path,
) -> dict[str, list[dict]]:
    """Return ``{packet_id: [section_dicts sorted by section_idx]}`` for ready packets.

    A packet is included only when **all** its sections are in a terminal state
    (``'approved'`` or ``'rejected'``).  Packets with any ``'pending'`` sections
    are omitted.

    At least one section must be ``'approved'`` for the packet to be usable;
    callers should check ``assemble_readme_from_approved_sections`` for ``None``
    when every section ended up rejected.
    """
    from src.warehouse import load_approval_records

    all_records = load_approval_records(warehouse_path, "", limit=500)

    # Group by packet_id
    by_packet: dict[str, list[dict]] = {}
    for record in all_records:
        if record.get("approval_subject_type") != "draft-readme-section":
            continue
        if record.get("status") in ("applied",):
            # Skip already-applied sections
            continue
        pid = record.get("packet_id") or ""
        if not pid:
            continue
        by_packet.setdefault(pid, []).append(record)

    # Keep only packets where every section is terminal
    result: dict[str, list[dict]] = {}
    terminal = {"approved", "rejected"}
    for pid, sections in by_packet.items():
        states = {s.get("state", "pending") for s in sections}
        if states <= terminal:
            result[pid] = sorted(sections, key=lambda s: int(s.get("section_idx") or 0))

    return result


def assemble_readme_from_approved_sections(sections: list[dict]) -> str | None:
    """Concatenate approved sections into a single README in ``section_idx`` order.

    Returns ``None`` if there are zero approved sections.
    Rejected sections are skipped.
    """
    parts: list[str] = []
    for section in sorted(sections, key=lambda s: int(s.get("section_idx") or 0)):
        if section.get("state") != "approved":
            continue
        heading = section.get("section_heading") or ""
        body = section.get("section_body") or ""
        if heading and heading != "(intro)":
            parts.append(f"## {heading}\n{body}")
        else:
            parts.append(body)
    if not parts:
        return None
    return "".join(parts)


def mark_section_packet_applied(packet_id: str, output_dir: Path) -> None:
    """Set ``status='applied'`` on every section sub-record sharing *packet_id*."""
    from src.warehouse import load_approval_records, save_approval_record

    records = load_approval_records(output_dir, "", limit=500)
    for record in records:
        if record.get("approval_subject_type") != "draft-readme-section":
            continue
        if record.get("packet_id") != packet_id:
            continue
        updated = dict(record)
        updated["status"] = "applied"
        updated["applied_at"] = datetime.now(timezone.utc).isoformat()
        save_approval_record(output_dir, updated)
