"""Self-contained HTML dashboard generator.

Produces a single .html file with embedded CSS, JS, and data.
No external dependencies — works offline, shareable as one file.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from src.sparkline import sparkline as render_sparkline


# ── Color constants (matching Excel design system) ──────────────────

TIER_COLORS_CSS = {
    "shipped": "#166534",
    "functional": "#1565C0",
    "wip": "#D97706",
    "skeleton": "#C2410C",
    "abandoned": "#6B7280",
}

GRADE_COLORS_CSS = {
    "A": "#166534",
    "B": "#15803D",
    "C": "#CA8A04",
    "D": "#C2410C",
    "F": "#991B1B",
}

RADAR_COLORS = {
    "Adopt": "#166534",
    "Trial": "#1565C0",
    "Hold": "#6B7280",
    "Decline": "#991B1B",
}


def export_html_dashboard(
    report_data: dict,
    output_dir: Path,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> dict:
    """Generate interactive HTML dashboard. Returns {html_path}."""
    html = _render_html(report_data, trend_data, score_history)
    output_dir.mkdir(parents=True, exist_ok=True)
    date = report_data.get("generated_at", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    username = report_data.get("username", "unknown")
    html_path = output_dir / f"dashboard-{username}-{date}.html"
    html_path.write_text(html)
    return {"html_path": html_path}


def _render_html(
    report_data: dict,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> str:
    """Build the complete HTML string."""
    username = report_data.get("username", "unknown")
    date = report_data.get("generated_at", "")[:10]
    repos_audited = report_data.get("repos_audited", 0)
    grade = report_data.get("portfolio_grade", "F")

    # Prepare minimal data payload for JS
    js_data = {
        "username": username,
        "date": date,
        "grade": grade,
        "average_score": report_data.get("average_score", 0),
        "repos_audited": repos_audited,
        "tier_distribution": report_data.get("tier_distribution", {}),
        "audits": [
            {
                "name": a.get("metadata", {}).get("name", ""),
                "grade": a.get("grade", "F"),
                "score": round(a.get("overall_score", 0), 3),
                "interest": round(a.get("interest_score", 0), 3),
                "tier": a.get("completeness_tier", ""),
                "language": a.get("metadata", {}).get("language") or "",
                "description": (a.get("metadata", {}).get("description") or "")[:80],
                "url": a.get("metadata", {}).get("html_url", ""),
                "badges": len(a.get("badges", [])),
            }
            for a in report_data.get("audits", [])
        ],
    }

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        f"<title>Portfolio Dashboard: {escape(username)}</title>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<style>{_css()}</style>",
        "</head>",
        "<body>",
        _header_section(username, date, repos_audited, grade),
        _kpi_section(report_data),
        '<div class="section"><h2>Completeness vs Interest</h2>',
        '<canvas id="scatter" width="800" height="500"></canvas>',
        '<div id="tooltip" class="tooltip"></div>',
        '</div>',
        _repo_table(report_data.get("audits", []), score_history),
        _tech_radar_section(report_data, trend_data),
        _distribution_section(report_data),
        _footer(),
        f'<script id="dashboard-data" type="application/json">{_json_script_data(js_data)}</script>',
        f"<script>{_js()}</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


def _header_section(username: str, date: str, repos: int, grade: str) -> str:
    color = GRADE_COLORS_CSS.get(grade, "#6B7280")
    return f"""
    <header>
      <h1>Portfolio Dashboard: {escape(username)}</h1>
      <p>Generated {escape(date)} | {repos} repos audited | Grade <span style="color:{color};font-weight:bold">{escape(grade)}</span></p>
    </header>"""


def _kpi_section(data: dict) -> str:
    tiers = data.get("tier_distribution", {})
    avg = data.get("average_score", 0)
    shipped = tiers.get("shipped", 0)
    functional = tiers.get("functional", 0)
    needs_work = tiers.get("skeleton", 0) + tiers.get("abandoned", 0)
    return f"""
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-label">Avg Score</div><div class="kpi-value">{avg:.2f}</div></div>
      <div class="kpi-card"><div class="kpi-label">Shipped</div><div class="kpi-value" style="color:#166534">{shipped}</div></div>
      <div class="kpi-card"><div class="kpi-label">Functional</div><div class="kpi-value" style="color:#1565C0">{functional}</div></div>
      <div class="kpi-card"><div class="kpi-label">Needs Work</div><div class="kpi-value" style="color:#C2410C">{needs_work}</div></div>
    </div>"""


def _repo_table(audits: list[dict], score_history: dict[str, list[float]] | None = None) -> str:
    rows = []
    sorted_audits = sorted(audits, key=lambda a: a.get("overall_score", 0), reverse=True)
    for a in sorted_audits:
        m = a.get("metadata", {})
        name = m.get("name", "")
        url = m.get("html_url", "")
        grade = a.get("grade", "F")
        score = a.get("overall_score", 0)
        interest = a.get("interest_score", 0)
        tier = a.get("completeness_tier", "")
        lang = m.get("language") or ""
        desc = (m.get("description") or "")[:60]
        gc = GRADE_COLORS_CSS.get(grade, "#6B7280")
        tc = TIER_COLORS_CSS.get(tier, "#6B7280")

        spark = ""
        if score_history:
            scores = score_history.get(name, [])
            spark = render_sparkline(scores)

        safe_name = escape(name)
        safe_lang = escape(lang)
        safe_desc = escape(desc)
        safe_tier = escape(tier)
        safe_url = _safe_href(url)
        link = f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_name}</a>' if safe_url else safe_name
        rows.append(
            f'<tr data-tier="{escape(tier, quote=True)}" data-grade="{escape(grade, quote=True)}" data-name="{escape(name, quote=True)}">'
            f'<td>{link}</td>'
            f'<td style="color:{gc};font-weight:bold;text-align:center">{escape(grade)}</td>'
            f'<td class="num">{score:.3f}</td>'
            f'<td class="num">{interest:.3f}</td>'
            f'<td style="color:{tc};font-weight:bold">{safe_tier}</td>'
            f'<td>{safe_lang}</td>'
            f'<td class="sparkline">{escape(spark)}</td>'
            f'<td class="desc">{safe_desc}</td>'
            f'</tr>'
        )

    return f"""
    <div class="section">
      <h2>All Repos</h2>
      <div class="filters">
        <select id="filter-tier" onchange="filterTable()">
          <option value="all">All Tiers</option>
          <option value="shipped">Shipped</option>
          <option value="functional">Functional</option>
          <option value="wip">WIP</option>
          <option value="skeleton">Skeleton</option>
          <option value="abandoned">Abandoned</option>
        </select>
        <select id="filter-grade" onchange="filterTable()">
          <option value="all">All Grades</option>
          <option value="A">A</option><option value="B">B</option>
          <option value="C">C</option><option value="D">D</option>
          <option value="F">F</option>
        </select>
        <input id="search" type="text" placeholder="Search repos..." oninput="filterTable()">
      </div>
      <table id="repo-table">
        <thead><tr>
          <th>Repo</th><th>Grade</th><th>Score</th><th>Interest</th>
          <th>Tier</th><th>Language</th><th>Trend</th><th>Description</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


