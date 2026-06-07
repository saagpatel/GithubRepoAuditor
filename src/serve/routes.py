"""FastAPI route handlers for audit serve."""

from __future__ import annotations

import asyncio
import html as _html
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from src.portfolio_truth_types import truth_latest_path
from src.serve.runner import SAFE_FLAG_NAMES, get_session, spawn_run, validate_flags

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _output_dir(request: Request) -> Path:
    return request.app.state.output_dir


def _escape(value: object) -> str:
    return _html.escape(str(value), quote=True)


def _load_portfolio_truth(output_dir: Path) -> dict[str, Any]:
    p = truth_latest_path(output_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _connect_warehouse(output_dir: Path) -> sqlite3.Connection | None:
    db = output_dir / "portfolio-warehouse.db"
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _repo_list(truth: dict[str, Any]) -> list[dict[str, Any]]:
    repos = truth.get("repos") or truth.get("portfolio") or []
    if isinstance(repos, list):
        return repos
    return []


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except sqlite3.Error:
        return set()


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    output_dir = _output_dir(request)
    truth = _load_portfolio_truth(output_dir)
    repos = _repo_list(truth)
    total = len(repos)
    generated_at = truth.get("generated_at") or truth.get("snapshot_date") or "—"

    # Top-5 by risk score (descending)
    def _risk(r: dict[str, Any]) -> float:
        return float(r.get("risk_score") or r.get("risk") or 0)

    def _gap(r: dict[str, Any]) -> float:
        # Gap = 100 - completeness (higher gap = lower completeness)
        completeness = float(r.get("completeness_score") or r.get("completeness") or 0)
        return 100.0 - completeness

    top_risk = sorted(repos, key=_risk, reverse=True)[:5]
    top_gap = sorted(repos, key=_gap, reverse=True)[:5]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "total": total,
            "generated_at": generated_at,
            "top_risk": top_risk,
            "top_gap": top_gap,
        },
    )


