"""FastAPI route handlers for audit serve."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from src.serve.runner import SAFE_FLAG_NAMES, get_session, spawn_run, validate_flags

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _output_dir(request: Request) -> Path:
    return request.app.state.output_dir


def _load_portfolio_truth(output_dir: Path) -> dict[str, Any]:
    p = output_dir / "portfolio-truth-latest.json"
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
        raise HTTPException(status_code=404, detail=f"Repo '{name}' not found")

    # Pull last 5 run snapshots for this repo from warehouse
    history: list[dict[str, Any]] = []
    conn = _connect_warehouse(output_dir)
    if conn is not None:
        try:
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
            history = [dict(r) for r in rows]
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    # Score breakdown — try dimension_scores
    dimension_scores: list[dict[str, Any]] = []
    conn2 = _connect_warehouse(output_dir)
    if conn2 is not None:
        try:
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
            dimension_scores = [dict(r) for r in rows2]
        except sqlite3.Error:
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


@router.post("/approvals/{approval_id}/approve", response_class=HTMLResponse)
async def approve_action(request: Request, approval_id: str) -> HTMLResponse:
    """Record intent into session log; does NOT mutate the approval state."""
    _record_intent(request, approval_id, "approve")
    return HTMLResponse('<span class="badge badge-approved">Approved (intent recorded)</span>')


@router.post("/approvals/{approval_id}/reject", response_class=HTMLResponse)
async def reject_action(request: Request, approval_id: str) -> HTMLResponse:
    """Record intent into session log; does NOT mutate the approval state."""
    _record_intent(request, approval_id, "reject")
    return HTMLResponse('<span class="badge badge-rejected">Rejected (intent recorded)</span>')


def _record_intent(request: Request, approval_id: str, action: str) -> None:
    log_path = _output_dir(request) / "serve-intent-log.jsonl"
    entry = {"approval_id": approval_id, "action": action, "ts": time.time()}
    with log_path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


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
    run_id = spawn_run(username=username, flags=flag_dict, output_dir=output_dir)
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
