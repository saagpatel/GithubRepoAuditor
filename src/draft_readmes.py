"""Agentic README authoring — composes semantic index + LLM provider into draft packets.

Arc G Sprint 5.1 — core module.  Pure functions where possible so they're easy
to unit-test without spinning up a real LLM.
"""

from __future__ import annotations

import hashlib
import logging
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
