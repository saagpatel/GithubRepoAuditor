"""Generate golden input/output cases from the REAL GHRA decision functions.

Runs the actual Python implementations across exhaustive/sampled input grids and
writes goldens.json. The Node runner (run_golden.cjs) replays every case through
the JS port in ../verdict_core.js and diffs exact equality.

Usage:  uv run python fable-explore/verdict-machine/golden/generate_goldens.py
        (from the GithubRepoAuditor repo root)
"""

from __future__ import annotations

import itertools
import json
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from src.portfolio_context_contract import analyze_project_context  # noqa: E402
from src.portfolio_pathing import build_operating_path_entry  # noqa: E402
from src.portfolio_risk import STRATEGIC_REPOS, build_risk_entry  # noqa: E402
from src.portfolio_truth_reconcile import (  # noqa: E402
    _activity_status_for,
    _attention_state_for,
    _registry_status_for,
)

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
STRATEGIC_NAME = next(
    iter(sorted(STRATEGIC_REPOS))
)  # any member; JS only sees a boolean
SYNTHETIC_NAME = "synthetic-repo"

SECTION_HEADINGS = {
    "project_summary": "What This Project Is",
    "current_state": "Current State",
    "stack": "Stack",
    "run_instructions": "How To Run",
    "known_risks": "Known Risks",
    "next_recommended_move": "Next Recommended Move",
}
SECTION_ORDER = list(SECTION_HEADINGS)
FILLER = (
    "This paragraph carries genuinely meaningful content for the section so the "
    "contract parser treats it as substantive rather than boilerplate filler text. "
    "It describes concrete decisions, states, and commands in enough detail to pass."
)


def activity_cases() -> list[dict]:
    cases = []
    for days in [None, 0, 1, 7, 13, 14, 15, 29, 30, 31, 90, 400]:
        for lifecycle in ["", "archived", "experimental"]:
            for gh_archived in [False, True]:
                last = None if days is None else NOW - timedelta(days=days)
                expected = _activity_status_for(
                    last, lifecycle, now=NOW, github_archived=gh_archived
                )
                cases.append(
                    {
                        "input": {
                            "lastActivityDays": days,
                            "lifecycleState": lifecycle,
                            "githubArchived": gh_archived,
                        },
                        "expected": expected,
                        "expected_registry": _registry_status_for(expected),
                    }
                )
    return cases


def context_cases() -> list[dict]:
    support_variants = [
        [],
        ["NOTES.md"],
        ["STATUS.md"],
        ["ROADMAP.md", "NOTES.md"],
        ["HANDOFF.md"],
        ["HANDOFF.md", "ROADMAP.md"],
        ["DISCOVERY-SUMMARY.md", "IMPLEMENTATION-ROADMAP.md"],
        ["STATUS.md", "PLAN.md", "NOTES.md"],
    ]
    cases = []
    for bits in itertools.product([False, True], repeat=6):
        sections = dict(zip(SECTION_ORDER, bits))
        for primary_exists, has_readme in [
            (True, False),
            (False, True),
            (True, True),
            (False, False),
        ]:
            for support in support_variants:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)
                    body_lines: list[str] = []
                    for field, present in sections.items():
                        if present:
                            body_lines.append(f"## {SECTION_HEADINGS[field]}")
                            body_lines.append(FILLER)
                            body_lines.append("")
                    body = "\n".join(body_lines)

                    context_files = list(support)
                    readme_text = ""
                    if primary_exists:
                        (tmp_path / "AGENTS.md").write_text(body, encoding="utf-8")
                        context_files.append("AGENTS.md")
                        if has_readme:
                            # README exists but contributes nothing: starts with a
                            # non-alias heading, no lead paragraph.
                            (tmp_path / "README.md").write_text(
                                "## License\nMIT.\n", encoding="utf-8"
                            )
                    elif has_readme:
                        # An empty README is "no README" to the contract
                        # (has_readme = bool(readme_text.strip())). When no sections
                        # are selected, still give the README neutral, non-alias
                        # content so the file genuinely exists in contract terms.
                        readme_body = body if body.strip() else "## License\nMIT.\n"
                        (tmp_path / "README.md").write_text(
                            readme_body, encoding="utf-8"
                        )

                    analysis = analyze_project_context(
                        tmp_path, context_files, readme_text=readme_text
                    )
                    # Sanity: generated files must reproduce the intended section
                    # presence, otherwise the case tests the wrong thing.
                    derived = {
                        "project_summary": analysis.project_summary_present,
                        "current_state": analysis.current_state_present,
                        "stack": analysis.stack_present,
                        "run_instructions": analysis.run_instructions_present,
                        "known_risks": analysis.known_risks_present,
                        "next_recommended_move": analysis.next_recommended_move_present,
                    }
                    effective_sections = (
                        sections
                        if (primary_exists or has_readme)
                        else dict.fromkeys(SECTION_ORDER, False)
                    )
                    if derived != effective_sections:
                        raise AssertionError(
                            f"fixture drift: wanted {effective_sections} got {derived} "
                            f"(primary={primary_exists}, readme={has_readme})"
                        )
                    cases.append(
                        {
                            "input": {
                                "primaryExists": primary_exists,
                                "hasReadme": has_readme,
                                "sections": derived,
                                "supportingFileNames": context_files,
                                "primaryContextFile": "AGENTS.md",
                            },
                            "expected": {
                                "context_quality": analysis.context_quality,
                                "missing_fields": analysis.missing_fields,
                                "supporting_context_files": [
                                    Path(item).name
                                    for item in analysis.supporting_context_files
                                ],
                            },
                        }
                    )
    return cases


