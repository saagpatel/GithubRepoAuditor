from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

VALID_LIFECYCLE_STATES = {"active", "maintenance", "dormant", "experimental", "archived"}
VALID_CRITICALITY = {"low", "medium", "high", "critical"}
VALID_REVIEW_CADENCE = {"weekly", "monthly", "quarterly", "ad-hoc"}
VALID_INTENDED_DISPOSITIONS = {"maintain", "finish", "archive", "experiment"}
DEFAULT_CATALOG_PATH = Path("config") / "portfolio-catalog.yaml"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(key: str) -> str:
    return key.strip().lower()


def _normalize_enum(value: Any, allowed: set[str]) -> str:
    normalized = _safe_text(value).lower()
    return normalized if normalized in allowed else ""


def load_portfolio_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or DEFAULT_CATALOG_PATH
    if not catalog_path.is_file():
        return {
            "path": str(catalog_path),
            "exists": False,
            "errors": [],
            "warnings": [],
            "defaults": {},
            "repos": {},
        }

    try:
        import yaml
    except ImportError:
        return {
            "path": str(catalog_path),
            "exists": True,
            "errors": [],
            "warnings": ["PyYAML is not installed, so the portfolio catalog was skipped."],
            "defaults": {},
            "repos": {},
        }

    try:
        loaded = yaml.safe_load(catalog_path.read_text()) or {}
    except yaml.YAMLError as exc:
        return {
            "path": str(catalog_path),
            "exists": True,
            "errors": [f"Failed to parse portfolio catalog: {exc}"],
            "warnings": [],
            "defaults": {},
            "repos": {},
        }

    if not isinstance(loaded, dict):
        return {
            "path": str(catalog_path),
            "exists": True,
            "errors": ["Portfolio catalog root must be a mapping."],
            "warnings": [],
            "defaults": {},
            "repos": {},
        }

    errors: list[str] = []
    warnings: list[str] = []
    defaults = _normalize_defaults(loaded.get("defaults") or {}, errors)
    repos = _normalize_repo_entries(loaded.get("repos") or {}, defaults, errors, warnings)
    return {
        "path": str(catalog_path),
        "exists": True,
        "errors": errors,
        "warnings": warnings,
        "defaults": defaults,
        "repos": repos,
    }


def _normalize_defaults(defaults: Any, errors: list[str]) -> dict[str, str]:
    if not isinstance(defaults, dict):
        if defaults:
            errors.append("Portfolio catalog defaults must be a mapping.")
        return {}

    normalized = {
        "lifecycle_state": _normalize_enum(defaults.get("lifecycle_state"), VALID_LIFECYCLE_STATES),
        "criticality": _normalize_enum(defaults.get("criticality"), VALID_CRITICALITY),
        "review_cadence": _normalize_enum(defaults.get("review_cadence"), VALID_REVIEW_CADENCE),
    }
    for key, allowed in (
        ("lifecycle_state", VALID_LIFECYCLE_STATES),
        ("criticality", VALID_CRITICALITY),
        ("review_cadence", VALID_REVIEW_CADENCE),
    ):
        raw_value = defaults.get(key)
        if raw_value and not normalized[key]:
            errors.append(f"Portfolio catalog defaults.{key} must be one of: {', '.join(sorted(allowed))}.")
    return {key: value for key, value in normalized.items() if value}