def _tech_radar_section(data: dict, trend_data: list[dict] | None) -> str:
    from src.history import load_language_trends
    trends = load_language_trends()

    if not trends:
        # Fall back to current language distribution
        lang_dist = data.get("language_distribution", {})
        if not lang_dist:
            return ""
        trends = [
            {"language": lang, "current_count": count, "category": "Hold", "repos_per_run": [count]}
            for lang, count in sorted(lang_dist.items(), key=lambda x: x[1], reverse=True)[:15]
        ]

    rows = []
    for t in trends[:20]:
        spark = render_sparkline([float(v) for v in t.get("repos_per_run", [])])
        cat = t.get("category", "Hold")
        color = RADAR_COLORS.get(cat, "#6B7280")
        rows.append(
            f'<tr><td>{escape(t["language"])}</td><td class="num">{t["current_count"]}</td>'
            f'<td class="sparkline">{escape(spark)}</td>'
            f'<td style="color:{color};font-weight:bold">{escape(cat)}</td></tr>'
        )

    return f"""
    <div class="section">
      <h2>Tech Radar</h2>
      <table>
        <thead><tr><th>Language</th><th>Repos</th><th>Trend</th><th>Category</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


def _distribution_section(data: dict) -> str:
    tiers = data.get("tier_distribution", {})
    total = sum(tiers.values()) or 1

    tier_bars = []
    for tier_name in ["shipped", "functional", "wip", "skeleton", "abandoned"]:
        count = tiers.get(tier_name, 0)
        pct = count / total * 100
        color = TIER_COLORS_CSS.get(tier_name, "#6B7280")
        tier_bars.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{tier_name.capitalize()}</span>'
            f'<div class="bar-bg"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>'
            f'<span class="bar-count">{count}</span>'
            f'</div>'
        )

    return f"""
    <div class="section">
      <h2>Tier Distribution</h2>
      <div class="bar-chart">{''.join(tier_bars)}</div>
    </div>"""


def _footer() -> str:
    return """
    <footer>
      <p>Generated by <a href="https://github.com/saagpatel/GithubRepoAuditor">GithubRepoAuditor</a></p>
    </footer>"""


def _css() -> str:
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #F8FAFC; color: #1B2A4A; line-height: 1.6; }
    header { background: #1B2A4A; color: white; padding: 24px 32px; }
    header h1 { font-size: 24px; margin-bottom: 4px; }
    header p { color: #94A3B8; font-size: 14px; }
    .kpi-row { display: flex; gap: 16px; padding: 24px 32px; }
    .kpi-card { flex: 1; background: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; text-align: center; }
    .kpi-label { font-size: 12px; color: #64748B; text-transform: uppercase; letter-spacing: 1px; }
    .kpi-value { font-size: 32px; font-weight: 700; color: #1B2A4A; }
    .section { padding: 24px 32px; }
    .section h2 { font-size: 18px; color: #1B2A4A; margin-bottom: 16px; border-bottom: 2px solid #E2E8F0; padding-bottom: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { background: #1B2A4A; color: white; padding: 8px 12px; text-align: left; font-weight: 600; }
    td { padding: 6px 12px; border-bottom: 1px solid #E2E8F0; }
    tr:nth-child(even) { background: #F8FAFC; }
    tr:hover { background: #EEF2FF; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .desc { color: #64748B; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .sparkline { font-family: 'Courier New', monospace; color: #0EA5E9; letter-spacing: 1px; }
    a { color: #0EA5E9; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .filters { display: flex; gap: 8px; margin-bottom: 12px; }
    .filters select, .filters input { padding: 6px 12px; border: 1px solid #CBD5E1; border-radius: 4px; font-size: 13px; }
    .filters input { flex: 1; }
    canvas { width: 100%; max-width: 800px; border: 1px solid #E2E8F0; border-radius: 8px; background: white; }
    .tooltip { position: absolute; background: #1B2A4A; color: white; padding: 6px 10px; border-radius: 4px; font-size: 12px; pointer-events: none; display: none; z-index: 10; }
    .bar-chart { max-width: 500px; }
    .bar-row { display: flex; align-items: center; margin-bottom: 8px; }
    .bar-label { width: 90px; font-size: 13px; font-weight: 600; }
    .bar-bg { flex: 1; height: 24px; background: #E2E8F0; border-radius: 4px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
    .bar-count { width: 40px; text-align: right; font-size: 13px; color: #64748B; margin-left: 8px; }
    footer { text-align: center; padding: 24px; color: #94A3B8; font-size: 12px; border-top: 1px solid #E2E8F0; margin-top: 32px; }
    @media print {
      .filters { display: none; }
      canvas { display: none; }
      header { background: white; color: #1B2A4A; border-bottom: 2px solid #1B2A4A; }
      header p { color: #64748B; }
      body { font-size: 10pt; }
      .kpi-card { break-inside: avoid; }
      .section { page-break-inside: avoid; }
    }
    """