def pathing_cases() -> list[dict]:
    grid = itertools.product(
        [
            "",
            "maintain",
            "finish",
            "archive",
            "experiment",
            "weird-value",
        ],  # operating_path
        ["", "maintain", "experiment"],  # intended_disposition
        ["", "default", "finish", "maintain"],  # maturity_program
        [False, True],  # has_explicit_entry
        [
            "",
            "none",
            "boilerplate",
            "minimum-viable",
            "standard",
            "full",
        ],  # context_quality
        [False, True],  # archived
        ["", "active", "archived", "parked"],  # registry_status
    )
    cases = []
    for op, disp, prog, explicit, ctx, archived, registry in grid:
        entry = {
            "operating_path": op,
            "intended_disposition": disp,
            "maturity_program": prog,
            "has_explicit_entry": explicit,
        }
        result = build_operating_path_entry(
            entry,
            context_quality=ctx,
            archived=archived,
            registry_status=registry,
        )
        cases.append(
            {
                "input": {
                    "entry": entry,
                    "options": {
                        "contextQuality": ctx,
                        "archived": archived,
                        "registryStatus": registry,
                    },
                },
                "expected": {
                    "operating_path": result["operating_path"],
                    "operating_path_source": result["operating_path_source"],
                    "path_override": result["path_override"],
                    "path_confidence": result["path_confidence"],
                    "path_rationale": result["path_rationale"],
                },
            }
        )
    # Extra matrix for the keyword args the live pipeline defaults but the
    # function supports (explainer exposes them under "advanced").
    extra_grid = itertools.product(
        ["", "maintain", "finish"],
        [False, True],
        ["minimum-viable", "standard"],
        ["", "needs-review"],
        ["", "abandoned", "skeleton", "shipped"],
        ["", "needs-skepticism", "insufficient-data", "trusted"],
    )
    for op, explicit, ctx, intent, tier, dq in extra_grid:
        entry = {
            "operating_path": op,
            "intended_disposition": "",
            "maturity_program": "",
            "has_explicit_entry": explicit,
        }
        result = build_operating_path_entry(
            entry,
            context_quality=ctx,
            intent_alignment=intent,
            archived=False,
            registry_status="active",
            completeness_tier=tier,
            decision_quality_status=dq,
        )
        cases.append(
            {
                "input": {
                    "entry": entry,
                    "options": {
                        "contextQuality": ctx,
                        "intentAlignment": intent,
                        "archived": False,
                        "registryStatus": "active",
                        "completenessTier": tier,
                        "decisionQualityStatus": dq,
                    },
                },
                "expected": {
                    "operating_path": result["operating_path"],
                    "operating_path_source": result["operating_path_source"],
                    "path_override": result["path_override"],
                    "path_confidence": result["path_confidence"],
                    "path_rationale": result["path_rationale"],
                },
            }
        )
    return cases