def _normalize_repo_entries(
    entries: Any,
    defaults: dict[str, str],
    errors: list[str],
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, dict):
        if entries:
            errors.append("Portfolio catalog repos must be a mapping keyed by repo name.")
        return {}

    normalized_entries: dict[str, dict[str, Any]] = {}
    seen_bare_names: set[str] = set()

    for raw_key, raw_value in entries.items():
        key = _safe_text(raw_key)
        if not key:
            continue
        if not isinstance(raw_value, dict):
            errors.append(f"Portfolio catalog entry '{key}' must be a mapping.")
            continue
        normalized = {
            "owner": _safe_text(raw_value.get("owner")),
            "team": _safe_text(raw_value.get("team")),
            "purpose": _safe_text(raw_value.get("purpose")),
            "lifecycle_state": _normalize_enum(raw_value.get("lifecycle_state"), VALID_LIFECYCLE_STATES) or defaults.get("lifecycle_state", ""),
            "criticality": _normalize_enum(raw_value.get("criticality"), VALID_CRITICALITY) or defaults.get("criticality", ""),
            "review_cadence": _normalize_enum(raw_value.get("review_cadence"), VALID_REVIEW_CADENCE) or defaults.get("review_cadence", ""),
            "intended_disposition": _normalize_enum(raw_value.get("intended_disposition"), VALID_INTENDED_DISPOSITIONS),
            "notes": _safe_text(raw_value.get("notes")),
            "catalog_key": key,
            "matched_by": "full-name" if "/" in key else "bare-name",
            "has_explicit_entry": True,
        }
        for field_name, allowed in (
            ("lifecycle_state", VALID_LIFECYCLE_STATES),
            ("criticality", VALID_CRITICALITY),
            ("review_cadence", VALID_REVIEW_CADENCE),
            ("intended_disposition", VALID_INTENDED_DISPOSITIONS),
        ):
            raw_enum = raw_value.get(field_name)
            if raw_enum and not normalized[field_name]:
                errors.append(f"Portfolio catalog entry '{key}' has invalid {field_name}: {raw_enum}.")

        if "/" not in key:
            bare_key = _normalize_key(key)
            if bare_key in seen_bare_names:
                warnings.append(f"Portfolio catalog bare repo key '{key}' is duplicated and may be ambiguous.")
            seen_bare_names.add(bare_key)

        normalized_entries[_normalize_key(key)] = normalized

    return normalized_entries


def catalog_entry_for_repo(
    metadata: dict[str, Any],
    catalog_data: dict[str, Any],
) -> dict[str, Any]:
    repos = catalog_data.get("repos") or {}
    full_name = _safe_text(metadata.get("full_name"))
    repo_name = _safe_text(metadata.get("name"))
    normalized_full_name = _normalize_key(full_name)
    normalized_repo_name = _normalize_key(repo_name)

    matched = repos.get(normalized_full_name)
    if matched:
        return {
            **matched,
            "repo": repo_name,
            "repo_full_name": full_name,
        }

    if normalized_repo_name and normalized_repo_name in repos:
        return {
            **repos[normalized_repo_name],
            "repo": repo_name,
            "repo_full_name": full_name,
        }

    return {
        "repo": repo_name,
        "repo_full_name": full_name,
        "owner": "",
        "team": "",
        "purpose": "",
        "lifecycle_state": "",
        "criticality": "",
        "review_cadence": "",
        "intended_disposition": "",
        "notes": "",
        "catalog_key": "",
        "matched_by": "",
        "has_explicit_entry": False,
    }


def build_catalog_line(entry: dict[str, Any]) -> str:
    if not entry or not entry.get("has_explicit_entry"):
        return "No portfolio catalog contract is recorded yet."
    segments = []
    owner_or_team = _safe_text(entry.get("team")) or _safe_text(entry.get("owner"))
    if owner_or_team:
        segments.append(owner_or_team)
    if entry.get("purpose"):
        segments.append(str(entry["purpose"]))
    if entry.get("lifecycle_state"):
        segments.append(f"lifecycle {entry['lifecycle_state']}")
    if entry.get("criticality"):
        segments.append(f"criticality {entry['criticality']}")
    if entry.get("review_cadence"):
        segments.append(f"cadence {entry['review_cadence']}")
    if entry.get("intended_disposition"):
        segments.append(f"disposition {entry['intended_disposition']}")
    return " | ".join(segments) if segments else "Portfolio catalog contract is present."


