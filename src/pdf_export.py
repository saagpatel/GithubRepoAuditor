"""PDF export for GitHub Repo Auditor.

Generates a multi-section PDF report from audit data using fpdf2.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# ── FPDF subclass ──────────────────────────────────────────────────────

def _make_pdf_class():
    """Factory to defer FPDF import so ImportError is handled gracefully."""
    try:
        from fpdf import FPDF
    except ImportError:
        return None

    class AuditPDF(FPDF):
        _username: str = ""
        _date: str = ""

        def header(self) -> None:
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 8, f"GitHub Portfolio Audit - {self._username}  |  {self._date}", align="R")
            self.ln(2)
            self.set_draw_color(200, 200, 200)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(4)
            self.set_text_color(0, 0, 0)

        def footer(self) -> None:
            self.set_y(-14)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, f"Page {self.page_no()}", align="C")
            self.set_text_color(0, 0, 0)

    return AuditPDF


# ── Colour helpers ─────────────────────────────────────────────────────

_GRADE_COLOURS: dict[str, tuple[int, int, int]] = {
    "A+": (0, 150, 80),
    "A":  (0, 160, 90),
    "B":  (80, 160, 40),
    "C":  (200, 160, 0),
    "D":  (220, 100, 0),
    "F":  (200, 40, 40),
}

_TIER_COLOURS: dict[str, tuple[int, int, int]] = {
    "shipped":    (0, 150, 80),
    "functional": (80, 160, 40),
    "wip":        (200, 160, 0),
    "skeleton":   (220, 100, 0),
    "abandoned":  (180, 60, 60),
}


def _grade_colour(grade: str) -> tuple[int, int, int]:
    letter = grade[0] if grade else "F"
    for key, colour in _GRADE_COLOURS.items():
        if key == grade:
            return colour
    for key, colour in _GRADE_COLOURS.items():
        if key[0] == letter:
            return colour
    return (150, 150, 150)


def _tier_colour(tier: str) -> tuple[int, int, int]:
    return _TIER_COLOURS.get(tier.lower(), (150, 150, 150))


# ── Section builders ───────────────────────────────────────────────────

def _title_page(pdf, data: dict, date_str: str) -> None:
    pdf.add_page()
    pdf.ln(20)

    # Large title
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 14, "GitHub Portfolio Audit", align="C")
    pdf.ln(12)

    # Username
    pdf.set_font("Helvetica", "", 18)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 10, f"@{data.get('username', '')}", align="C")
    pdf.ln(8)

    # Date
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, date_str, align="C")
    pdf.ln(20)

    # Divider
    pdf.set_draw_color(220, 220, 220)
    pdf.set_line_width(0.5)
    mid = pdf.w / 2
    pdf.line(mid - 40, pdf.get_y(), mid + 40, pdf.get_y())
    pdf.ln(20)

    # Grade + score box
    grade = data.get("portfolio_grade", "-")
    avg = data.get("average_score", 0)
    r, g, b = _grade_colour(grade)

    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 48)
    box_w = 60
    box_h = 30
    x = (pdf.w - box_w) / 2
    pdf.set_x(x)
    pdf.cell(box_w, box_h, grade, align="C", fill=True)
    pdf.ln(12)

    pdf.set_text_color(60, 60, 60)
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 8, f"Portfolio Grade    Average Score: {avg:.0%}", align="C")
    pdf.ln(6)

    # Repo count
    n_audits = len(data.get("audits", []))
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, f"{n_audits} repositories audited", align="C")


def _exec_summary(pdf, data: dict) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Executive Summary")
    pdf.ln(12)

    # Tier distribution
    tier_dist: dict[str, int] = data.get("tier_distribution", {})
    tier_order = ["shipped", "functional", "wip", "skeleton", "abandoned"]

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 8, "Tier Distribution")
    pdf.ln(8)

    bar_area_w = pdf.w - pdf.l_margin - pdf.r_margin
    total = sum(tier_dist.values()) or 1

    for tier in tier_order:
        count = tier_dist.get(tier, 0)
        if count == 0:
            continue
        r, g, b = _tier_colour(tier)
        label = f"{tier.capitalize():<12} {count:>3}"
        pct = count / total
        bar_w = max(2, pct * (bar_area_w - 60))

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(60, 7, label)
        pdf.set_fill_color(r, g, b)
        pdf.cell(bar_w, 7, "", fill=True)
        pdf.cell(12, 7, f"{pct:.0%}", align="R")
        pdf.ln(8)

    pdf.ln(8)

    # Top 5 repos
    audits = data.get("audits", [])
    top5 = sorted(audits, key=lambda a: a.get("overall_score", 0), reverse=True)[:5]
    if top5:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 8, "Top 5 Repositories")
        pdf.ln(8)

        col_widths = [70, 20, 20, 30, 30]
        headers = ["Repository", "Grade", "Score", "Tier", "Language"]
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(245, 245, 245)
        pdf.set_text_color(40, 40, 40)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, 8, h, border="B", fill=True)
        pdf.ln()

        for audit in top5:
            meta = audit.get("metadata", {})
            grade = audit.get("grade", "-")
            score = audit.get("overall_score", 0)
            tier = audit.get("completeness_tier", "-")
            lang = (meta.get("language") or "-")[:12]
            name = meta.get("name", "-")[:30]

            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(col_widths[0], 7, name)

            gr, gg, gb = _grade_colour(grade)
            pdf.set_text_color(gr, gg, gb)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col_widths[1], 7, grade)

            pdf.set_text_color(40, 40, 40)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(col_widths[2], 7, f"{score:.0%}")
            pdf.cell(col_widths[3], 7, tier.capitalize())
            pdf.cell(col_widths[4], 7, lang)
            pdf.ln()


def _repos_table(pdf, data: dict) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "All Repositories")
    pdf.ln(12)

    col_widths = [65, 20, 20, 30, 35]
    headers = ["Repository", "Grade", "Score", "Tier", "Language"]

    def _header_row() -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(50, 50, 70)
        pdf.set_text_color(255, 255, 255)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, 8, h, fill=True)
        pdf.ln()

    _header_row()

    audits = sorted(
        data.get("audits", []),
        key=lambda a: a.get("overall_score", 0),
        reverse=True,
    )
    for i, audit in enumerate(audits):
        # New page with header if near bottom
        if pdf.get_y() > pdf.h - 30:
            pdf.add_page()
            _header_row()

        meta = audit.get("metadata", {})
        grade = audit.get("grade", "-")
        score = audit.get("overall_score", 0)
        tier = audit.get("completeness_tier", "-")
        lang = (meta.get("language") or "-")[:14]
        name = meta.get("name", "-")[:32]

        fill = i % 2 == 0
        if fill:
            pdf.set_fill_color(248, 248, 252)
        else:
            pdf.set_fill_color(255, 255, 255)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(col_widths[0], 7, name, fill=fill)

        gr, gg, gb = _grade_colour(grade)
        pdf.set_text_color(gr, gg, gb)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[1], 7, grade, fill=fill)

        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[2], 7, f"{score:.0%}", fill=fill)
        pdf.cell(col_widths[3], 7, tier.capitalize(), fill=fill)
        pdf.cell(col_widths[4], 7, lang, fill=fill)
        pdf.ln()


def _quick_wins(pdf, data: dict) -> None:
    backlog: list[dict] = data.get("action_backlog", [])
    if not backlog:
        return

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Quick Wins")
    pdf.ln(12)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, "High-impact actions to raise your portfolio score.")
    pdf.ln(10)

    _PRIORITY_COLOURS = {
        "high":   (200, 40, 40),
        "medium": (200, 140, 0),
        "low":    (100, 160, 60),
    }

    for item in backlog[:10]:
        repo = item.get("repo", "-")
        action = item.get("action", "-")
        priority = str(item.get("priority", "medium")).lower()
        pr, pg, pb = _PRIORITY_COLOURS.get(priority, (120, 120, 120))

        # Bullet dot
        pdf.set_fill_color(pr, pg, pb)
        pdf.ellipse(pdf.l_margin, pdf.get_y() + 2, 4, 4, style="F")

        pdf.set_x(pdf.l_margin + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(40, 7, repo)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, action)
        pdf.ln(8)


def _grade_chart(pdf, data: dict) -> None:
    """Simple bar chart of grade distribution using rect()."""
    audits = data.get("audits", [])
    if not audits:
        return

    grade_counts: dict[str, int] = {}
    for audit in audits:
        g = (audit.get("grade") or "F")[0]  # normalise to letter only
        grade_counts[g] = grade_counts.get(g, 0) + 1

    grade_order = ["A", "B", "C", "D", "F"]
    counts = [grade_counts.get(g, 0) for g in grade_order]
    max_count = max(counts) if any(counts) else 1

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Grade Distribution")
    pdf.ln(12)

    chart_x = pdf.l_margin + 10
    chart_y = pdf.get_y()
    chart_h = 60
    bar_w = 24
    gap = 10

    for idx, (grade, count) in enumerate(zip(grade_order, counts)):
        bar_h = (count / max_count) * chart_h if max_count else 0
        x = chart_x + idx * (bar_w + gap)
        y = chart_y + chart_h - bar_h
        r, g_c, b = _grade_colour(grade)
        pdf.set_fill_color(r, g_c, b)
        if bar_h > 0:
            pdf.rect(x, y, bar_w, bar_h, style="F")
        # Label
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.set_xy(x, chart_y + chart_h + 2)
        pdf.cell(bar_w, 6, grade, align="C")
        pdf.set_xy(x, chart_y + chart_h + 8)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(bar_w, 5, str(count), align="C")


# ── Public API ─────────────────────────────────────────────────────────

def export_pdf_report(report_data: dict, output_dir: Path) -> "Path | None":
    """Generate a PDF audit report and write it to *output_dir*.

    Returns the path to the written file, or None if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF  # noqa: F401 — checked here for clean error
    except ImportError:
        print("  PDF export requires fpdf2: pip install fpdf2", file=sys.stderr)
        return None

    AuditPDF = _make_pdf_class()
    if AuditPDF is None:
        print("  PDF export requires fpdf2: pip install fpdf2", file=sys.stderr)
        return None

    username = report_data.get("username", "unknown")
    generated_at = report_data.get("generated_at", "")
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        dt = datetime.now(timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")

    pdf = AuditPDF(orientation="P", unit="mm", format="A4")
    pdf._username = username
    pdf._date = date_str
    pdf.set_margins(left=15, top=18, right=15)
    pdf.set_auto_page_break(auto=True, margin=18)

    _title_page(pdf, report_data, date_str)
    _exec_summary(pdf, report_data)
    _repos_table(pdf, report_data)
    _quick_wins(pdf, report_data)
    _grade_chart(pdf, report_data)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"audit-report-{username}-{date_str}.pdf"
    out_path = output_dir / filename
    pdf.output(str(out_path))
    return out_path
