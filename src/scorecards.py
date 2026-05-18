from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SCORECARDS_PATH = Path("config") / "scorecards.yaml"
VALID_RULE_CHECKS = {
    "dimension_at_least",
    "lens_at_least",
    "tier_at_least",
    "flag_absent",
    "activity_days_at_most",
    "security_posture_at_least",
    "audit_field_at_least",
    "catalog_field_in",
}
DEFAULT_LEVELS = [
    {"key": "missing-basics", "threshold": 0.0},
    {"key": "foundation", "threshold": 0.35},
    {"key": "operating", "threshold": 0.60},
    {"key": "strong", "threshold": 0.80},
    {"key": "leading", "threshold": 0.92},
]
DEFAULT_PROGRAM_TARGETS = {
    "default": "operating",
    "maintain": "strong",
    "finish": "operating",
    "experiment": "foundation",
    "archive": "foundation",
}
TIER_RANKS = {
    "abandoned": 0,
    "skeleton": 1,
    "wip": 2,
    "functional": 3,
    "shipped": 4,
}
NUMERIC_AUDIT_FIELDS = {"overall_score", "interest_score"}


@dataclass(frozen=True)
class RuleEvaluation:
    key: str
    label: str
    status: str
    weight: float
    value: float
    reason: str


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


def _normalize_key(value: Any) -> str:
    return _safe_text(value).lower()