def evaluate_intent_alignment(
    entry: dict[str, Any],
    *,
    completeness_tier: str,
    archived: bool,
    operator_focus: str,
) -> tuple[str, str]:
    if not entry or not entry.get("has_explicit_entry"):
        return ("missing-contract", "No explicit portfolio catalog contract is recorded for this repo yet.")

    disposition = _safe_text(entry.get("intended_disposition")).lower()
    tier = _safe_text(completeness_tier).lower()
    focus = _safe_text(operator_focus)

    if disposition == "archive" and (archived or tier in {"abandoned", "skeleton"}):
        return ("aligned", "The repo posture already matches the plan to archive or let it stay dormant.")
    if disposition == "experiment" and (tier in {"wip", "skeleton"} or focus in {"Watch Closely", "Improving"}):
        return ("aligned", "The repo still looks like an experiment rather than a slipped maintenance commitment.")
    if disposition == "maintain" and tier in {"functional", "shipped"} and focus not in {"Act Now", "Revalidate"}:
        return ("aligned", "The repo is holding a maintain posture without urgent or revalidation pressure.")
    if disposition == "finish" and tier in {"wip", "functional"} and focus != "Revalidate":
        return ("aligned", "The repo still looks finishable rather than fully off-track.")

    return (
        "needs-review",
        "The current repo condition and the intended disposition are no longer clearly aligned.",
    )


def build_portfolio_catalog_summary(audits: list[Any], *, catalog_path: str = "") -> dict[str, Any]:
    lifecycle = Counter()
    criticality = Counter()
    cadence = Counter()
    disposition = Counter()
    owners = Counter()
    explicit_count = 0

    for audit in audits:
        entry = getattr(audit, "portfolio_catalog", None) if hasattr(audit, "portfolio_catalog") else (audit or {}).get("portfolio_catalog", {})
        if not entry or not entry.get("has_explicit_entry"):
            continue
        explicit_count += 1
        if entry.get("lifecycle_state"):
            lifecycle[entry["lifecycle_state"]] += 1
        if entry.get("criticality"):
            criticality[entry["criticality"]] += 1
        if entry.get("review_cadence"):
            cadence[entry["review_cadence"]] += 1
        if entry.get("intended_disposition"):
            disposition[entry["intended_disposition"]] += 1
        if entry.get("team") or entry.get("owner"):
            owners[_safe_text(entry.get("team")) or _safe_text(entry.get("owner"))] += 1

    total_repos = len(audits)
    missing_contract_count = max(total_repos - explicit_count, 0)
    summary = (
        f"{explicit_count}/{total_repos} repos have an explicit catalog contract."
        if total_repos
        else "No audited repos are available."
    )
    if missing_contract_count:
        summary += f" {missing_contract_count} repo(s) still need a contract."

    return {
        "catalog_path": catalog_path,
        "cataloged_repo_count": explicit_count,
        "missing_contract_count": missing_contract_count,
        "lifecycle_state_counts": dict(lifecycle),
        "criticality_counts": dict(criticality),
        "review_cadence_counts": dict(cadence),
        "intended_disposition_counts": dict(disposition),
        "owner_counts": dict(owners),
        "top_owners": [name for name, _count in owners.most_common(5)],
        "summary": summary,
    }


def build_intent_alignment_summary(audits: list[Any]) -> dict[str, Any]:
    counts = Counter()
    for audit in audits:
        entry = getattr(audit, "portfolio_catalog", None) if hasattr(audit, "portfolio_catalog") else (audit or {}).get("portfolio_catalog", {})
        counts[_safe_text(entry.get("intent_alignment")) or "missing-contract"] += 1

    summary = (
        f"{counts.get('aligned', 0)} aligned, {counts.get('needs-review', 0)} needing review, "
        f"and {counts.get('missing-contract', 0)} missing a contract."
    )
    return {
        "counts": dict(counts),
        "summary": summary,
    }