def _json_script_data(data: dict) -> str:
    """Serialize JSON safely for embedding inside a non-executable script tag."""
    return json.dumps(data).replace("</", "<\\/")


def _safe_href(url: str) -> str:
    """Allow only absolute http(s) URLs in generated anchor tags."""
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return escape(url, quote=True)
    return ""


def _js() -> str:
    return """
    const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);
    // Tier colors for scatter chart
    const TIER_COLORS = {shipped:'#166534',functional:'#1565C0',wip:'#D97706',skeleton:'#C2410C',abandoned:'#6B7280'};

    // Scatter chart
    (function() {
      const canvas = document.getElementById('scatter');
      if (!canvas || !DATA.audits.length) return;
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height;
      const pad = 50;

      function draw() {
        ctx.clearRect(0,0,W,H);
        ctx.fillStyle = 'white'; ctx.fillRect(0,0,W,H);

        // Grid
        ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 1;
        for (let i = 0; i <= 10; i++) {
          const x = pad + (W-2*pad)*i/10, y = pad + (H-2*pad)*i/10;
          ctx.beginPath(); ctx.moveTo(x, pad); ctx.lineTo(x, H-pad); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W-pad, y); ctx.stroke();
        }

        // Quadrant lines
        ctx.strokeStyle = '#808080'; ctx.lineWidth = 1.5; ctx.setLineDash([6,4]);
        const qx = pad + (W-2*pad)*0.55, qy = pad + (H-2*pad)*(1-0.45);
        ctx.beginPath(); ctx.moveTo(qx, pad); ctx.lineTo(qx, H-pad); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(pad, qy); ctx.lineTo(W-pad, qy); ctx.stroke();
        ctx.setLineDash([]);

        // Axis labels
        ctx.fillStyle = '#64748B'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('Completeness', W/2, H-8);
        ctx.save(); ctx.translate(12, H/2); ctx.rotate(-Math.PI/2); ctx.fillText('Interest', 0, 0); ctx.restore();

        // Axis ticks
        ctx.fillStyle = '#94A3B8'; ctx.font = '10px sans-serif';
        for (let i = 0; i <= 10; i += 2) {
          const v = i/10;
          ctx.textAlign = 'center'; ctx.fillText(v.toFixed(1), pad+(W-2*pad)*v, H-pad+16);
          ctx.textAlign = 'right'; ctx.fillText(v.toFixed(1), pad-8, pad+(H-2*pad)*(1-v)+4);
        }

        // Points
        DATA.audits.forEach(a => {
          const x = pad + (W-2*pad)*a.score;
          const y = pad + (H-2*pad)*(1-a.interest);
          ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2);
          ctx.fillStyle = TIER_COLORS[a.tier] || '#6B7280';
          ctx.fill();
          ctx.strokeStyle = 'white'; ctx.lineWidth = 1; ctx.stroke();
        });
      }
      draw();

      // Hover tooltip
      const tooltip = document.getElementById('tooltip');
      canvas.addEventListener('mousemove', e => {
        const rect = canvas.getBoundingClientRect();
        const mx = (e.clientX - rect.left) * (W / rect.width);
        const my = (e.clientY - rect.top) * (H / rect.height);
        let found = null;
        DATA.audits.forEach(a => {
          const x = pad + (W-2*pad)*a.score;
          const y = pad + (H-2*pad)*(1-a.interest);
          if (Math.hypot(mx-x, my-y) < 8) found = a;
        });
        if (found) {
          tooltip.style.display = 'block';
          tooltip.style.left = (e.clientX + 12) + 'px';
          tooltip.style.top = (e.clientY - 8) + 'px';
          tooltip.textContent = found.name + ' (score:' + found.score + ' interest:' + found.interest + ')';
        } else {
          tooltip.style.display = 'none';
        }
      });
      canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
    })();

    // Table filtering
    function filterTable() {
      const tier = document.getElementById('filter-tier').value;
      const grade = document.getElementById('filter-grade').value;
      const search = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('#repo-table tbody tr').forEach(row => {
        const show = (tier === 'all' || row.dataset.tier === tier)
          && (grade === 'all' || row.dataset.grade === grade)
          && row.dataset.name.toLowerCase().includes(search);
        row.style.display = show ? '' : 'none';
      });
    }

    // Sortable columns
    document.querySelectorAll('#repo-table th').forEach((th, i) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const tbody = document.querySelector('#repo-table tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const asc = th.dataset.sort !== 'asc';
        th.dataset.sort = asc ? 'asc' : 'desc';
        rows.sort((a, b) => {
          const va = a.children[i].textContent, vb = b.children[i].textContent;
          const na = parseFloat(va), nb = parseFloat(vb);
          if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
          return asc ? va.localeCompare(vb) : vb.localeCompare(va);
        });
        rows.forEach(r => tbody.appendChild(r));
      });
    });
    """