def risk_cases() -> list[dict]:
    full_grid = list(
        itertools.product(
            [SYNTHETIC_NAME, STRATEGIC_NAME],  # display_name → isStrategic
            ["", "maintain", "finish", "archive", "experiment"],  # operating_path
            ["", "investigate"],  # path_override
            [
                "none",
                "boilerplate",
                "minimum-viable",
                "standard",
                "full",
            ],  # context_quality
            ["active", "recent", "stale", "archived"],  # activity_status
            ["active", "recent", "parked", "archived"],  # registry_status
            ["", "medium", "high", "critical"],  # criticality
            ["", "basic", "full"],  # doctor_standard
            [False, True],  # known_risks_present
            [False, True],  # run_instructions_present
            [0, 2],  # high alerts
            [0, 1],  # critical alerts
        )
    )
    rng = random.Random(20260711)
    sampled = rng.sample(full_grid, 6000)
    # Hand-picked edges guaranteed present.
    edges = [
        (
            SYNTHETIC_NAME,
            "maintain",
            "",
            "standard",
            "stale",
            "parked",
            "",
            "",
            True,
            True,
            0,
            0,
        ),
        (
            SYNTHETIC_NAME,
            "finish",
            "",
            "standard",
            "stale",
            "parked",
            "",
            "",
            True,
            True,
            0,
            0,
        ),
        (
            SYNTHETIC_NAME,
            "",
            "investigate",
            "none",
            "active",
            "active",
            "high",
            "",
            False,
            False,
            0,
            0,
        ),
        (
            SYNTHETIC_NAME,
            "maintain",
            "",
            "full",
            "active",
            "active",
            "",
            "",
            True,
            True,
            0,
            1,
        ),
        (
            STRATEGIC_NAME,
            "maintain",
            "",
            "full",
            "active",
            "active",
            "high",
            "",
            True,
            True,
            0,
            0,
        ),
        (
            SYNTHETIC_NAME,
            "archive",
            "",
            "none",
            "active",
            "active",
            "critical",
            "",
            False,
            False,
            9,
            9,
        ),
    ]
    cases = []
    for combo in edges + sampled:
        (
            name,
            op,
            override,
            ctx,
            act,
            reg,
            crit,
            doctor,
            known,
            run,
            high,
            critical,
        ) = combo
        result = build_risk_entry(
            display_name=name,
            operating_path=op,
            path_override=override,
            context_quality=ctx,
            activity_status=act,
            registry_status=reg,
            criticality=crit,
            doctor_standard=doctor,
            known_risks_present=known,
            run_instructions_present=run,
            security_high_alerts=high,
            security_critical_alerts=critical,
        )
        cases.append(
            {
                "input": {
                    "isStrategic": name in STRATEGIC_REPOS,
                    "operatingPath": op,
                    "pathOverride": override,
                    "contextQuality": ctx,
                    "activityStatus": act,
                    "registryStatus": reg,
                    "criticality": crit,
                    "doctorStandard": doctor,
                    "knownRisksPresent": known,
                    "runInstructionsPresent": run,
                    "securityHighAlerts": high,
                    "securityCriticalAlerts": critical,
                },
                "expected": result,
            }
        )
    return cases


def attention_cases() -> list[dict]:
    grid = itertools.product(
        ["active", "recent", "parked", "archived"],  # registry_status
        ["", "archived", "experimental"],  # lifecycle_state
        ["", "maintain", "finish", "archive", "experiment"],  # operating_path
        ["", "experiment", "maintain"],  # intended_disposition
        ["", "infrastructure", "commercial", "personal"],  # category
        ["", "investigate"],  # path_override
        [False, True],  # security_risk
        [False, True],  # github_archived
    )
    cases = []
    for reg, lifecycle, op, disp, cat, override, sec, gh in grid:
        expected = _attention_state_for(
            registry_status=reg,
            lifecycle_state=lifecycle,
            operating_path=op,
            intended_disposition=disp,
            category=cat,
            path_override=override,
            risk_entry={"security_risk": sec},
            github_archived=gh,
        )
        cases.append(
            {
                "input": {
                    "registryStatus": reg,
                    "lifecycleState": lifecycle,
                    "operatingPath": op,
                    "intendedDisposition": disp,
                    "category": cat,
                    "pathOverride": override,
                    "riskEntry": {"security_risk": sec},
                    "githubArchived": gh,
                },
                "expected": expected,
            }
        )
    return cases


def main() -> None:
    goldens = {
        "generated_from": "GithubRepoAuditor src @ golden-generation time",
        "activity": activity_cases(),
        "context": context_cases(),
        "pathing": pathing_cases(),
        "risk": risk_cases(),
        "attention": attention_cases(),
    }
    out = Path(__file__).parent / "goldens.json"
    out.write_text(json.dumps(goldens, indent=1), encoding="utf-8")
    counts = {k: len(v) for k, v in goldens.items() if isinstance(v, list)}
    print(f"wrote {out}")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
