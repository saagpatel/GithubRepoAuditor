from __future__ import annotations

import hashlib
import json


BASELINE_SIGNATURE_FIELDS = (
    "username",
    "scoring_profile",
    "skip_forks",
    "skip_archived",
    "scorecard",
    "security_offline",
)
BASELINE_CONTEXT_FIELDS = BASELINE_SIGNATURE_FIELDS + ("portfolio_baseline_size",)
FIELD_LABELS = {
    "username": "username",
    "scoring_profile": "scoring profile",
    "skip_forks": "skip forks",
    "skip_archived": "skip archived",
    "scorecard": "scorecard",
    "security_offline": "security offline",
    "portfolio_baseline_size": "portfolio baseline size",
}


def normalize_scoring_profile(profile_name: str | None) -> str:
    return profile_name or "default"


def _compute_signature(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_filter_signature(*, username: str, scoring_profile: str, skip_forks: bool, skip_archived: bool, scorecard: bool, security_offline: bool) -> str:
    payload = {
        "username": username,
        "scoring_profile": normalize_scoring_profile(scoring_profile),
        "skip_forks": bool(skip_forks),
        "skip_archived": bool(skip_archived),
        "scorecard": bool(scorecard),
        "security_offline": bool(security_offline),
    }
    return _compute_signature(payload)


def build_filter_signature_from_args(args, *, scoring_profile: str) -> str:
    return build_filter_signature(
        username=getattr(args, "username", ""),
        scoring_profile=scoring_profile,
        skip_forks=bool(getattr(args, "skip_forks", False)),
        skip_archived=bool(getattr(args, "skip_archived", False)),
        scorecard=bool(getattr(args, "scorecard", False)),
        security_offline=bool(getattr(args, "security_offline", False)),
    )


def build_baseline_context(
    *,
    username: str,
    scoring_profile: str,
    skip_forks: bool,
    skip_archived: bool,
    scorecard: bool,
    security_offline: bool,
    portfolio_baseline_size: int,
) -> dict:
    context = {
        "username": username,
        "scoring_profile": normalize_scoring_profile(scoring_profile),
        "skip_forks": bool(skip_forks),
        "skip_archived": bool(skip_archived),
        "scorecard": bool(scorecard),
        "security_offline": bool(security_offline),
        "portfolio_baseline_size": int(portfolio_baseline_size),
    }
    context["baseline_signature"] = _compute_signature(context)
    return context


def build_baseline_context_from_args(args, *, scoring_profile: str, portfolio_baseline_size: int) -> dict:
    return build_baseline_context(
        username=getattr(args, "username", ""),
        scoring_profile=scoring_profile,
        skip_forks=bool(getattr(args, "skip_forks", False)),
        skip_archived=bool(getattr(args, "skip_archived", False)),
        scorecard=bool(getattr(args, "scorecard", False)),
        security_offline=bool(getattr(args, "security_offline", False)),
        portfolio_baseline_size=portfolio_baseline_size,
    )


def build_requested_baseline_context(args, *, scoring_profile: str) -> dict:
    return {
        "username": getattr(args, "username", ""),
        "scoring_profile": normalize_scoring_profile(scoring_profile),
        "skip_forks": bool(getattr(args, "skip_forks", False)),
        "skip_archived": bool(getattr(args, "skip_archived", False)),
        "scorecard": bool(getattr(args, "scorecard", False)),
        "security_offline": bool(getattr(args, "security_offline", False)),
        "filter_signature": build_filter_signature_from_args(args, scoring_profile=scoring_profile),
    }


def build_watch_state(args, *, scoring_profile: str, portfolio_baseline_size: int, review_sync: str = "local") -> dict:
    baseline_context = build_baseline_context_from_args(
        args,
        scoring_profile=scoring_profile,
        portfolio_baseline_size=portfolio_baseline_size,
    )
    return {
        "review_sync": review_sync,
        "filter_signature": build_filter_signature_from_args(args, scoring_profile=scoring_profile),
        "baseline_signature": baseline_context["baseline_signature"],
        "baseline_context": baseline_context,
    }


def extract_baseline_context(report_data: dict | None) -> dict:
    if not report_data:
        return {}

    context = dict(report_data.get("baseline_context") or {})
    if not context:
        return {}

    if "scoring_profile" in context:
        context["scoring_profile"] = normalize_scoring_profile(context.get("scoring_profile"))
    if "baseline_signature" not in context and report_data.get("baseline_signature"):
        context["baseline_signature"] = report_data.get("baseline_signature")
    return context


def compare_baseline_context(expected: dict, actual: dict, *, include_size: bool = True) -> list[dict]:
    fields = BASELINE_CONTEXT_FIELDS if include_size else BASELINE_SIGNATURE_FIELDS
    mismatches: list[dict] = []
    for field in fields:
        if field not in actual:
            mismatches.append(
                {
                    "field": field,
                    "label": FIELD_LABELS[field],
                    "expected": expected.get(field),
                    "actual": None,
                    "reason": "missing",
                }
            )
            continue
        if expected.get(field) != actual.get(field):
            mismatches.append(
                {
                    "field": field,
                    "label": FIELD_LABELS[field],
                    "expected": expected.get(field),
                    "actual": actual.get(field),
                    "reason": "different",
                }
            )
    return mismatches


def format_mismatch_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value in (None, ""):
        return "missing"
    return str(value)