def _normalize_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _labelize(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def load_scorecards(path: Path | None = None) -> dict[str, Any]:
    scorecards_path = path or DEFAULT_SCORECARDS_PATH
    if not scorecards_path.is_file():
        return {
            "path": str(scorecards_path),
            "exists": False,
            "errors": [],
            "warnings": [],
            "default_levels": list(DEFAULT_LEVELS),
            "programs": {},
        }

    try:
        import yaml
    except ImportError:
        return {
            "path": str(scorecards_path),
            "exists": True,
            "errors": [],
            "warnings": ["PyYAML is not installed, so scorecards were skipped."],
            "default_levels": list(DEFAULT_LEVELS),
            "programs": {},
        }

    try:
        loaded = yaml.safe_load(scorecards_path.read_text()) or {}
    except yaml.YAMLError as exc:
        return {
            "path": str(scorecards_path),
            "exists": True,
            "errors": [f"Failed to parse scorecards: {exc}"],
            "warnings": [],
            "default_levels": list(DEFAULT_LEVELS),
            "programs": {},
        }

    if not isinstance(loaded, dict):
        return {
            "path": str(scorecards_path),
            "exists": True,
            "errors": ["Scorecards root must be a mapping."],
            "warnings": [],
            "default_levels": list(DEFAULT_LEVELS),
            "programs": {},
        }

    errors: list[str] = []
    warnings: list[str] = []
    default_levels = _normalize_levels(loaded.get("levels"), errors, context="defaults")
    programs = _normalize_programs(loaded.get("programs"), default_levels, errors)
    return {
        "path": str(scorecards_path),
        "exists": True,
        "errors": errors,
        "warnings": warnings,
        "default_levels": default_levels,
        "programs": programs,
    }


def _normalize_levels(raw_levels: Any, errors: list[str], *, context: str) -> list[dict[str, Any]]:
    if raw_levels in (None, ""):
        return [dict(level) for level in DEFAULT_LEVELS]
    if not isinstance(raw_levels, list):
        errors.append(f"Scorecard {context} levels must be a list.")
        return [dict(level) for level in DEFAULT_LEVELS]

    levels: list[dict[str, Any]] = []
    thresholds: list[float] = []
    for index, raw in enumerate(raw_levels):
        if not isinstance(raw, dict):
            errors.append(f"Scorecard {context} level #{index + 1} must be a mapping.")
            continue
        key = _normalize_key(raw.get("key"))
        threshold = _normalize_float(raw.get("threshold"))
        if not key:
            errors.append(f"Scorecard {context} level #{index + 1} is missing key.")
            continue
        if threshold is None:
            errors.append(f"Scorecard {context} level '{key}' is missing threshold.")
            continue
        levels.append({"key": key, "label": _safe_text(raw.get("label")) or _labelize(key), "threshold": threshold})
        thresholds.append(threshold)

    if not levels:
        return [dict(level) for level in DEFAULT_LEVELS]
    if thresholds != sorted(thresholds):
        errors.append(f"Scorecard {context} levels must be ordered by ascending threshold.")
        return [dict(level) for level in DEFAULT_LEVELS]
    return levels


def _normalize_programs(
    raw_programs: Any,
    default_levels: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_programs, dict):
        if raw_programs:
            errors.append("Scorecards programs must be a mapping.")
        return {}

    programs: dict[str, dict[str, Any]] = {}
    for program_key, raw_program in raw_programs.items():
        key = _normalize_key(program_key)
        if not key:
            continue
        if not isinstance(raw_program, dict):
            errors.append(f"Scorecard program '{program_key}' must be a mapping.")
            continue
        rules = raw_program.get("rules")
        if not isinstance(rules, list) or not rules:
            errors.append(f"Scorecard program '{program_key}' must define at least one rule.")
            continue
        normalized_rules: list[dict[str, Any]] = []
        for index, raw_rule in enumerate(rules):
            if not isinstance(raw_rule, dict):
                errors.append(f"Scorecard program '{program_key}' rule #{index + 1} must be a mapping.")
                continue
            normalized_rule = _normalize_rule(raw_rule, errors, program_key=program_key)
            if normalized_rule:
                normalized_rules.append(normalized_rule)
        levels = _normalize_levels(raw_program.get("levels"), errors, context=f"program '{program_key}'")
        target = _normalize_key(raw_program.get("target_maturity")) or DEFAULT_PROGRAM_TARGETS.get(key, "operating")
        level_keys = {level["key"] for level in levels}
        if target not in level_keys:
            errors.append(
                f"Scorecard program '{program_key}' target_maturity '{target}' is not defined in its levels."
            )
            target = DEFAULT_PROGRAM_TARGETS.get(key, levels[min(len(levels) - 1, 2)]["key"])
        programs[key] = {
            "key": key,
            "label": _safe_text(raw_program.get("label")) or _labelize(key),
            "description": _safe_text(raw_program.get("description")) or "No scorecard description is recorded yet.",
            "levels": levels or default_levels,
            "target_maturity": target,
            "rules": normalized_rules,
        }
    return programs


def _normalize_rule(raw_rule: dict[str, Any], errors: list[str], *, program_key: str) -> dict[str, Any] | None:
    rule_key = _normalize_key(raw_rule.get("key"))
    check = _normalize_key(raw_rule.get("check"))
    if not rule_key:
        errors.append(f"Scorecard program '{program_key}' has a rule without key.")
        return None
    if check not in VALID_RULE_CHECKS:
        errors.append(f"Scorecard rule '{rule_key}' in program '{program_key}' uses unsupported check '{check}'.")
        return None
    weight = _normalize_float(raw_rule.get("weight"))
    if weight is None or weight <= 0:
        errors.append(f"Scorecard rule '{rule_key}' in program '{program_key}' must have a positive weight.")
        return None
    rule = {
        "key": rule_key,
        "label": _safe_text(raw_rule.get("label")) or _labelize(rule_key),
        "check": check,
        "weight": weight,
    }
    for field in (
        "dimension",
        "lens",
        "tier",
        "flag",
        "field",
        "catalog_field",
        "summary_label",
    ):
        text = _safe_text(raw_rule.get(field))
        if text:
            rule[field] = text
    threshold = _normalize_float(raw_rule.get("threshold"))
    if threshold is not None:
        rule["threshold"] = threshold
    partial_threshold = _normalize_float(raw_rule.get("partial_threshold"))
    if partial_threshold is not None:
        rule["partial_threshold"] = partial_threshold
    values = raw_rule.get("values")
    if isinstance(values, list):
        rule["values"] = [_safe_text(value).lower() for value in values if _safe_text(value)]
    return rule


def evaluate_scorecards_for_report(report, scorecards_data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    programs = scorecards_data.get("programs") or {}
    repo_results: list[dict[str, Any]] = []
    for audit in report.audits:
        repo_results.append(evaluate_repo_scorecard(audit, programs))
    summary = build_scorecards_summary(repo_results, scorecards_data)
    programs_summary = build_scorecard_programs_summary(scorecards_data)
    return repo_results, summary, programs_summary


def evaluate_repo_scorecard(audit: Any, programs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    audit_dict = _mapping(audit)
    metadata = _mapping(audit_dict.get("metadata"))
    catalog = {
        **_mapping(audit_dict.get("portfolio_catalog")),
        "archive_ready": (
            "yes"
            if bool(metadata.get("archived")) or _normalize_key(audit_dict.get("completeness_tier")) in {"skeleton", "abandoned"}
            else "no"
        ),
    }
    repo_name = _safe_text(metadata.get("name"))
    program_key = resolve_program_key(catalog, programs)
    if not program_key or program_key not in programs:
        missing_program = program_key or _safe_text(catalog.get("maturity_program")) or "default"
        return {
            "repo": repo_name,
            "program": missing_program,
            "program_label": _labelize(missing_program),
            "score": 0.0,
            "maturity_level": "missing-basics",
            "target_maturity": _safe_text(catalog.get("target_maturity")) or "",
            "status": "missing-program",
            "passed_rules": 0,
            "applicable_rules": 0,
            "failed_rule_keys": [],
            "top_gaps": [],
            "summary": f"No scorecard program definition is available for '{missing_program}'.",
            "rule_results": [],
        }

    program = programs[program_key]
    target_maturity = resolve_target_maturity(catalog, program)
    rule_results = [_evaluate_rule(audit_dict, catalog, rule) for rule in program.get("rules", [])]
    applicable = [rule for rule in rule_results if rule.status != "not_applicable"]
    total_weight = sum(rule.weight for rule in applicable)
    score = round(
        sum(rule.weight * rule.value for rule in applicable) / total_weight,
        3,
    ) if total_weight else 0.0
    maturity_level = _maturity_for_score(score, program.get("levels") or DEFAULT_LEVELS)
    achieved_rank = _level_rank(maturity_level, program.get("levels") or DEFAULT_LEVELS)
    target_rank = _level_rank(target_maturity, program.get("levels") or DEFAULT_LEVELS)
    failed_rules = [rule for rule in applicable if rule.status in {"partial", "fail"}]
    top_gaps = [rule.label for rule in sorted(failed_rules, key=lambda item: (item.value, -item.weight))[:3]]
    status = "on-track" if achieved_rank >= target_rank else "below-target"
    if not applicable:
        status = "missing-program"
    summary = _build_scorecard_summary(
        program_label=program["label"],
        maturity_level=maturity_level,
        target_maturity=target_maturity,
        status=status,
        top_gaps=top_gaps,
    )
    return {
        "repo": repo_name,
        "program": program_key,
        "program_label": program["label"],
        "score": score,
        "maturity_level": maturity_level,
        "target_maturity": target_maturity,
        "status": status,
        "passed_rules": len([rule for rule in applicable if rule.status == "pass"]),
        "applicable_rules": len(applicable),
        "failed_rule_keys": [rule.key for rule in failed_rules],
        "top_gaps": top_gaps,
        "summary": summary,
        "rule_results": [
            {
                "key": rule.key,
                "label": rule.label,
                "status": rule.status,
                "weight": rule.weight,
                "reason": rule.reason,
            }
            for rule in rule_results
        ],
    }


def resolve_program_key(catalog: dict[str, Any], programs: dict[str, dict[str, Any]]) -> str:
    explicit = _normalize_key(catalog.get("maturity_program"))
    if explicit:
        return explicit
    default_program = _normalize_key(catalog.get("catalog_default_maturity_program"))
    if default_program:
        return default_program
    disposition = _normalize_key(catalog.get("intended_disposition"))
    if disposition and disposition in programs:
        return disposition
    return "default"


def resolve_target_maturity(catalog: dict[str, Any], program: dict[str, Any]) -> str:
    target = _normalize_key(catalog.get("target_maturity")) or _normalize_key(catalog.get("catalog_default_target_maturity"))
    levels = {level["key"] for level in program.get("levels") or DEFAULT_LEVELS}
    if target in levels:
        return target
    return _normalize_key(program.get("target_maturity")) or "operating"


def _evaluate_rule(audit: dict[str, Any], catalog: dict[str, Any], rule: dict[str, Any]) -> RuleEvaluation:
    check = rule["check"]
    if check == "dimension_at_least":
        return _evaluate_at_least_rule(
            rule,
            actual=_dimension_score(audit, _safe_text(rule.get("dimension"))),
            summary_label=_safe_text(rule.get("summary_label")) or _safe_text(rule.get("dimension")),
        )
    if check == "lens_at_least":
        lenses = _mapping(audit.get("lenses"))
        actual = _normalize_float(_mapping(lenses.get(_safe_text(rule.get("lens")))).get("score"))
        return _evaluate_at_least_rule(
            rule,
            actual=actual,
            summary_label=_safe_text(rule.get("summary_label")) or _safe_text(rule.get("lens")),
        )
    if check == "security_posture_at_least":
        actual = _normalize_float(_mapping(audit.get("security_posture")).get("score"))
        return _evaluate_at_least_rule(rule, actual=actual, summary_label="security posture")
    if check == "audit_field_at_least":
        field = _safe_text(rule.get("field"))
        actual = _normalize_float(audit.get(field))
        return _evaluate_at_least_rule(rule, actual=actual, summary_label=field)
    if check == "tier_at_least":
        required_tier = _normalize_key(rule.get("tier"))
        current_tier = _normalize_key(audit.get("completeness_tier"))
        if required_tier not in TIER_RANKS:
            return RuleEvaluation(rule["key"], rule["label"], "not_applicable", rule["weight"], 0.0, "Required tier is invalid.")
        passed = TIER_RANKS.get(current_tier, -1) >= TIER_RANKS[required_tier]
        reason = f"{current_tier or 'unknown'} tier {'meets' if passed else 'does not meet'} the {required_tier} bar."
        return RuleEvaluation(rule["key"], rule["label"], "pass" if passed else "fail", rule["weight"], 1.0 if passed else 0.0, reason)
    if check == "flag_absent":
        flag = _safe_text(rule.get("flag"))
        flags = {str(item).strip() for item in audit.get("flags", [])}
        passed = flag not in flags
        return RuleEvaluation(
            rule["key"],
            rule["label"],
            "pass" if passed else "fail",
            rule["weight"],
            1.0 if passed else 0.0,
            f"Flag '{flag}' is {'absent' if passed else 'present'}.",
        )
    if check == "activity_days_at_most":
        actual = _activity_days(audit)
        threshold = _normalize_float(rule.get("threshold"))
        partial_threshold = _normalize_float(rule.get("partial_threshold"))
        if threshold is None or actual is None:
            return RuleEvaluation(rule["key"], rule["label"], "not_applicable", rule["weight"], 0.0, "No activity age is available.")
        if actual <= threshold:
            return RuleEvaluation(rule["key"], rule["label"], "pass", rule["weight"], 1.0, f"Activity is fresh at {actual} days.")
        if partial_threshold is not None and actual <= partial_threshold:
            return RuleEvaluation(rule["key"], rule["label"], "partial", rule["weight"], 0.5, f"Activity is aging at {actual} days.")
        return RuleEvaluation(rule["key"], rule["label"], "fail", rule["weight"], 0.0, f"Activity is too old at {actual} days.")
    if check == "catalog_field_in":
        field = _safe_text(rule.get("catalog_field"))
        values = set(rule.get("values") or [])
        actual = _normalize_key(catalog.get(field))
        if not values:
            return RuleEvaluation(rule["key"], rule["label"], "not_applicable", rule["weight"], 0.0, "No catalog values are configured.")
        if not actual:
            return RuleEvaluation(rule["key"], rule["label"], "not_applicable", rule["weight"], 0.0, f"Catalog field '{field}' is empty.")
        passed = actual in values
        return RuleEvaluation(
            rule["key"],
            rule["label"],
            "pass" if passed else "fail",
            rule["weight"],
            1.0 if passed else 0.0,
            f"Catalog field '{field}' is {actual}.",
        )
    return RuleEvaluation(rule["key"], rule["label"], "not_applicable", rule["weight"], 0.0, "Rule is unsupported.")


def _evaluate_at_least_rule(rule: dict[str, Any], *, actual: float | None, summary_label: str) -> RuleEvaluation:
    threshold = _normalize_float(rule.get("threshold"))
    partial_threshold = _normalize_float(rule.get("partial_threshold"))
    if threshold is None or actual is None:
        return RuleEvaluation(rule["key"], rule["label"], "not_applicable", rule["weight"], 0.0, f"No {summary_label} value is available.")
    if actual >= threshold:
        return RuleEvaluation(rule["key"], rule["label"], "pass", rule["weight"], 1.0, f"{summary_label} is {actual:.2f}.")
    if partial_threshold is not None and actual >= partial_threshold:
        return RuleEvaluation(rule["key"], rule["label"], "partial", rule["weight"], 0.5, f"{summary_label} is only {actual:.2f}.")
    return RuleEvaluation(rule["key"], rule["label"], "fail", rule["weight"], 0.0, f"{summary_label} is only {actual:.2f}.")


def _dimension_score(audit: dict[str, Any], dimension: str) -> float | None:
    for result in audit.get("analyzer_results", []):
        if _safe_text(result.get("dimension")) == dimension:
            return _normalize_float(result.get("score"))
    return None


def _activity_days(audit: dict[str, Any]) -> int | None:
    for result in audit.get("analyzer_results", []):
        if _safe_text(result.get("dimension")) != "activity":
            continue
        details = _mapping(result.get("details"))
        days = details.get("days_since_push")
        if isinstance(days, int):
            return days
    metadata = _mapping(audit.get("metadata"))
    pushed_at = _safe_text(metadata.get("pushed_at"))
    if not pushed_at:
        return None
    try:
        pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - pushed_dt).days)


def _maturity_for_score(score: float, levels: list[dict[str, Any]]) -> str:
    chosen = levels[0]["key"]
    for level in levels:
        if score >= float(level.get("threshold", 0.0) or 0.0):
            chosen = level["key"]
    return chosen


def _level_rank(level_key: str, levels: list[dict[str, Any]]) -> int:
    for index, level in enumerate(levels):
        if level["key"] == level_key:
            return index
    return -1


def _build_scorecard_summary(
    *,
    program_label: str,
    maturity_level: str,
    target_maturity: str,
    status: str,
    top_gaps: list[str],
) -> str:
    level_label = _labelize(maturity_level)
    target_label = _labelize(target_maturity)
    if status == "missing-program":
        return f"{program_label} scorecard is missing or invalid."
    if status == "on-track":
        return f"{program_label} is currently at {level_label} and on track for the {target_label} target."
    if top_gaps:
        gaps = ", ".join(top_gaps[:3])
        return f"{program_label} is at {level_label} and still below the {target_label} target because {gaps.lower()} are behind."
    return f"{program_label} is at {level_label} and still below the {target_label} target."


def build_scorecards_summary(scorecard_results: list[dict[str, Any]], scorecards_data: dict[str, Any]) -> dict[str, Any]:
    by_program: dict[str, int] = {}
    by_maturity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    below_target = []
    for result in scorecard_results:
        by_program[result.get("program", "default")] = by_program.get(result.get("program", "default"), 0) + 1
        by_maturity[result.get("maturity_level", "missing-basics")] = by_maturity.get(result.get("maturity_level", "missing-basics"), 0) + 1
        by_status[result.get("status", "missing-program")] = by_status.get(result.get("status", "missing-program"), 0) + 1
        if result.get("status") == "below-target":
            below_target.append(
                {
                    "repo": result.get("repo", ""),
                    "program": result.get("program_label", result.get("program", "default")),
                    "summary": result.get("summary", ""),
                }
            )
    below_target = [item for item in below_target if item.get("repo")][:5]
    summary = (
        f"{by_status.get('on-track', 0)} repo(s) are on track, "
        f"{by_status.get('below-target', 0)} are below target, "
        f"and {by_status.get('missing-program', 0)} are missing a valid program."
    )
    if scorecards_data.get("errors"):
        summary += " Some scorecard config errors were detected."
    return {
        "scorecards_path": scorecards_data.get("path", ""),
        "program_counts": by_program,
        "maturity_level_counts": by_maturity,
        "status_counts": by_status,
        "top_below_target_repos": below_target,
        "summary": summary,
        "errors": list(scorecards_data.get("errors") or []),
        "warnings": list(scorecards_data.get("warnings") or []),
        "scorecards_exists": bool(scorecards_data.get("exists")),
    }


def build_scorecard_programs_summary(scorecards_data: dict[str, Any]) -> dict[str, Any]:
    programs = scorecards_data.get("programs") or {}
    return {
        key: {
            "label": program.get("label", _labelize(key)),
            "description": program.get("description", ""),
            "target_maturity": program.get("target_maturity", ""),
            "levels": [level.get("key", "") for level in program.get("levels", [])],
            "rule_count": len(program.get("rules", [])),
        }
        for key, program in programs.items()
    }
