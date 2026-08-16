"""FastAPI app factory for the tracker UI.

Routes (per spec §6) + `/healthz`:

    GET  /                        kanban
    GET  /top                     top-ranked postings (any draft status)
    GET  /posting/{id}            posting detail
    POST /posting/{id}/apply      transition to 'applied' (human-click only)
    POST /application/{id}/status set arbitrary status (HTMX drag-and-drop)
    GET  /companies               company overview
    GET  /metrics                 dashboard
    GET  /healthz                 DB + Ollama + key check

Templates live under `src/job_finder/ui/templates/`. Every route that
renders a page passes `current=<route-key>` so the top nav can highlight
the active tab.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ..config import settings
from . import queries
from .jobs import ACTIONS, get_registry


def _safe_redirect(next_url: str | None, fallback: str) -> str:
    """Reject open-redirect attempts via the `next_url` form field.

    Only accept site-relative paths starting with a single `/`. Block:
        - schemes (https://, javascript:)
        - protocol-relative (//evil.com/...)
        - empty / None
    Anything else falls back to the per-route default.
    """
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
        return fallback
    return next_url

# Note: Windows event-loop policy (SelectorEventLoop for psycopg async) is
# handled in `jfb web serve` (see cli.py). Always launch the UI through that
# command, not via `uvicorn ...` directly.

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_app() -> FastAPI:
    app = FastAPI(title="Job Finder Bot", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    # Expose the configured default draft mode to every template so the
    # Queue buttons can pre-select the right radio without per-route plumbing.
    templates.env.globals["draft_mode_default"] = settings.draft_mode_default
    # Preset pool résumés (autonomy / graphics / applied-ai / fullstack) — the
    # queue UI offers these as $0, no-LLM alternatives to tailor/curate.
    from ..resume.presets import all_presets, is_valid_preset_mode, preset_label
    templates.env.globals["presets"] = all_presets()
    templates.env.globals["preset_label"] = preset_label
    templates.env.globals["is_preset_mode"] = is_valid_preset_mode

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Dashboard homepage. Shows pipeline state + 'what to do next' CTA.
        The kanban moved to /kanban — this page is the entry point for
        people who don't know what the bot does yet.
        """
        stats = await queries.pipeline_stats()
        # Decide the single most-important next action based on pipeline state.
        if stats["needs_classify"] > 0:
            next_action = {
                "title": f"Score {stats['needs_classify']} new posting(s)",
                "subtitle": "These have been pulled but not yet scored for fit. Cheap (~$0.01 each).",
                "href": "/run/classify",
                "cta": "Score them →",
                "kind": "cheap",
            }
        elif stats["queued"] > 0:
            next_action = {
                "title": f"Generate drafts for {stats['queued']} queued posting(s)",
                "subtitle": "Each runs through a fit-gate first; only good fits cost ~$0.05.",
                "href": "/run/draft",
                "cta": "Generate →",
                "kind": "paid",
            }
        elif stats["ready_for_human"] > 0:
            next_action = {
                "title": f"Review {stats['ready_for_human']} ready draft(s)",
                "subtitle": "Open each posting, read the cover letter, download the PDF, and submit on the company's site.",
                "href": "/top",
                "cta": "Review →",
                "kind": "free",
            }
        else:
            next_action = {
                "title": "Pull new postings",
                "subtitle": "Hit every seeded company's careers page. No LLM calls — free.",
                "href": "/run/ingest",
                "cta": "Pull →",
                "kind": "free",
            }
        return templates.TemplateResponse(
            request,
            "home.html",
            {"current": "home", "stats": stats, "next_action": next_action},
        )

    @app.get("/kanban", response_class=HTMLResponse)
    async def kanban(request: Request):
        grouped = await queries.kanban_rows()
        return templates.TemplateResponse(
            request,
            "kanban.html",
            {
                "current": "kanban",
                "columns": queries.KANBAN_COLUMNS,
                "grouped": grouped,
            },
        )

    @app.post("/posting/{posting_id}/dismiss")
    async def dismiss_posting(
        posting_id: int,
        reason: str | None = Form(default=None),
        next_url: str | None = Form(default=None),
    ):
        """Manual reject — hide this posting from /top forever (until you
        un-dismiss it). Useful when the bot scored it well but you can see
        the JD is unsuitable (geo lock, visa requirement, etc.)."""
        try:
            await queries.dismiss_posting(posting_id, reason=reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return RedirectResponse(
            url=_safe_redirect(next_url, fallback=f"/posting/{posting_id}"),
            status_code=303,
        )

    @app.post("/posting/{posting_id}/undismiss")
    async def undismiss_posting(
        posting_id: int,
        next_url: str | None = Form(default=None),
    ):
        """Reverse a dismissal — moves the application back to 'queued' so
        it shows up on /top again. No-op if the posting isn't dismissed."""
        await queries.queue_for_draft(posting_id, mode="curate")
        return RedirectResponse(
            url=_safe_redirect(next_url, fallback=f"/posting/{posting_id}"),
            status_code=303,
        )

    @app.get("/top", response_class=HTMLResponse)
    async def top(request: Request, limit: int = 200, show_dismissed: int = 0):
        # Cap absurdly large requests so the page doesn't render a megabyte
        # of rows. 1000 is more than enough for any human review session.
        limit = min(max(limit, 1), 1000)
        rows = await queries.top_postings(limit=limit, include_dismissed=bool(show_dismissed))
        # Single-pass header counts; the template used to walk `rows` three
        # times via Jinja `selectattr | list | length`.
        n_queued = n_review = n_applied = 0
        for r in rows:
            if r.get("applied_at"):
                n_applied += 1
            status = r.get("application_status")
            if status == "queued":
                n_queued += 1
            elif status in ("drafted", "ready_for_human"):
                n_review += 1
        return templates.TemplateResponse(
            request,
            "top.html",
            {
                "current": "top",
                "rows": rows,
                "n_queued": n_queued,
                "n_review": n_review,
                "n_applied": n_applied,
                "show_dismissed": bool(show_dismissed),
            },
        )

    @app.get("/posting/{posting_id}", response_class=HTMLResponse)
    async def posting_detail(request: Request, posting_id: int):
        row = await queries.posting_detail(posting_id)
        if row is None:
            raise HTTPException(status_code=404, detail="posting not found")
        return templates.TemplateResponse(
            request,
            "posting.html",
            {"current": "posting", "p": row},
        )

    @app.post("/posting/{posting_id}/queue")
    async def queue_for_draft(
        posting_id: int,
        mode: str = Form(default="tailor"),
        next_url: str | None = Form(default=None),
    ):
        """First gate of the two-gate apply flow.

        Per prefs.md, the bot does NOT auto-draft. The user must explicitly
        click "Queue for draft" on a posting; this endpoint inserts an
        `applications` row with status='queued', and the drafter (`jfb draft top`)
        picks it up on its next run.

        `mode` selects how the drafter will write this application:
            - tailor — model paraphrases bullets to match the posting (original)
            - curate — model only selects + pulls VERBATIM emphasis quotes

        After drafting, the posting moves to status='ready_for_human' for the
        SECOND gate (the existing /apply endpoint).
        """
        try:
            await queries.queue_for_draft(posting_id, mode=mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return RedirectResponse(
            url=_safe_redirect(next_url, fallback=f"/posting/{posting_id}"),
            status_code=303,
        )

    @app.post("/posting/{posting_id}/apply")
    async def mark_applied(
        posting_id: int,
        notes: str | None = Form(default=None),
    ):
        """SECOND gate: the ONLY endpoint that sets applied_at. Human-triggered.

        Spec §6: no bulk-apply button. Each call is one conscious click after
        the user has reviewed the bot-generated draft.
        """
        await queries.mark_applied(posting_id, notes=notes)
        # 303 → browser re-GETs the detail page; clean HTMX story too
        return RedirectResponse(url=f"/posting/{posting_id}", status_code=303)

    @app.post("/application/{application_id}/status")
    async def change_status(
        application_id: int,
        status: str = Form(...),
    ):
        """HTMX target for kanban drag-and-drop between non-terminal columns.

        Note: moving into 'applied' here *is* allowed (e.g. you submitted
        externally and want to reflect state), but the canonical path is
        still the /apply endpoint above.
        """
        try:
            await queries.set_status(application_id, status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        # HTMX: return a tiny OK; client code refreshes the column client-side
        return HTMLResponse(content=f"<span>{status}</span>")

    @app.get("/companies", response_class=HTMLResponse)
    async def companies(request: Request):
        rows = await queries.companies_overview()
        return templates.TemplateResponse(
            request,
            "companies.html",
            {"current": "companies", "rows": rows},
        )

    @app.get("/metrics", response_class=HTMLResponse)
    async def metrics(request: Request):
        data = await queries.metrics_overview()
        data["current"] = "metrics"
        return templates.TemplateResponse(request, "metrics.html", data)

    @app.get("/posting/{posting_id}/resume.pdf")
    async def tailored_resume_pdf(posting_id: int):
        """Render the tailored résumé PDF inline. Free — no LLM call."""
        from ..resume import render_for_posting
        try:
            pdf_path = await render_for_posting(posting_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        data = pdf_path.read_bytes()
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{pdf_path.name}"'},
        )

    @app.get("/posting/{posting_id}/cover-letter.pdf")
    async def preset_cover_letter_pdf(posting_id: int):
        """Render the preset pool cover-letter PDF inline. Preset mode only."""
        from ..resume import render_cover_letter_for_posting
        try:
            pdf_path = await render_cover_letter_for_posting(posting_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return Response(
            content=pdf_path.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{pdf_path.name}"'},
        )

    # ─── /run — pipeline operations from the browser ──────────────────────
    @app.get("/run", response_class=HTMLResponse)
    async def run_index(request: Request):
        """Operations panel — buttons for ingest, classify, draft, etc."""
        registry = get_registry()
        return templates.TemplateResponse(
            request,
            "run.html",
            {
                "current": "run",
                "actions": list(ACTIONS.values()),
                "running_jobs": [
                    j.snapshot() for j in registry.list() if j.status == "running"
                ],
                "recent_jobs": [
                    j.snapshot() for j in registry.list()[:8] if j.status != "running"
                ],
            },
        )

    @app.get("/run/{action}", response_class=HTMLResponse)
    async def run_confirm(request: Request, action: str):
        """Confirmation page for any action. Shows what's about to happen +
        cost estimate + a single 'Run it' button. Free actions skip this and
        execute on POST directly."""
        if action not in ACTIONS:
            raise HTTPException(status_code=404, detail=f"unknown action {action!r}")
        ax = ACTIONS[action]
        registry = get_registry()
        already = registry.is_running(action)
        return templates.TemplateResponse(
            request,
            "run_confirm.html",
            {
                "current": "run",
                "action": ax,
                "already_running": already.snapshot() if already else None,
            },
        )

    @app.post("/run/{action}")
    async def run_start(action: str, confirm: str = Form(default="")):
        """Kick off a pipeline action as a background job. Cost-bearing
        actions require `confirm=1` from the confirm page; free actions
        run immediately."""
        if action not in ACTIONS:
            raise HTTPException(status_code=404, detail=f"unknown action {action!r}")
        ax = ACTIONS[action]
        registry = get_registry()

        already = registry.is_running(action)
        if already:
            return RedirectResponse(url=f"/run/job/{already.id}", status_code=303)

        if ax.requires_confirm and confirm != "1":
            raise HTTPException(status_code=400, detail="confirmation required")

        from .run_actions import build_action  # local import keeps cold-path
        try:
            _do = build_action(action)
        except KeyError as e:
            raise HTTPException(status_code=500, detail=f"action {action!r} has no handler") from e

        job = registry.start(action=action, name=ax.title, coro_factory=_do)
        return RedirectResponse(url=f"/run/job/{job.id}", status_code=303)

    @app.get("/run/job/{job_id}", response_class=HTMLResponse)
    async def run_job_status(request: Request, job_id: str):
        registry = get_registry()
        job = registry.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return templates.TemplateResponse(
            request,
            "run_job.html",
            {"current": "run", "job": job.snapshot()},
        )

    @app.get("/about", response_class=HTMLResponse)
    async def about(request: Request):
        return templates.TemplateResponse(
            request,
            "about.html",
            {"current": "about"},
        )

    @app.get("/healthz")
    async def healthz():
        status = await queries.healthcheck()
        return JSONResponse(content=status, status_code=200 if status["ok"] else 503)

    return app
