"""Typed contracts for the weekly-story and risk seams.

These are the typed forms of the `weekly_story_v1` and risk-posture contracts
documented in `docs/architecture.md`, adopted per the 2026-07-10 elegance
review to put types at the enrichment boundary. They describe the shapes
produced by `src/weekly_packaging.py` (`_build_weekly_story_v1` and its
evidence-item helpers) and `src/report_enrichment.py`
(`build_risk_lookup` / `_extract_risk_posture`); they are annotations only
and introduce no runtime behavior.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class WeeklyStoryEvidenceItem(TypedDict):
    label: str
    summary: str
    kind: str
    safe_posture: str
    command_hint: NotRequired[str]


class WeeklyStorySection(TypedDict):
    id: str
    label: str
    state: str
    headline: str
    next_step: str
    next_label: str
    reason_codes: list[str]
    evidence_items: list[WeeklyStoryEvidenceItem]


class WeeklyStoryV1(TypedDict):
    version: int
    headline: str
    decision: str
    why_this_week: str
    next_step: str
    section_order: list[str]
    sections: list[WeeklyStorySection]


class RiskLookupEntry(TypedDict):
    risk_tier: str
    risk_summary: str


class TopElevatedEntry(TypedDict):
    repo: str
    risk_summary: str


class RiskPosture(TypedDict):
    elevated_count: int
    moderate_count: int
    baseline_count: int
    deferred_count: int
    tier_counts: dict[str, int]
    top_elevated: list[TopElevatedEntry]
