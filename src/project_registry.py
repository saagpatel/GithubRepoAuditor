"""Canonical cross-store project-identity registry.

Joins the four stores that key projects differently — this auditor
(``identity.project_key``), bridge-db (``project_name``), Notion's Local
Portfolio Projects (row title), and ``~/.claude`` memory (``project_*.md``
slug) — under one canonical key, so events stop going unmatched.

The auditor is the system of record for *what exists*, so its
``project_key`` is the canonical key, with ``repo_full_name`` as the stable
secondary natural key. A normalization function bridges the majority of
spelling differences; a small curated override table (see
``config/project-registry-overrides.json``) handles the cases where even
normalization diverges, plus supplementary entries for operator-OS projects
the auditor does not track (e.g. ``personal-ops``).

Every external source is optional: a missing bridge-db / Notion snapshot /
memory dir degrades to reduced coverage rather than failing the run.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
NOTION_PROJECTION_POLICY_SCHEMA_VERSION = "notion_projection_policy.v2"
IDENTITY_ALIAS_MAP_DEPRECATES_AFTER = "2026-09-30"

# Migration-only alias map for Operator-OS identity dialects found by the
# 2026-07-03 dialect census. Canonical values are repo_full_name, not
# project_key; do not grow this into a permanent second identity system.
IDENTITY_ALIAS_MAP: dict[str, str] = {
    "OPERANT": "saagpatel/operant",
    "CryptForge": "saagpatel/CryptForge",
    "Fun:GamePrjs/ CryptForge": "saagpatel/CryptForge",
    "Devil-s-Advocate": "saagpatel/devils-advocate",
    "devils-advocate": "saagpatel/devils-advocate",
    "GithubRepoAuditor": "saagpatel/GithubRepoAuditor",
    "github-repo-auditor": "saagpatel/GithubRepoAuditor",
    "MCPAudit": "saagpatel/MCPAudit",
    "mcpaudit-web": "saagpatel/MCPAudit",
    "Notion": "saagpatel/Notion",
    "notion_os": "saagpatel/Notion",
    "fable-outputs": "saagpatel/fable-outputs",
    "fable-second-sprint": "saagpatel/fable-second-sprint",
    "portfolio-mcp": "saagpatel/portfolio-mcp",
    "mcp-trust": "saagpatel/mcp-trust",
    "agent-bridge": "saagpatel/agent-bridge",
    "bridge-db": "saagpatel/bridge-db",
    "cost-tracker": "saagpatel/cost-tracker",
    "notification-hub": "saagpatel/notification-hub",
    "portfolio-code-health": "saagpatel/portfolio-code-health",
    "portfolio-index": "saagpatel/portfolio-index",
    "AIWorkFlow": "saagpatel/AIWorkFlow",
    "ApplyKit": "saagpatel/ApplyKit",
    "Signal & Noise": "saagpatel/SignalAndNoise",
    "Signal---Noise": "saagpatel/SignalAndNoise",
}

BRIDGE_CANONICAL_KEY_DISAGREEMENTS: dict[str, str] = {
    "operant-public": "Bridge canonical_key should reconcile to OPERANT/saagpatel/operant.",
    "portfolio-health": (
        "Bridge canonical_key should reconcile to "
        "portfolio-code-health/saagpatel/portfolio-code-health."
    ),
}

# Built-in fallbacks, mirrored by config/project-registry-overrides.json.
# Hard normalization failures: drifted identifier -> canonical project_key.
DEFAULT_OVERRIDES: dict[str, str] = {
    "jcc": "JobCommandCenter",
    "jsm_export": "JSMTicketAnalyticsExport",
    "bhv": "BrowserHistoryVisualizer",
    "netmapper": "NetworkMapper",
    "notion_os": "Notion",
    "screenshotselect": "ScreenshottoDataSelect",
    "interruptionresume": "Interruption Resume Studio",
}

# Real operator-OS projects absent from the auditor's repo registry.
DEFAULT_SUPPLEMENTARY: list[dict] = [
    {
        "canonical_key": "supp:personal-ops",
        "display_name": "personal-ops",
        "repo_full_name": None,
        "group_key": "operator_infra",
        "lifecycle_state": "active",
        "note": (
            "Local operator control plane (127.0.0.1:46210). Most active "
            "project in bridge-db yet absent from auditor portfolio-truth."
        ),
    },
    {
        "canonical_key": "supp:SecondBrain",
        "display_name": "SecondBrain",
        "repo_full_name": None,
        "group_key": "operator_infra",
        "lifecycle_state": "active",
        "note": (
            "4-layer knowledge vault at /Users/d/Documents/SecondBrain "
            "(engraph-indexed). Not a git repo; absent from auditor."
        ),
    },
]

# Memory slugs that are notes about a project, not their own project.
# slug -> parent canonical_key (empty string = pure meta, attach to nothing).
DEFAULT_MEMORY_META: dict[str, str] = {
    "personal_ops_codebase": "supp:personal-ops",
    "personal_ops_vision": "supp:personal-ops",
    "github_repo_auditor_future_arcs": "GithubRepoAuditor",
    "skill_library_port_2026-05": "",
    "skill_eval_harness_2026-05": "",
}

DEFAULT_NOTION_TITLE_ALIASES: dict[str, str] = {
    "DesktopPEt-ready": "DesktopPEt",
    "EarthPulse-readiness": "EarthPulse",
    "GithubRepoAuditor-public": "GithubRepoAuditor",
    "Notion Operating System": "Notion",
    "OrbitForge (staging)": "OrbitForge",
    "Personal Ops": "operator-os-docs",
    "PomGambler-prod": "PomGambler",
}

DEFAULT_NOTION_PROJECTION_ONLY_ROWS: dict[str, str] = {
    "app": "local runtime/app shell placeholder; not a portfolio-truth repo",
    "claude-code-harness": "local agent harness projection; outside repo-root truth",
    "Sandbox Local Portfolio Project": "actuation sandbox fixture row",
    "SecondBrain": "knowledge vault under /Users/d/Documents; not a /Users/d/Projects repo",
}

DEFAULT_NOTION_TRUTH_SHADOW_ROWS: dict[str, str] = {
    "agent-bridge-launch": "agent-bridge",
    "PortfolioCommandCenter-public": "PortfolioCommandCenter",
}

# Operator-machine source locations (overridable via the "sources" block of
# config/project-registry-overrides.json). Every source is optional.
DEFAULT_SOURCES: dict[str, str] = {
    "bridge_db": "~/.local/share/bridge-db/bridge.db",
    "notion_snapshot": "~/.local/share/notion-os/project-snapshot.json",
    "memory_dir": "~/.claude/projects/-Users-d/memory",
    "scoring_data_source_id": "35e04e4d-bcd8-45c0-b783-238edef210f7",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def normalize(value: str | None) -> str:
    """Lowercase, drop any taxonomy path prefix, strip non-alphanumerics."""
    if not value:
        return ""
    text = str(value)
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return _NON_ALNUM.sub("", text.lower())


def _repo_base(repo_full_name: str | None) -> str:
    return repo_full_name.rsplit("/", 1)[-1] if repo_full_name else ""


def _strip_alias_prefix(alias: str) -> str:
    return alias.split(":", 1)[1] if ":" in alias else alias


def load_overrides_config(
    config_path: Path | None,
) -> tuple[
    dict[str, str],
    list[dict],
    dict[str, str],
    str,
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
    """Load overrides + supplementary + memory-meta, falling back to defaults."""
    if config_path is None or not config_path.exists():
        return (
            dict(DEFAULT_OVERRIDES),
            [dict(s) for s in DEFAULT_SUPPLEMENTARY],
            dict(DEFAULT_MEMORY_META),
            NOTION_PROJECTION_POLICY_SCHEMA_VERSION,
            dict(DEFAULT_NOTION_TITLE_ALIASES),
            dict(DEFAULT_NOTION_PROJECTION_ONLY_ROWS),
            dict(DEFAULT_NOTION_TRUTH_SHADOW_ROWS),
        )
    data = json.loads(config_path.read_text())
    overrides = data.get("overrides", DEFAULT_OVERRIDES)
    supplementary = data.get("supplementary", DEFAULT_SUPPLEMENTARY)
    memory_meta = data.get("memory_meta", DEFAULT_MEMORY_META)
    projection_policy_schema_version = data.get(
        "notion_projection_policy_schema_version",
        NOTION_PROJECTION_POLICY_SCHEMA_VERSION,
    )
    title_aliases = data.get("notion_title_aliases", DEFAULT_NOTION_TITLE_ALIASES)
    projection_only = data.get(
        "notion_projection_only_rows", DEFAULT_NOTION_PROJECTION_ONLY_ROWS
    )
    truth_shadow = data.get(
        "notion_truth_shadow_rows", DEFAULT_NOTION_TRUTH_SHADOW_ROWS
    )
    return (
        dict(overrides),
        [dict(s) for s in supplementary],
        dict(memory_meta),
        str(projection_policy_schema_version),
        dict(title_aliases),
        dict(projection_only),
        dict(truth_shadow),
    )


def load_source_paths(config_path: Path | None) -> dict[str, object]:
    """Resolve external-source locations, merging config over built-in defaults.

    Returns a dict with ``bridge_db``/``notion_snapshot``/``memory_dir`` as
    expanded ``Path`` objects and ``scoring_data_source_id`` as a string.
    """
    sources = dict(DEFAULT_SOURCES)
    if config_path is not None and config_path.exists():
        try:
            configured = json.loads(config_path.read_text()).get("sources", {})
            sources.update({k: v for k, v in configured.items() if v})
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "bridge_db": Path(sources["bridge_db"]).expanduser(),
        "notion_snapshot": Path(sources["notion_snapshot"]).expanduser(),
        "memory_dir": Path(sources["memory_dir"]).expanduser(),
        "scoring_data_source_id": sources.get("scoring_data_source_id"),
    }


def _read_bridge_names(bridge_db_path: Path | None) -> list[str]:
    if bridge_db_path is None or not bridge_db_path.exists():
        return []
    try:
        uri = f"file:{bridge_db_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                "SELECT DISTINCT project_name FROM activity_log "
                "UNION SELECT DISTINCT project_name FROM pending_handoffs"
            ).fetchall()
        return [r[0] for r in rows if r[0]]
    except sqlite3.Error:
        return []


def _read_notion_titles(notion_snapshot_path: Path | None) -> list[str]:
    if notion_snapshot_path is None or not notion_snapshot_path.exists():
        return []
    try:
        data = json.loads(notion_snapshot_path.read_text())
        return [p["title"] for p in data.get("projects", []) if p.get("title")]
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def _read_notion_pageids(notion_project_map_path: Path | None) -> dict[str, str]:
    if notion_project_map_path is None or not notion_project_map_path.exists():
        return {}
    try:
        data = json.loads(notion_project_map_path.read_text())
        return {
            name: entry["localProjectId"]
            for name, entry in data.items()
            if isinstance(entry, dict) and entry.get("localProjectId")
        }
    except (json.JSONDecodeError, OSError):
        return {}


def _read_memory_slugs(memory_dir: Path | None) -> list[str]:
    if memory_dir is None or not memory_dir.exists():
        return []
    return sorted(p.name[len("project_") : -len(".md")] for p in memory_dir.glob("project_*.md"))


class _Entry:
    """Mutable accumulator for one canonical project during the join."""

    __slots__ = (
        "canonical_key",
        "display_name",
        "repo_full_name",
        "group_key",
        "lifecycle_state",
        "source",
        "note",
        "matchset",
        "bridge_names",
        "notion_local_title",
        "notion_local_page_id",
        "notion_scoring_page_id",
        "memory_slug",
        "memory_meta",
        "aliases",
    )

    def __init__(self, identity: dict, lifecycle_state: str | None, source: str, note: str | None):
        self.canonical_key = identity["project_key"]
        self.display_name = identity.get("display_name") or self.canonical_key
        self.repo_full_name = identity.get("repo_full_name") or None
        self.group_key = identity.get("group_key")
        self.lifecycle_state = lifecycle_state
        self.source = source
        self.note = note
        self.matchset = {
            f
            for f in (
                normalize(self.display_name),
                normalize(self.canonical_key),
                normalize(_repo_base(self.repo_full_name)),
            )
            if f
        }
        self.bridge_names: list[str] = []
        self.notion_local_title: str | None = None
        self.notion_local_page_id: str | None = None
        self.notion_scoring_page_id: str | None = None
        self.memory_slug: str | None = None
        self.memory_meta: list[str] = []
        self.aliases: set[str] = set()

    def add_alias(self, prefixed: str) -> None:
        if _strip_alias_prefix(prefixed) != self.display_name:
            self.aliases.add(prefixed)

    def _supp_key(self) -> str | None:
        """Post-migration canonical key for a repo-less project.

        Per the signed IDENTITY-DECISION-RECORD, ``repo_full_name`` is the
        canonical key when a project has a GitHub remote; a repo-less project
        gets a stable ``supp:<canonical_key>`` key instead. Returns ``None``
        for repo-backed entries (they resolve via ``repo_full_name``).
        Hardcoded supplementary entries already carry a ``supp:``
        ``canonical_key`` and pass through unchanged; auditor-discovered
        repo-less entries prefix the *full* ``canonical_key`` (a path-shaped
        ``project_key``) so the supp: key stays 1:1 with the already-unique
        canonical_key and two projects sharing a leaf segment cannot collide.
        """
        if self.repo_full_name:
            return None
        if self.canonical_key.startswith("supp:"):
            return self.canonical_key
        return f"supp:{self.canonical_key}"

    def to_dict(self) -> dict:
        out = {
            "canonical_key": self.canonical_key,
            "display_name": self.display_name,
            "repo_full_name": self.repo_full_name,
            "supp_key": self._supp_key(),
            "group_key": self.group_key,
            "lifecycle_state": self.lifecycle_state,
            "source": self.source,
            "bridge_project_names": self.bridge_names,
            "notion_local_title": self.notion_local_title,
            "notion_local_page_id": self.notion_local_page_id,
            "notion_scoring_page_id": self.notion_scoring_page_id,
            "memory_slug": self.memory_slug,
            "memory_meta_notes": self.memory_meta,
            "aliases": sorted(self.aliases),
            "coverage": {
                "auditor": self.source == "auditor",
                "bridge": bool(self.bridge_names),
                "notion_local": bool(self.notion_local_title),
                "memory": bool(self.memory_slug),
            },
        }
        if self.note:
            out["note"] = self.note
        return out


def build_project_registry(
    snapshot: dict,
    *,
    bridge_db_path: Path | None = None,
    notion_snapshot_path: Path | None = None,
    notion_project_map_path: Path | None = None,
    memory_dir: Path | None = None,
    scoring_pageids: dict[str, str] | None = None,
    overrides_config_path: Path | None = None,
    generated_at: datetime | None = None,
) -> dict:
    """Build the canonical registry from a portfolio-truth snapshot dict.

    ``snapshot`` is the serialized portfolio-truth (``snapshot.to_dict()``).
    All other sources are optional and degrade gracefully.
    """
    (
        overrides,
        supplementary,
        memory_meta,
        notion_projection_policy_schema_version,
        notion_title_aliases,
        notion_projection_only_rows,
        notion_truth_shadow_rows,
    ) = load_overrides_config(overrides_config_path)
    generated_at = generated_at or datetime.now(timezone.utc)

    entries: list[_Entry] = [
        _Entry(p["identity"], (p.get("declared") or {}).get("lifecycle_state"), "auditor", None)
        for p in snapshot.get("projects", [])
    ]
    for supp in supplementary:
        entries.append(
            _Entry(
                {
                    "project_key": supp["canonical_key"],
                    "display_name": supp.get("display_name"),
                    "repo_full_name": supp.get("repo_full_name"),
                    "group_key": supp.get("group_key"),
                },
                supp.get("lifecycle_state"),
                "supplementary",
                supp.get("note"),
            )
        )

    by_key = {e.canonical_key: e for e in entries}
    index: dict[str, _Entry] = {}
    collisions: list[dict] = []
    for entry in entries:
        for form in entry.matchset:
            existing = index.get(form)
            if existing is None:
                index[form] = entry
            elif existing is not entry:
                # Two distinct projects normalize to the same form: the index
                # keeps the first (stable), so the second would mis-resolve.
                # Surface it as a warning rather than failing silently.
                collisions.append(
                    {
                        "normalized_form": form,
                        "kept": existing.canonical_key,
                        "shadowed": entry.canonical_key,
                    }
                )
    override_norm = {normalize(raw): key for raw, key in overrides.items()}
    title_alias_norm = {
        normalize(raw): target for raw, target in notion_title_aliases.items()
    }
    projection_only_norm = {
        normalize(raw): raw for raw in notion_projection_only_rows
    }

    def resolve_entry_direct(raw: str) -> _Entry | None:
        norm = normalize(raw)
        if not norm:
            return None
        if norm in override_norm:
            target = by_key.get(override_norm[norm])
            if target is not None:
                return target
        return index.get(norm)

    def resolve_entry(raw: str) -> _Entry | None:
        entry = resolve_entry_direct(raw)
        if entry is not None:
            return entry
        alias_target = title_alias_norm.get(normalize(raw))
        if alias_target:
            return resolve_entry_direct(alias_target)
        return None

    notion_orphans: list[str] = []
    notion_projection_only: list[dict[str, str]] = []
    for title in _read_notion_titles(notion_snapshot_path):
        entry = resolve_entry(title)
        if entry is not None:
            entry.notion_local_title = title
            entry.add_alias(f"notion:{title}")
        elif normalize(title) in projection_only_norm:
            notion_projection_only.append(
                {
                    "title": title,
                    "reason": notion_projection_only_rows.get(title)
                    or notion_projection_only_rows.get(projection_only_norm[normalize(title)])
                    or "",
                }
            )
        else:
            notion_orphans.append(title)

    pageid_unmatched: list[str] = []
    for name, page_id in _read_notion_pageids(notion_project_map_path).items():
        entry = resolve_entry(name)
        if entry is not None:
            entry.notion_local_page_id = page_id
            entry.add_alias(f"notionmap:{name}")
        else:
            pageid_unmatched.append(name)

    for project_name, page_id in (scoring_pageids or {}).items():
        entry = resolve_entry(project_name)
        if entry is not None:
            entry.notion_scoring_page_id = page_id

    memory_orphans: list[dict] = []
    for slug in _read_memory_slugs(memory_dir):
        if slug in memory_meta:
            parent = memory_meta[slug]
            if parent and parent in by_key:
                by_key[parent].memory_meta.append(f"project_{slug}")
                continue
            if not parent:
                memory_orphans.append({"slug": slug, "kind": "meta-epic-note"})
                continue
        entry = resolve_entry(slug)
        if entry is not None:
            if entry.memory_slug is None:
                entry.memory_slug = f"project_{slug}"
            else:
                entry.memory_meta.append(f"project_{slug}")
            entry.add_alias(f"memory:{slug}")
        else:
            memory_orphans.append({"slug": slug, "kind": "unmatched"})

    bridge_orphans: list[str] = []
    for name in _read_bridge_names(bridge_db_path):
        entry = resolve_entry(name)
        if entry is not None:
            if name not in entry.bridge_names:
                entry.bridge_names.append(name)
            entry.add_alias(f"bridge:{name}")
        else:
            bridge_orphans.append(name)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": (
            "Canonical cross-store project-identity registry for the operator "
            "OS. Joins GithubRepoAuditor, bridge-db, Notion (Local Portfolio "
            "Projects), and ~/.claude memory under one canonical key."
        ),
        "canonical_key": {
            "primary": "GithubRepoAuditor identity.project_key (taxonomy-path-qualified)",
            "secondary": "repo_full_name (saagpatel/<repo>)",
            "supplementary": "supp:<name> for operator-OS projects the auditor does not track",
        },
        "entry_count": len(entries),
        "resolution_overrides": overrides,
        "projection_policy": {
            "schema_version": notion_projection_policy_schema_version,
            "notion_title_aliases": notion_title_aliases,
            "notion_projection_only_rows": notion_projection_only_rows,
            "notion_truth_shadow_rows": notion_truth_shadow_rows,
        },
        "entries": [e.to_dict() for e in entries],
        "projection_only": {
            "notion_local": sorted(notion_projection_only, key=lambda row: row["title"])
        },
        "unmatched": {
            "bridge": sorted(bridge_orphans),
            "memory": memory_orphans,
            "notion_local": sorted(notion_orphans),
            "notion_pageid_map": sorted(pageid_unmatched),
        },
        "warnings": {"normalized_key_collisions": collisions},
    }


def build_index(registry: dict) -> dict:
    """Precompute lookup structures from a built registry for resolve()."""
    norm2entry: dict[str, dict] = {}
    for entry in registry["entries"]:
        forms = {normalize(entry["display_name"])}
        if entry.get("repo_full_name"):
            forms.add(normalize(_repo_base(entry["repo_full_name"])))
        if "/" in (entry.get("canonical_key") or ""):
            forms.add(normalize(entry["canonical_key"]))
        for alias in entry.get("aliases", []):
            forms.add(normalize(_strip_alias_prefix(alias)))
        for form in forms:
            if form:
                norm2entry.setdefault(form, entry)
    override_norm = {
        normalize(raw): key for raw, key in registry.get("resolution_overrides", {}).items()
    }
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    return {"norm2entry": norm2entry, "override_norm": override_norm, "by_key": by_key}


def resolve(name: str, index: dict) -> dict | None:
    """Map a free-form project name to its canonical entry, or None."""
    norm = normalize(name)
    if not norm:
        return None
    if norm in index["override_norm"]:
        entry = index["by_key"].get(index["override_norm"][norm])
        if entry is not None:
            return {
                "canonical_key": entry["canonical_key"],
                "display_name": entry["display_name"],
                "matched_via": "override",
            }
    entry = index["norm2entry"].get(norm)
    if entry is not None:
        return {
            "canonical_key": entry["canonical_key"],
            "display_name": entry["display_name"],
            "matched_via": "normalized",
        }
    return None


def fetch_scoring_pageids(data_source_id: str, token: str) -> dict[str, str]:
    """Read Project Name -> page_id from the Notion Project Portfolio DB.

    Uses the auditor's Notion client; paginates the data source. Returns an
    empty dict on any failure so registry generation never hard-depends on it.
    """
    from src.notion_client import query_notion_collection

    result: dict[str, str] = {}
    cursor: str | None = None
    try:
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            response = query_notion_collection(data_source_id, token, body=body)
            if response is None or response.status_code != 200:
                break
            payload = response.json()
            for page in payload.get("results", []):
                title_prop = page.get("properties", {}).get("Project Name", {})
                segments = title_prop.get("title", []) if isinstance(title_prop, dict) else []
                name = "".join(seg.get("plain_text", "") for seg in segments).strip()
                if name and page.get("id"):
                    result[name] = page["id"]
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
            if not cursor:
                break
    except Exception:
        return result
    return result