@router.get("/repos/{name}", response_class=HTMLResponse)
async def repo_detail(request: Request, name: str) -> HTMLResponse:
    output_dir = _output_dir(request)
    truth = _load_portfolio_truth(output_dir)
    repos = _repo_list(truth)

    repo = next((r for r in repos if r.get("name") == name), None)
    if repo is None:
        return templates.TemplateResponse(
            request,
            "repo.html",
            {
                "repo": None,
                "name": name,
                "history": [],
                "error": f"Repo '{name}' not found in portfolio truth snapshot.",
            },
            status_code=404,
        )

    # Pull last 5 run snapshots for this repo from warehouse
    history: list[dict[str, Any]] = []
    conn = _connect_warehouse(output_dir)
    if conn is not None:
        try:
            if "repo_name" in _table_columns(conn, "repo_snapshots"):
                rows = conn.execute(
                    """
                    SELECT rs.run_id, ar.generated_at, rs.total_score,
                           rs.completeness_score, rs.risk_score
                    FROM   repo_snapshots rs
                    JOIN   audit_runs ar ON ar.run_id = rs.run_id
                    WHERE  rs.repo_name = ?
                    ORDER  BY ar.generated_at DESC
                    LIMIT  5
                    """,
                    (name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT rs.run_id, ar.generated_at, rs.overall_score AS total_score,
                           NULL AS completeness_score, NULL AS risk_score
                    FROM   repo_snapshots rs
                    JOIN   audit_runs ar ON ar.run_id = rs.run_id
                    JOIN   repos r ON r.repo_id = rs.repo_id
                    WHERE  r.name = ? OR r.full_name = ? OR rs.repo_id = ?
                    ORDER  BY ar.generated_at DESC
                    LIMIT  5
                    """,
                    (name, name, name),
                ).fetchall()
            history = [dict(r) for r in rows]
        except sqlite3.Error:
            # Optional warehouse history should not block the repo detail page.
            pass
        finally:
            conn.close()

    # Score breakdown — try dimension_scores
    dimension_scores: list[dict[str, Any]] = []
    conn2 = _connect_warehouse(output_dir)
    if conn2 is not None:
        try:
            if "repo_name" in _table_columns(conn2, "dimension_scores"):
                rows2 = conn2.execute(
                    """
                    SELECT ds.dimension, ds.score, ds.weight
                    FROM   dimension_scores ds
                    JOIN   audit_runs ar ON ar.run_id = ds.run_id
                    WHERE  ds.repo_name = ?
                    ORDER  BY ar.generated_at DESC
                    LIMIT  20
                    """,
                    (name,),
                ).fetchall()
            else:
                rows2 = conn2.execute(
                    """
                    SELECT ds.dimension, ds.score, ds.max_score AS weight
                    FROM   dimension_scores ds
                    JOIN   audit_runs ar ON ar.run_id = ds.run_id
                    JOIN   repos r ON r.repo_id = ds.repo_id
                    WHERE  r.name = ? OR r.full_name = ? OR ds.repo_id = ?
                    ORDER  BY ar.generated_at DESC
                    LIMIT  20
                    """,
                    (name, name, name),
                ).fetchall()
            dimension_scores = [dict(r) for r in rows2]
        except sqlite3.Error:
            # Optional dimension breakdown should not block the repo detail page.
            pass
        finally:
            conn2.close()

    return templates.TemplateResponse(
        request,
        "repo.html",
        {
            "repo": repo,
            "history": history,
            "dimension_scores": dimension_scores,
        },
    )


@router.get("/runs", response_class=HTMLResponse)
async def runs_list(request: Request, page: int = 1) -> HTMLResponse:
    output_dir = _output_dir(request)
    per_page = 20
    offset = (page - 1) * per_page
    rows: list[dict[str, Any]] = []
    total_count = 0

    conn = _connect_warehouse(output_dir)
    if conn is not None:
        try:
            total_count = conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0]
            raw = conn.execute(
                """
                SELECT run_id, username, generated_at, run_mode,
                       total_repos, repos_audited, average_score
                FROM   audit_runs
                ORDER  BY generated_at DESC
                LIMIT  ? OFFSET ?
                """,
                (per_page, offset),
            ).fetchall()
            rows = [dict(r) for r in raw]
        except sqlite3.Error:
            # Runs can render as an empty list when the optional warehouse is unreadable.
            pass
        finally:
            conn.close()

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "rows": rows,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
        },
    )


@router.get("/approvals", response_class=HTMLResponse)
async def approvals(request: Request) -> HTMLResponse:
    output_dir = _output_dir(request)
    records: list[dict[str, Any]] = []
    try:
        from src.warehouse import load_approval_records

        # username is inferred from output_dir contents — use empty string as sentinel
        records = load_approval_records(output_dir, username="")
    except Exception:
        # Approval center is best-effort; the page can render with no records.
        pass

    return templates.TemplateResponse(
        request,
        "approvals.html",
        {
            "records": records,
        },
    )


@router.get("/approvals/{record_id}/draft-diff", response_class=HTMLResponse)
async def draft_diff(request: Request, record_id: str) -> HTMLResponse:
    """Return an HTMX partial showing proposed vs current README for a draft-readme packet."""
    output_dir = _output_dir(request)
    record: dict[str, Any] | None = None
    try:
        from src.warehouse import load_approval_records

        all_records = load_approval_records(output_dir, username="")
        record = next(
            (r for r in all_records if r.get("approval_id") == record_id),
            None,
        )
    except Exception:
        # Missing/unreadable approval records are handled by the 404 below.
        pass

    if record is None:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    if record.get("approval_subject_type") != "draft-readme":
        raise HTTPException(
            status_code=404,
            detail=f"Record '{record_id}' is not a draft-readme packet",
        )

    proposed_readme: str = record.get("proposed_readme") or ""
    current_readme_sha: str | None = record.get("current_readme_sha") or None
    repo_name: str = record.get("repo_name") or record.get("subject_key") or record_id
    diff_summary: str = record.get("diff_summary") or ""

    return templates.TemplateResponse(
        request,
        "draft_diff.html",
        {
            "repo_name": repo_name,
            "proposed_readme": proposed_readme,
            "current_readme_sha": current_readme_sha,
            "diff_summary": diff_summary,
        },
    )


@router.get("/approvals/{record_id}/campaign-plan", response_class=HTMLResponse)
async def campaign_plan(request: Request, record_id: str) -> HTMLResponse:
    """Return an HTMX partial showing goal + per-action table for a campaign-plan packet."""
    output_dir = _output_dir(request)
    record: dict[str, Any] | None = None
    try:
        from src.warehouse import load_approval_records

        all_records = load_approval_records(output_dir, username="")
        record = next(
            (r for r in all_records if r.get("approval_id") == record_id),
            None,
        )
    except Exception:
        # Missing/unreadable campaign records are handled by the 404 below.
        pass

    if record is None:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    if record.get("approval_subject_type") != "campaign-plan":
        raise HTTPException(
            status_code=404,
            detail=f"Record '{record_id}' is not a campaign-plan packet",
        )

    goal: str = record.get("goal") or record.get("target_context") or ""
    candidate_count: int = int(record.get("candidate_count") or 0)
    qualified_count: int = int(record.get("qualified_count") or 0)
    llm_cost_usd: float = float(record.get("llm_cost_usd") or 0.0)
    raw_actions: list[Any] = record.get("actions") or []
    # Normalise to list[dict] — the warehouse may return them as dicts already
    actions: list[dict[str, Any]] = [a if isinstance(a, dict) else {} for a in raw_actions]
    pending_count: int = sum(1 for a in actions if a.get("action_type") == "pending_human_action")
    # 7B.4 — per-action state counts
    approved_count: int = sum(1 for a in actions if (a.get("state") or "pending") == "approved")
    rejected_count: int = sum(1 for a in actions if (a.get("state") or "pending") == "rejected")
    state_pending_count: int = sum(1 for a in actions if (a.get("state") or "pending") == "pending")

    return templates.TemplateResponse(
        request,
        "campaign_plan.html",
        {
            "packet_id": record_id,
            "goal": goal,
            "candidate_count": candidate_count,
            "qualified_count": qualified_count,
            "llm_cost_usd": llm_cost_usd,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "state_pending_count": state_pending_count,
            "actions": actions,
        },
    )


@router.post("/approvals/{approval_id}/approve", response_class=HTMLResponse)
async def approve_packet(request: Request, approval_id: str) -> HTMLResponse:
    """Record intent into session log; does NOT mutate the approval state."""
    _record_intent(request, approval_id, "approve")
    return HTMLResponse('<span class="badge badge-approved">Approved (intent recorded)</span>')


@router.post("/approvals/{approval_id}/reject", response_class=HTMLResponse)
async def reject_packet(request: Request, approval_id: str) -> HTMLResponse:
    """Record intent into session log; does NOT mutate the approval state."""
    _record_intent(request, approval_id, "reject")
    return HTMLResponse('<span class="badge badge-rejected">Rejected (intent recorded)</span>')


# ---------------------------------------------------------------------------
# 7B.3 — Per-action approve / reject (HTMX partial routes)
# ---------------------------------------------------------------------------


def _render_action_row(packet_id: str, idx: int, action: dict[str, Any]) -> str:
    """Render a single campaign-plan action table row as an HTML fragment."""
    state: str = action.get("state") or "pending"
    repo = _escape(action.get("repo_name") or "")
    action_type = _escape(action.get("action_type") or "")
    target = _escape(action.get("target") or "—")
    rationale = _escape(action.get("rationale") or "—")
    safe_packet_id = _escape(packet_id)

    if state == "approved":
        state_cell = '<span class="badge badge-approved">&#10003; Approved</span>'
        buttons = ""
        row_class = "campaign-plan__row--approved"
    elif state == "rejected":
        reason = _escape(action.get("rejected_reason") or "")
        reason_note = f" ({reason})" if reason else ""
        state_cell = f'<span class="badge badge-rejected">&#10007; Rejected{reason_note}</span>'
        buttons = ""
        row_class = "campaign-plan__row--rejected"
    else:
        state_cell = '<span class="badge badge-pending">Pending</span>'
        buttons = (
            f'<button class="btn-approve" '
            f'hx-post="/approvals/{safe_packet_id}/actions/{idx}/approve" '
            f'hx-target="closest tr" hx-swap="outerHTML">&#10003; Approve</button> '
            f'<button class="btn-reject" '
            f'hx-post="/approvals/{safe_packet_id}/actions/{idx}/reject" '
            f'hx-target="closest tr" hx-swap="outerHTML">&#10007; Reject</button>'
        )
        row_class = "campaign-plan__row--pending"

    return (
        f'<tr class="{row_class}" id="action-row-{idx}">'
        f"<td><code>{repo}</code></td>"
        f'<td><span class="campaign-plan__action-type">{action_type}</span></td>'
        f"<td>{target}</td>"
        f'<td class="campaign-plan__rationale">{rationale}</td>'
        f"<td>{state_cell}</td>"
        f"<td>{buttons}</td>"
        f"</tr>"
    )


@router.post("/approvals/{packet_id}/actions/{idx}/approve", response_class=HTMLResponse)
async def approve_campaign_action(request: Request, packet_id: str, idx: int) -> HTMLResponse:
    """Set action idx to approved; return updated row partial for HTMX swap."""
    from src.plan_campaign import approve_action as _approve_action
    from src.warehouse import load_approval_records

    output_dir = _output_dir(request)
    try:
        _approve_action(packet_id, idx, output_dir)
    except (ValueError, IndexError):
        return HTMLResponse(
            '<tr><td colspan="6" class="error">Not found.</td></tr>',
            status_code=404,
        )

    # Re-read the updated action dict from the ledger
    try:
        all_records = load_approval_records(output_dir, username="")
        record = next((r for r in all_records if r.get("approval_id") == packet_id), None)
        action_dict: dict[str, Any] = {}
        if record:
            raw = record.get("actions") or []
            if 0 <= idx < len(raw):
                action_dict = raw[idx] if isinstance(raw[idx], dict) else {}
    except Exception:
        action_dict = {"state": "approved"}

    # Dynamic values are escaped in _render_action_row before fragment emission.
    # codeql[py/reflective-xss]
    return HTMLResponse(_render_action_row(packet_id, idx, action_dict))


@router.post("/approvals/{packet_id}/actions/{idx}/reject", response_class=HTMLResponse)
async def reject_campaign_action(
    request: Request,
    packet_id: str,
    idx: int,
    reason: str = Form(""),
) -> HTMLResponse:
    """Set action idx to rejected; return updated row partial for HTMX swap."""
    from src.plan_campaign import reject_action as _reject_action
    from src.warehouse import load_approval_records

    output_dir = _output_dir(request)
    try:
        _reject_action(packet_id, idx, output_dir, reason=reason)
    except (ValueError, IndexError):
        return HTMLResponse(
            '<tr><td colspan="6" class="error">Not found.</td></tr>',
            status_code=404,
        )

    try:
        all_records = load_approval_records(output_dir, username="")
        record = next((r for r in all_records if r.get("approval_id") == packet_id), None)
        action_dict: dict[str, Any] = {}
        if record:
            raw = record.get("actions") or []
            if 0 <= idx < len(raw):
                action_dict = raw[idx] if isinstance(raw[idx], dict) else {}
    except Exception:
        action_dict = {"state": "rejected"}

    # Dynamic values are escaped in _render_action_row before fragment emission.
    # codeql[py/reflective-xss]
    return HTMLResponse(_render_action_row(packet_id, idx, action_dict))


def _record_intent(request: Request, approval_id: str, action: str) -> None:
    log_path = _output_dir(request) / "serve-intent-log.jsonl"
    entry = {"approval_id": approval_id, "action": action, "ts": time.time()}
    with log_path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


# ── Sprint 8.5 — per-section draft-readme routes ─────────────────────────────


def _render_section_card(record_id: str, section: dict[str, Any]) -> str:
    """Render a single section card as an HTML fragment for HTMX hx-swap='outerHTML'."""
    state: str = section.get("state") or "pending"
    heading: str = section.get("section_heading") or "(intro)"
    body: str = section.get("section_body") or ""
    safe_record_id = _escape(record_id)

    if state == "approved":
        state_badge = '<span class="badge badge-approved">&#10003; Approved</span>'
        buttons = ""
        card_class = "section-card section-card--approved"
    elif state == "rejected":
        reason = _escape(section.get("rejected_reason") or "")
        reason_note = f" ({reason})" if reason else ""
        state_badge = f'<span class="badge badge-rejected">&#10007; Rejected{reason_note}</span>'
        buttons = ""
        card_class = "section-card section-card--rejected"
    else:
        state_badge = '<span class="badge badge-pending">Pending</span>'
        buttons = (
            f'<button class="btn-approve" '
            f'hx-post="/approvals/sections/{safe_record_id}/approve" '
            f'hx-target="closest .section-card" hx-swap="outerHTML">'
            f"&#10003; Approve</button> "
            f'<button class="btn-reject" '
            f'hx-post="/approvals/sections/{safe_record_id}/reject" '
            f'hx-target="closest .section-card" hx-swap="outerHTML">'
            f"&#10007; Reject</button>"
        )
        card_class = "section-card section-card--pending"

    safe_body = _escape(body)
    safe_heading = _escape(heading)

    return (
        f'<div class="{card_class}" id="section-card-{safe_record_id}">'
        f'<div class="section-card__header">'
        f'<h3 class="section-card__heading">## {safe_heading}</h3>'
        f"{state_badge}"
        f"</div>"
        f'<pre class="section-card__body">{safe_body}</pre>'
        f'<div class="section-card__actions">{buttons}</div>'
        f"</div>"
    )


@router.get("/approvals/{packet_id}/draft-sections", response_class=HTMLResponse)
async def draft_sections(request: Request, packet_id: str) -> HTMLResponse:
    """Render the multi-section diff view: counter + N section cards."""
    output_dir = _output_dir(request)
    sections: list[dict[str, Any]] = []
    try:
        from src.warehouse import load_approval_records

        all_records = load_approval_records(output_dir, username="")
        sections = sorted(
            [
                r
                for r in all_records
                if r.get("approval_subject_type") == "draft-readme-section"
                and r.get("packet_id") == packet_id
            ],
            key=lambda r: int(r.get("section_idx") or 0),
        )
    except Exception:
        # Missing/unreadable section records are handled by the 404 below.
        pass

    if not sections:
        raise HTTPException(status_code=404, detail=f"Packet '{packet_id}' not found")

    repo_name: str = str(sections[0].get("repo_name") or sections[0].get("subject_key") or "")
    total = len(sections)
    approved_count = sum(1 for s in sections if s.get("state") == "approved")
    rejected_count = sum(1 for s in sections if s.get("state") == "rejected")
    pending_count = total - approved_count - rejected_count

    return templates.TemplateResponse(
        request,
        "draft_sections.html",
        {
            "packet_id": packet_id,
            "repo_name": repo_name,
            "sections": sections,
            "total": total,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "pending_count": pending_count,
        },
    )


@router.post("/approvals/sections/{record_id}/approve", response_class=HTMLResponse)
async def approve_section_route(request: Request, record_id: str) -> HTMLResponse:
    """Set section record_id to approved; return updated section card for HTMX swap."""
    from src.draft_readmes import approve_section as _approve_section
    from src.warehouse import load_approval_records

    output_dir = _output_dir(request)
    try:
        _approve_section(record_id, output_dir)
    except ValueError:
        return HTMLResponse(
            '<div class="section-card section-card--error">Not found.</div>',
            status_code=404,
        )

    # Re-read to get the updated section dict
    try:
        all_records = load_approval_records(output_dir, username="")
        section: dict[str, Any] = next(
            (r for r in all_records if r.get("approval_id") == record_id),
            {"state": "approved"},
        )
    except Exception:
        section = {"state": "approved"}

    return HTMLResponse(_render_section_card(record_id, section))


@router.post("/approvals/sections/{record_id}/reject", response_class=HTMLResponse)
async def reject_section_route(
    request: Request,
    record_id: str,
    reason: str = Form(""),
) -> HTMLResponse:
    """Set section record_id to rejected; return updated section card for HTMX swap."""
    from src.draft_readmes import reject_section as _reject_section
    from src.warehouse import load_approval_records

    output_dir = _output_dir(request)
    try:
        _reject_section(record_id, output_dir, reason=reason)
    except ValueError:
        return HTMLResponse(
            '<div class="section-card section-card--error">Not found.</div>',
            status_code=404,
        )

    # Re-read to get the updated section dict
    try:
        all_records = load_approval_records(output_dir, username="")
        section: dict[str, Any] = next(
            (r for r in all_records if r.get("approval_id") == record_id),
            {"state": "rejected"},
        )
    except Exception:
        section = {"state": "rejected"}

    return HTMLResponse(_render_section_card(record_id, section))


@router.get("/initiatives", response_class=HTMLResponse)
async def initiatives(request: Request) -> HTMLResponse:
    """Render the open initiative tracker page."""
    output_dir = _output_dir(request)

    from src.initiatives import derive_status, initiatives_path, load_initiatives
    from src.maturity_tiers import compute_tier, tier_gap, tier_name

    inits = load_initiatives(initiatives_path(output_dir))

    # Load portfolio-truth, keyed by identity.display_name
    projects_by_name: dict[str, dict[str, Any]] = {}
    truth_path = truth_latest_path(output_dir)
    if truth_path.exists():
        try:
            truth = json.loads(truth_path.read_text())
            for p in truth.get("projects", []):
                name = (p.get("identity") or {}).get("display_name") or ""
                if name:
                    projects_by_name[name] = p
        except (json.JSONDecodeError, OSError):
            # Initiative list can render without truth-derived tier context.
            pass

    open_initiatives = [i for i in inits if i.closed_at is None]
    closed_count = sum(1 for i in inits if i.closed_at is not None)

    rows: list[dict[str, Any]] = []
    for init in open_initiatives:
        repo = projects_by_name.get(init.repo_name, {})
        current = compute_tier(repo) if repo else 0
        gap = tier_gap(repo, init.target_tier) if repo else None
        status = derive_status(init, repo)
        rows.append(
            {
                "repo_name": init.repo_name,
                "current_tier": current,
                "current_tier_name": tier_name(current),
                "target_tier": init.target_tier,
                "target_tier_name": tier_name(init.target_tier),
                "deadline": init.deadline,
                "set_at": init.set_at,
                "set_by": init.set_by,
                "status": status,
                "missing_requirements": gap.missing_requirements if gap else [],
                "requirement_sources": gap.requirement_sources if gap else [],
                "progress_pct": int(100 * current / init.target_tier) if init.target_tier else 0,
            }
        )

    counts = {
        "on_track": sum(1 for r in rows if r["status"] == "on-track"),
        "at_risk": sum(1 for r in rows if r["status"] == "at-risk"),
        "overdue": sum(1 for r in rows if r["status"] == "overdue"),
        "met": sum(1 for r in rows if r["status"] == "met"),
    }

    return templates.TemplateResponse(
        request,
        "initiatives.html",
        {"rows": rows, "counts": counts, "closed_count": closed_count},
    )


@router.get("/initiatives/suggestions", response_class=HTMLResponse)
async def initiatives_suggestions(
    request: Request,
    target: int | None = None,
) -> HTMLResponse:
    """Render LLM-ranked suggestions as a page with per-card Accept buttons.
    `target` query param overrides per-repo next-tier targeting."""
    from src.maturity_tiers import tier_name
    from src.suggest_initiatives import default_deadline_for_effort, generate_suggestions

    output_dir = _output_dir(request)
    truth_path = truth_latest_path(output_dir)

    if not truth_path.exists():
        return templates.TemplateResponse(
            request,
            "initiatives_suggestions.html",
            {
                "suggestions": [],
                "cost_usd": 0.0,
                "error": "portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first.",
            },
        )

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return templates.TemplateResponse(
            request,
            "initiatives_suggestions.html",
            {"suggestions": [], "cost_usd": 0.0, "error": f"Failed to read portfolio-truth: {exc}"},
        )

    projects = truth.get("projects", [])

    cache_key = f"{truth.get('generated_at', '')}|target={target if target is not None else 'auto'}"
    try:
        suggestions, cost = generate_suggestions(
            projects,
            target_tier=target,
            budget_usd=0.10,
            cache_key=cache_key,
            output_dir=output_dir,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "initiatives_suggestions.html",
            {"suggestions": [], "cost_usd": 0.0, "error": f"Failed to generate suggestions: {exc}"},
        )

    rows = [
        {
            "repo_name": s.repo_name,
            "current_tier": s.current_tier,
            "current_tier_name": tier_name(s.current_tier),
            "target_tier": s.target_tier,
            "target_tier_name": tier_name(s.target_tier),
            "missing_requirements": s.missing_requirements,
            "rationale": s.rationale,
            "estimated_effort": s.estimated_effort,
            "default_deadline": default_deadline_for_effort(s.estimated_effort),
        }
        for s in suggestions
    ]

    return templates.TemplateResponse(
        request,
        "initiatives_suggestions.html",
        {"suggestions": rows, "cost_usd": cost, "error": None},
    )


@router.post("/initiatives/accept", response_class=HTMLResponse)
async def accept_initiative_route(
    request: Request,
    repo_name: str = Form(...),
    target_tier: int = Form(...),
    deadline: str = Form(...),
) -> HTMLResponse:
    """HTMX endpoint: convert suggestion into initiative. Returns updated card partial."""
    from src.suggest_initiatives import accept_suggestion

    output_dir = _output_dir(request)
    truth_path = truth_latest_path(output_dir)

    if not truth_path.exists():
        return HTMLResponse(
            '<div class="suggestion-card accept-error">Error: portfolio-truth-latest.json not found</div>',
            status_code=400,
        )

    try:
        truth = json.loads(truth_path.read_text())
    except (OSError, json.JSONDecodeError):
        return HTMLResponse(
            '<div class="suggestion-card accept-error">Error: failed to read portfolio truth.</div>',
            status_code=400,
        )

    projects = truth.get("projects", [])

    try:
        initiative = accept_suggestion(
            repo_name=repo_name,
            projects=projects,
            output_dir=output_dir,
            deadline=deadline,
            target_tier=target_tier,
        )
    except ValueError:
        return HTMLResponse(
            '<div class="suggestion-card accept-error">Error: unable to accept initiative.</div>',
            status_code=400,
        )

    return HTMLResponse(
        f'<div class="suggestion-card accepted" data-repo="{_escape(initiative.repo_name)}">'
        f"<strong>✓ Accepted:</strong> {_escape(initiative.repo_name)} → "
        f"Tier {initiative.target_tier} by {_escape(initiative.deadline)}. "
        f'<a href="/initiatives">View initiatives →</a>'
        f"</div>"
    )


@router.post("/initiatives/suggestions/dismiss", response_class=HTMLResponse)
async def dismiss_suggestion_route(
    request: Request,
    repo_name: str = Form(...),
    reason: str = Form(""),
) -> HTMLResponse:
    """Dismiss a suggestion. Returns HTMX partial (Arc G S11.4)."""
    from src.suggest_initiatives import dismiss_suggestion_record, dismissed_path

    output_dir = _output_dir(request)
    try:
        entry = dismiss_suggestion_record(
            dismissed_path(output_dir), repo_name=repo_name, reason=reason
        )
    except ValueError:
        return HTMLResponse(
            '<div class="suggestion-card accept-error">Error: unable to dismiss suggestion.</div>',
            status_code=400,
        )

    return HTMLResponse(
        f'<div class="suggestion-card dismissed" data-repo="{_escape(entry.repo_name)}">'
        f"<strong>✗ Dismissed:</strong> {_escape(entry.repo_name)}"
        + (f" — {_escape(entry.reason)}" if entry.reason else "")
        + ' <a href="/initiatives/suggestions">Refresh suggestions →</a>'
        + "</div>"
    )


@router.get("/initiatives/dismissed", response_class=HTMLResponse)
async def initiatives_dismissed(request: Request) -> HTMLResponse:
    """List currently dismissed suggestions with per-row Undo button (Arc G S12.2).

    Filters out entries whose `expires_at` is strictly before today —
    those rows should appear under `--dismissal-history` only.
    """
    from datetime import date as _date

    from src.suggest_initiatives import dismissed_path, load_dismissed

    output_dir = _output_dir(request)
    items = load_dismissed(dismissed_path(output_dir))
    today_iso = _date.today().isoformat()

    rows = [
        {
            "repo_name": d.repo_name,
            "reason": d.reason,
            "dismissed_at": d.dismissed_at,
            "dismissed_by": d.dismissed_by,
            "expires_at": d.expires_at,
        }
        for d in items
        if not d.expires_at or d.expires_at >= today_iso
    ]

    return templates.TemplateResponse(
        request,
        "initiatives_dismissed.html",
        {"rows": rows, "count": len(rows)},
    )


@router.post("/initiatives/dismissed/undo", response_class=HTMLResponse)
async def undo_dismiss_route(
    request: Request,
    repo_name: str = Form(...),
) -> HTMLResponse:
    """Restore a dismissed repo. HTMX swap-out the row (Arc G S12.2)."""
    from src.suggest_initiatives import dismissed_path, undo_dismiss

    output_dir = _output_dir(request)
    removed = undo_dismiss(dismissed_path(output_dir), repo_name)

    if removed:
        return HTMLResponse(
            f'<tr class="undone"><td colspan="5">✓ Restored: {_html.escape(repo_name)}</td></tr>'
        )
    return HTMLResponse(
        f'<tr class="undo-error"><td colspan="5">Error: {_html.escape(repo_name)} not currently dismissed</td></tr>',
        status_code=404,
    )


@router.get("/initiatives/dismissal-history", response_class=HTMLResponse)
async def initiatives_dismissal_history(request: Request) -> HTMLResponse:
    """Show chronological audit trail of dismiss/undo/expire events (Arc G S13.1)."""
    from src.suggest_initiatives import dismissed_path, load_dismissal_events

    output_dir = _output_dir(request)
    events = load_dismissal_events(dismissed_path(output_dir))
    # Newest first.
    rows = sorted(
        [
            {
                "repo_name": e.repo_name,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at,
                "actor": e.actor,
                "reason": e.reason,
            }
            for e in events
        ],
        key=lambda r: r["occurred_at"],
        reverse=True,
    )
    return templates.TemplateResponse(
        request,
        "initiatives_dismissal_history.html",
        {"rows": rows, "count": len(rows)},
    )


@router.get("/initiatives/{repo_name}/gap", response_class=HTMLResponse)
async def initiative_gap(request: Request, repo_name: str, target: int = 0) -> HTMLResponse:
    """Return an HTMX partial listing missing requirements for *repo_name* to reach *target* tier."""
    output_dir = _output_dir(request)

    from src.maturity_tiers import compute_tier, tier_gap, tier_name

    # Resolve target: use query-string value if provided and valid (1-4), else 0
    if target not in (1, 2, 3, 4):
        # Fall back to looking up the open initiative for this repo
        try:
            from src.initiatives import initiatives_path, load_initiatives

            inits = load_initiatives(initiatives_path(output_dir))
            for init in inits:
                if init.repo_name == repo_name and init.closed_at is None:
                    target = init.target_tier
                    break
        except Exception:
            # Query parameter target remains authoritative if initiative lookup fails.
            pass

    # Load portfolio-truth
    projects_by_name: dict[str, dict[str, Any]] = {}
    truth_path = truth_latest_path(output_dir)
    if truth_path.exists():
        try:
            truth = json.loads(truth_path.read_text())
            for p in truth.get("projects", []):
                name = (p.get("identity") or {}).get("display_name") or ""
                if name:
                    projects_by_name[name] = p
        except (json.JSONDecodeError, OSError):
            # The route raises a 404 below when truth data cannot be loaded.
            pass

    repo = projects_by_name.get(repo_name)
    if repo is None:
        raise HTTPException(
            status_code=404, detail=f"Repo '{repo_name}' not found in portfolio-truth"
        )

    if target not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="target must be 1-4")

    gap = tier_gap(repo, target)
    current = compute_tier(repo)

    return templates.TemplateResponse(
        request,
        "initiative_gap.html",
        {
            "repo_name": repo_name,
            "current_tier": current,
            "current_tier_name": tier_name(current),
            "target_tier": target,
            "target_tier_name": tier_name(target),
            "missing_requirements": gap.missing_requirements,
            "requirement_sources": gap.requirement_sources,
        },
    )


@router.get("/runs/new", response_class=HTMLResponse)
async def new_run_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "new_run.html",
        {
            "safe_flags": sorted(SAFE_FLAG_NAMES),
        },
    )


@router.post("/runs/new")
async def new_run_post(
    request: Request,
    username: str = Form(...),
    flags: str = Form(default=""),
) -> dict[str, str]:
    """Validate flags and spawn audit subprocess. Returns {run_id}."""
    flag_dict: dict[str, bool] = {}
    for raw in flags.split():
        norm = raw.lstrip("-").replace("_", "-")
        flag_dict[norm] = True

    try:
        validate_flags(flag_dict)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    output_dir = _output_dir(request)
    try:
        run_id = spawn_run(username=username, flags=flag_dict, output_dir=output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"run_id": run_id}


@router.get("/runs/new/stream/{run_id}")
async def stream_run(request: Request, run_id: str) -> StreamingResponse:
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    async def _event_gen() -> Any:
        sent = 0
        heartbeat_interval = 15  # seconds
        last_hb = time.monotonic()

        while True:
            lines = list(session.tail(after=sent))
            for line in lines:
                sent += 1
                yield f"data: {line}\n\n"

            if session.done and sent >= len(list(session.tail())):
                yield f"data: [DONE rc={session.return_code}]\n\n"
                break

            now = time.monotonic()
            if now - last_hb >= heartbeat_interval:
                yield ": heartbeat\n\n"
                last_hb = now

            await asyncio.sleep(0.2)

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
