from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.models import RepoAudit

VALID_STATUSES = {"active", "recent", "parked", "archived"}

# Separator row pattern: |---|---|...|
SEPARATOR_RE = re.compile(r"^\|[\s\-:]+\|")

# Header keywords that indicate a header row (not data)
HEADER_KEYWORDS = {"project", "status", "tool", "context", "stack", "notes", "category", "metric", "count"}


def _normalize(name: str) -> str:
    """Normalize a project name for fuzzy matching.

    Strips hyphens, underscores, lowercases, removes common suffixes.
    """
    n = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    # Remove common suffixes that vary between registry and GitHub
    for suffix in ("prod", "ready", "readiness"):
        if n.endswith(suffix) and len(n) > len(suffix):
            n = n[: -len(suffix)]
    return n


def parse_registry(path: Path) -> dict[str, str]:
    """Parse project-registry.md into {project_name: status} mapping.

    Handles variable-column markdown tables across multiple sections.
    Column 1 is always Project, Column 2 is always Status.
    """
    content = path.read_text(errors="replace")
    projects: dict[str, str] = {}

    for line in content.splitlines():
        line = line.strip()

        # Skip non-table lines
        if not line.startswith("|"):
            continue

        # Skip separator rows
        if SEPARATOR_RE.match(line):
            continue

        # Split into columns
        cols = [c.strip() for c in line.split("|")]
        # Leading/trailing pipes create empty strings
        cols = [c for c in cols if c]

        if len(cols) < 2:
            continue

        name = cols[0].strip()
        status = cols[1].strip().lower()

        # Skip header rows
        if name.lower() in HEADER_KEYWORDS or status in HEADER_KEYWORDS:
            continue

        # Skip summary table rows (e.g., "Total projects | 64")
        if status.isdigit():
            continue

        # Only accept valid statuses
        if status not in VALID_STATUSES:
            continue

        projects[name] = status

    return projects


@dataclass
class RegistryReconciliation:
    on_github_not_registry: list[str]
    in_registry_not_github: list[str]
    matched: list[dict] = field(default_factory=list)
    registry_total: int = 0
    github_total: int = 0

    def to_dict(self) -> dict:
        return {
            "on_github_not_registry": self.on_github_not_registry,
            "in_registry_not_github": self.in_registry_not_github,
            "matched": self.matched,
            "registry_total": self.registry_total,
            "github_total": self.github_total,
        }


def reconcile(
    registry: dict[str, str],
    audits: list[RepoAudit],
) -> RegistryReconciliation:
    """Cross-reference registry projects with GitHub audit results.

    Uses three-pass matching: exact, case-insensitive, normalized.
    """
    # Build lookup structures for registry
    registry_exact: dict[str, str] = dict(registry)  # name -> status
    registry_lower: dict[str, str] = {k.lower(): k for k in registry}
    registry_norm: dict[str, str] = {_normalize(k): k for k in registry}

    matched_registry_names: set[str] = set()
    matched: list[dict] = []

    audit_map: dict[str, RepoAudit] = {a.metadata.name: a for a in audits}

    for repo_name, audit in audit_map.items():
        registry_name: str | None = None

        # Pass 1: exact match
        if repo_name in registry_exact:
            registry_name = repo_name
        # Pass 2: case-insensitive
        elif repo_name.lower() in registry_lower:
            registry_name = registry_lower[repo_name.lower()]
        # Pass 3: normalized
        else:
            norm = _normalize(repo_name)
            if norm in registry_norm:
                registry_name = registry_norm[norm]

        if registry_name:
            matched_registry_names.add(registry_name)
            matched.append({
                "github_name": repo_name,
                "registry_name": registry_name,
                "registry_status": registry[registry_name],
                "audit_tier": audit.completeness_tier,
                "score": round(audit.overall_score, 3),
            })

    # Unmatched repos (on GitHub but not in registry)
    on_github_not_registry = sorted(
        name for name in audit_map if not any(
            m["github_name"] == name for m in matched
        )
    )

    # Unmatched registry entries (in registry but not on GitHub)
    in_registry_not_github = sorted(
        name for name in registry if name not in matched_registry_names
    )

    # Sort matched by score descending
    matched.sort(key=lambda m: m["score"], reverse=True)

    return RegistryReconciliation(
        on_github_not_registry=on_github_not_registry,
        in_registry_not_github=in_registry_not_github,
        matched=matched,
        registry_total=len(registry),
        github_total=len(audits),
    )
