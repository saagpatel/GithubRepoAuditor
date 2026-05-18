"""Helpers for Score Explainer workbook content."""

from __future__ import annotations

from typing import Any

SCORE_EXPLAINER_HEADERS = ["Dimension", "Weight", "What It Measures", "How to Improve"]

DIMENSION_INFO = {
    "testing": (
        "Test directories, framework, test file count",
        "Add test/ with pytest/jest/vitest configured",
    ),
    "code_quality": (
        "Entry points, TODO density, types, commit quality",
        "Add main entry point, reduce TODOs",
    ),
    "activity": (
        "Push recency, commit count, releases, bus factor",
        "Push regularly, tag releases",
    ),
    "readme": (
        "Exists, description, install instructions, examples",
        "Add usage section with code blocks",
    ),
    "structure": (
        ".gitignore, source dirs, config files, LICENSE",
        "Add .gitignore + LICENSE + package manifest",
    ),
    "cicd": ("GitHub Actions, CI configs, build scripts", "Add .github/workflows/ci.yml"),
    "dependencies": (
        "Manifest + lockfile, dep count, libyears",
        "Add lockfile alongside manifest",
    ),
    "build_readiness": (
        "Docker, Makefile, .env.example, deploy configs",
        "Add Dockerfile or Makefile",
    ),
    "community_profile": ("LICENSE, CONTRIBUTING, CODE_OF_CONDUCT", "Add CONTRIBUTING.md"),
    "documentation": (
        "docs/ dir, CHANGELOG, comment density",
        "Add docs/ folder or CHANGELOG.md",
    ),
}


def build_score_explainer_content(
    *,
    weights: dict[str, float],
    grade_thresholds: list[tuple[float, str]],
    completeness_tiers: list[tuple[str, float]],
) -> dict[str, Any]:
    return {
        "dimension_rows": [
            [
                dimension,
                f"{weight:.0%}",
                DIMENSION_INFO.get(dimension, ("", ""))[0],
                DIMENSION_INFO.get(dimension, ("", ""))[1],
            ]
            for dimension, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
        ],
        "grade_rows": [[grade, f">= {threshold:.0%}"] for threshold, grade in grade_thresholds],
        "tier_rows": [
            [tier_name.capitalize(), f">= {threshold:.0%}"]
            for tier_name, threshold in completeness_tiers
        ],
    }


def write_score_explainer_sections(
    ws,
    content: dict[str, Any],
    *,
    title_font,
    section_font,
    style_header_row,
    style_data_cell,
    color_grade_cell,
    color_tier_cell,
) -> int:
    ws.merge_cells("A1:D1")
    ws["A1"].value = "Scoring System Reference"
    ws["A1"].font = title_font

    ws.cell(row=3, column=1, value="Dimension Weights").font = section_font
    for col, header in enumerate(SCORE_EXPLAINER_HEADERS, 1):
        ws.cell(row=4, column=col, value=header)
    style_header_row(ws, 4, len(SCORE_EXPLAINER_HEADERS))
    ws.freeze_panes = "A5"

    row = 5
    for values in content["dimension_rows"]:
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value))
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Grade Thresholds").font = section_font
    row += 1
    for grade, threshold_text in content["grade_rows"]:
        ws.cell(row=row, column=1, value=grade)
        ws.cell(row=row, column=2, value=threshold_text)
        color_grade_cell(ws.cell(row=row, column=1), grade)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Tier Thresholds").font = section_font
    row += 1
    for tier_name, threshold_text in content["tier_rows"]:
        ws.cell(row=row, column=1, value=tier_name)
        ws.cell(row=row, column=2, value=threshold_text)
        color_tier_cell(ws.cell(row=row, column=1), tier_name.lower())
        row += 1

    return row


def build_score_explainer_sheet(
    wb,
    *,
    weights: dict[str, float],
    grade_thresholds: list[tuple[float, str]],
    completeness_tiers: list[tuple[str, float]],
    get_or_create_sheet,
    build_score_explainer_content_fn,
    write_score_explainer_sections_fn,
    title_font,
    section_font,
    style_header_row,
    style_data_cell,
    color_grade_cell,
    color_tier_cell,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Score Explainer")
    ws.sheet_properties.tabColor = "37474F"
    content = build_score_explainer_content_fn(
        weights=weights,
        grade_thresholds=grade_thresholds,
        completeness_tiers=completeness_tiers,
    )
    row = write_score_explainer_sections_fn(
        ws,
        content,
        title_font=title_font,
        section_font=section_font,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        color_grade_cell=color_grade_cell,
        color_tier_cell=color_tier_cell,
    )

    auto_width(ws, 4, row)
