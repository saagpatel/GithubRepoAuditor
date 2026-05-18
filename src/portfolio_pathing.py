from __future__ import annotations

from collections import Counter
from typing import Any

VALID_OPERATING_PATHS = frozenset({"maintain", "finish", "archive", "experiment"})
VALID_MATURITY_PROGRAMS = frozenset({"default", *VALID_OPERATING_PATHS})
VALID_PATH_CONFIDENCE = frozenset({"high", "medium", "low", "legacy"})
INVESTIGATE_OVERRIDE = "investigate"
VALID_PATH_OVERRIDES = frozenset({INVESTIGATE_OVERRIDE})


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: Any) -> str:
    return _safe_text(value).lower()


def _labelize(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


# Utility: resolves catalog entry to (path, provenance) tuple.
# Called internally by build_operating_path_entry() in this module.
def resolve_declared_operating_path(entry: dict[str, Any]) -> tuple[str, str]:
    explicit_path = _normalize_key(entry.get("operating_path"))
    if explicit_path in VALID_OPERATING_PATHS:
        return explicit_path, "explicit-operating-path"

    intended_disposition = _normalize_key(entry.get("intended_disposition"))
    if intended_disposition in VALID_OPERATING_PATHS:
        return intended_disposition, "intended-disposition"

    explicit_contract = bool(entry.get("has_explicit_entry"))
    maturity_program = _normalize_key(entry.get("maturity_program"))
    if explicit_contract and maturity_program in VALID_OPERATING_PATHS:
        return maturity_program, "maturity-program"

    return "", ""


def build_operating_path_entry(
    entry: dict[str, Any],
    *,
    context_quality: str = "",
    intent_alignment: str = "",
    archived: bool = False,
    registry_status: str = "",
    completeness_tier: str = "",
    decision_quality_status: str = "",
) -> dict[str, Any]:
    stable_path, path_source = resolve_declared_operating_path(entry)
    maturity_program = _normalize_key(entry.get("maturity_program"))
    intended_disposition = _normalize_key(entry.get("intended_disposition"))
    explicit_contract = bool(entry.get("has_explicit_entry"))
    context_quality = _normalize_key(context_quality)
    intent_alignment = _normalize_key(intent_alignment)
    registry_status = _normalize_key(registry_status)
    completeness_tier = _normalize_key(completeness_tier)
    decision_quality_status = _normalize_key(decision_quality_status)

    concerns: list[str] = []
    rationale_parts: list[str] = []

    if stable_path:
        rationale_parts.append(
            f"Stable path is {_labelize(stable_path)} from {path_source.replace('-', ' ')}."
        )
    else:
        concerns.append("missing-operating-path")
        rationale_parts.append("No stable operating path is declared yet.")

    if (
        maturity_program in VALID_OPERATING_PATHS
        and intended_disposition in VALID_OPERATING_PATHS
        and maturity_program != intended_disposition
    ):
        concerns.append("program-disposition-conflict")
        rationale_parts.append(
            "Declared maturity program and intended disposition point at different paths."
        )

    if not explicit_contract:
        concerns.append("missing-explicit-contract")
        rationale_parts.append(
            "This repo is still relying on defaults or inferred portfolio intent."
        )

    if intent_alignment == "needs-review":
        concerns.append("intent-needs-review")
        rationale_parts.append(
            "Current repo condition is no longer clearly aligned with the declared intent."
        )

    if context_quality in {"none", "boilerplate"}:
        concerns.append("weak-context")
        rationale_parts.append(
            "Context quality is still too weak for path guidance to stand on its own."
        )

    if archived or registry_status == "archived":
        if stable_path != "archive":
            concerns.append("archived-outside-archive-path")
            rationale_parts.append(
                "The repo currently looks archival, but the declared operating path is not archive."
            )
    elif completeness_tier in {"abandoned", "skeleton"} and stable_path in {"maintain", "finish"}:
        concerns.append("repo-state-below-path-bar")
        rationale_parts.append(
            "Current repo maturity is still below what the declared operating path usually expects."
        )

    if decision_quality_status in {"needs-skepticism", "insufficient-data"}:
        rationale_parts.append(
            "Portfolio decision quality still requires review before path guidance should be treated as strong."
        )

    if any(
        concern
        in {
            "missing-operating-path",
            "program-disposition-conflict",
            "intent-needs-review",
            "weak-context",
            "archived-outside-archive-path",
        }
        for concern in concerns
    ):
        path_confidence = "low"
    elif not explicit_contract:
        path_confidence = "medium"
    elif context_quality == "minimum-viable":
        path_confidence = "medium"
    elif decision_quality_status in {"needs-skepticism", "insufficient-data"}:
        path_confidence = "medium"
    else:
        path_confidence = "high"

    path_override = INVESTIGATE_OVERRIDE if path_confidence == "low" else ""
    if path_override:
        rationale_parts.append("Treat this repo as investigate until path confidence improves.")

    rationale = " ".join(part for part in rationale_parts if part).strip()
    if not rationale:
        rationale = "No operating-path rationale is recorded yet."

    result = dict(entry)
    result.update(
        {
            "operating_path": stable_path,
            "operating_path_source": path_source,
            "path_override": path_override,
            "path_confidence": path_confidence,
            "path_rationale": rationale,
        }
    )
    return result


def build_operating_path_line(value: dict[str, Any]) -> str:
    path = _normalize_key(value.get("operating_path"))
    override = _normalize_key(value.get("path_override"))
    confidence = _normalize_key(value.get("path_confidence")) or "legacy"
    rationale = (
        _safe_text(value.get("path_rationale")) or "No operating-path rationale is recorded yet."
    )

    if path:
        headline = _labelize(path)
    else:
        headline = "Unspecified"
    if override == INVESTIGATE_OVERRIDE:
        headline = f"{headline} with Investigate override"
    return f"Operating Path: {headline} ({confidence} confidence) — {rationale}"


def build_operating_paths_summary(items: list[Any]) -> dict[str, Any]:
    path_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    override_counts: Counter[str] = Counter()

    for item in items:
        entry = (
            getattr(item, "portfolio_catalog", None)
            if hasattr(item, "portfolio_catalog")
            else (item or {}).get("portfolio_catalog", None)
        )
        if entry is None:
            continue
        path = _normalize_key(entry.get("operating_path")) or "unspecified"
        path_counts[path] += 1
        confidence = _normalize_key(entry.get("path_confidence")) or "legacy"
        confidence_counts[confidence] += 1
        override = _normalize_key(entry.get("path_override"))
        if override:
            override_counts[override] += 1

    ordered_paths = [
        f"{_labelize(path)} {path_counts[path]}"
        for path in ("maintain", "finish", "archive", "experiment")
        if path_counts.get(path)
    ]
    if path_counts.get("unspecified"):
        ordered_paths.append(f"Unspecified {path_counts['unspecified']}")
    summary = ", ".join(ordered_paths) if ordered_paths else "No operating paths are recorded yet."
    if override_counts:
        summary += (
            f". {sum(override_counts.values())} repo(s) currently require an "
            f"{INVESTIGATE_OVERRIDE} override."
        )
    return {
        "path_counts": dict(path_counts),
        "confidence_counts": dict(confidence_counts),
        "override_counts": dict(override_counts),
        "summary": summary,
    }
