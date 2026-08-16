"""CLI entry point. Installed as `jfb` via pyproject.

Commands:
  jfb seed load                          Load/refresh company seed data
  jfb ingest sources                     List available ATS sources
  jfb ingest companies [--source X]      List seeded companies
  jfb ingest run --source X --company T  Run one (source, token) pair
  jfb ingest source --source X           Run one source across all its companies
  jfb ingest all                         Run every configured source
  jfb stats                              Show DB-state snapshot
  jfb profile ingest [--path profile]    Chunk + embed profile, aggregate vector
  jfb classify run [--limit N]           Stage-2 regex classifier on un-scored postings
  jfb classify embed [--batch N]         Stage-3 Ollama embeddings for new postings
  jfb classify haiku [--batch N]         Stage-4 Haiku triage on cos-gated candidates
  jfb classify rank                      Recompute final_rank for all live postings
  jfb classify all                       embed → haiku → rank in one shot
  jfb draft one --posting-id N           Draft one application via Sonnet
  jfb draft top [--limit N]              Batch-draft top-N postings by final_rank
  jfb app show --id N                    Print a drafted application for review
  jfb top [--limit N]                    Show top-N postings by final_rank
  jfb web serve [--port 8000]            Launch the tracker UI (FastAPI + HTMX)
  jfb digest preview                     Print today's digest to stdout (no send)
  jfb digest send                        Render + email today's digest via Resend
  jfb portfolio crawl --source K --url U Crawl one portfolio site + embed chunks
  jfb portfolio crawl-all                Crawl limiliminal + 5gcx + vimy
  jfb portfolio github --repo OWNER/REPO Ingest a GitHub repo's README.md
  jfb scrape linkedin                    Playwright LinkedIn search (needs .[browser])
  jfb scrape indeed                      Playwright Indeed Canada search
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

# psycopg3's async pool uses select/socketpair; Windows' default ProactorEventLoop
# doesn't support that cleanly and deadlocks under concurrent pool checkout
# (symptom: `PoolTimeout: couldn't get a connection after 30.00 sec`).
# psycopg's own _compat module points to this fix.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .ats import REGISTRY, available_sources
from .db import aconn, close_pools, conn
from .ingest.orchestrator import run_all, run_one, run_source
from .logging_config import configure_logging
from .seeds.load import load as load_seeds

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Job Finder Bot — personal job-discovery pipeline. The bot drafts, the human submits.",
)
console = Console()

# ────────────────────────────────────────────────────────────────────────────
# seed
# ────────────────────────────────────────────────────────────────────────────

seed_app = typer.Typer(no_args_is_help=True, help="Seed data management.")
app.add_typer(seed_app, name="seed")


@seed_app.command("load")
def seed_load() -> None:
    """Insert or refresh company seeds (idempotent)."""
    configure_logging()
    inserted, updated = load_seeds()
    console.print(f"[green]Seed load complete.[/green] inserted={inserted} updated={updated}")


# ────────────────────────────────────────────────────────────────────────────
# ingest
# ────────────────────────────────────────────────────────────────────────────

ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion commands.")
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("sources")
def ingest_sources() -> None:
    """List available ATS client sources."""
    configure_logging()
    for s in available_sources():
        console.print(f"  • {s}")


@ingest_app.command("companies")
def ingest_companies(
    source: Annotated[str | None, typer.Option(help="Filter by ats_platform")] = None,
) -> None:
    """List seeded companies, optionally filtered by source."""
    configure_logging()
    with conn() as c:
        with c.cursor() as cur:
            if source:
                cur.execute(
                    """
                    SELECT tier, name, ats_platform, ats_token, bg_check_stringency, hq_city
                    FROM companies
                    WHERE active AND ats_platform = %s::ats_platform_enum
                    ORDER BY tier, name
                    """,
                    (source,),
                )
            else:
                cur.execute(
                    """
                    SELECT tier, name, ats_platform, ats_token, bg_check_stringency, hq_city
                    FROM companies WHERE active ORDER BY tier, name
                    """
                )
            rows = cur.fetchall()

    table = Table(title=f"Companies{f' ({source})' if source else ''}")
    for col in ("Tier", "Name", "ATS", "Token", "Check", "City"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r["tier"]),
            r["name"],
            r["ats_platform"],
            r["ats_token"] or "—",
            r["bg_check_stringency"],
            r["hq_city"] or "—",
        )
    console.print(table)


@ingest_app.command("run")
def ingest_run(
    source: Annotated[str, typer.Option(help="ATS source name")],
    company: Annotated[str, typer.Option(help="ats_token for the target")],
) -> None:
    """Run one (source, token) pair end-to-end."""
    configure_logging()
    if source not in REGISTRY:
        raise typer.BadParameter(f"unknown source: {source}")

    async def _go():
        try:
            result = await run_one(source, company)
        finally:
            await close_pools()
        return result

    result = asyncio.run(_go())
    console.print(json.dumps(dataclasses.asdict(result), default=str, indent=2))


@ingest_app.command("source")
def ingest_source_cmd(
    source: Annotated[str, typer.Option(help="ATS source name")],
    concurrency: Annotated[int, typer.Option(help="Max concurrent companies")] = 3,
) -> None:
    """Run one source across every seeded company configured for it."""
    configure_logging()

    async def _go():
        try:
            return await run_source(source, concurrency=concurrency)
        finally:
            await close_pools()

    results = asyncio.run(_go())
    totals = _sum_results(results)
    console.print(f"[green]{source} done[/green] → {totals}")


@ingest_app.command("all")
def ingest_all(
    concurrency: Annotated[int, typer.Option(help="Max concurrent companies per source")] = 3,
) -> None:
    """Run every configured source."""
    configure_logging()

    async def _go():
        try:
            return await run_all(concurrency=concurrency)
        finally:
            await close_pools()

    per_source = asyncio.run(_go())
    for src, results in per_source.items():
        totals = _sum_results(results)
        console.print(f"  {src}: {totals}")


def _sum_results(results) -> dict:
    return {
        "companies": len(results),
        "fetched": sum(r.fetched for r in results),
        "inserted": sum(r.inserted for r in results),
        "updated": sum(r.updated for r in results),
        "dup_skipped": sum(r.dup_skipped for r in results),
        "errors": sum(r.errors for r in results),
    }


# ────────────────────────────────────────────────────────────────────────────
# profile
# ────────────────────────────────────────────────────────────────────────────

profile_app = typer.Typer(no_args_is_help=True, help="Profile ingestion (resume + portfolio).")
app.add_typer(profile_app, name="profile")


@profile_app.command("ingest")
def profile_ingest(
    path: Annotated[Path, typer.Option(help="Path to profile markdown tree")] = Path("profile"),
    label: Annotated[str, typer.Option(help="Identity key for profile_vectors")] = "primary",
    replace: Annotated[bool, typer.Option(help="TRUNCATE portfolio_chunks first")] = True,
) -> None:
    """Chunk every *.md under --path, embed with Ollama, write aggregate vector."""
    configure_logging()
    from .classify.profile import ingest_profile

    async def _go():
        try:
            return await ingest_profile(profile_dir=path, label=label, replace=replace)
        finally:
            await close_pools()

    report = asyncio.run(_go())
    console.print(
        f"[green]Profile ingested.[/green] files={report.files_processed} "
        f"chunks={report.chunks_inserted} aggregate={report.aggregate_written}"
    )


# ────────────────────────────────────────────────────────────────────────────
# portfolio (site crawl — spec §5.1)
# ────────────────────────────────────────────────────────────────────────────

portfolio_app = typer.Typer(
    no_args_is_help=True,
    help="Portfolio-site crawlers (limiliminal / 5gcx / vimy / github).",
)
app.add_typer(portfolio_app, name="portfolio")


@portfolio_app.command("crawl")
def portfolio_crawl(
    source: Annotated[str, typer.Option(help="Source key, e.g. 'limiliminal'")],
    url: Annotated[str, typer.Option(help="Start URL for the crawl")],
    max_pages: Annotated[int, typer.Option(help="Hard cap on pages visited")] = 30,
    delay: Annotated[float, typer.Option(help="Seconds between fetches")] = 0.5,
) -> None:
    """Crawl one portfolio site, chunk, embed, and replace its chunks."""
    configure_logging()
    from .portfolio.ingest import ingest_site

    async def _go():
        try:
            return await ingest_site(source, url, max_pages=max_pages, delay=delay)
        finally:
            await close_pools()

    r = asyncio.run(_go())
    console.print(
        f"[green]{r.source_key}[/green] pages={r.pages_crawled} "
        f"chunks={r.chunks_inserted} errors={r.errors}"
    )


@portfolio_app.command("crawl-all")
def portfolio_crawl_all(
    max_pages: Annotated[int, typer.Option(help="Per-site page cap")] = 30,
    delay: Annotated[float, typer.Option(help="Seconds between fetches")] = 0.5,
) -> None:
    """Crawl every well-known portfolio site (limiliminal / 5gcx / vimy)."""
    configure_logging()
    from .portfolio.ingest import ingest_all

    async def _go():
        try:
            return await ingest_all(max_pages=max_pages, delay=delay)
        finally:
            await close_pools()

    reports = asyncio.run(_go())
    for r in reports:
        console.print(
            f"  {r.source_key:<20} pages={r.pages_crawled} "
            f"chunks={r.chunks_inserted} errors={r.errors}"
        )


@portfolio_app.command("github")
def portfolio_github(
    repo: Annotated[str, typer.Option(help="owner/repo, e.g. 'acme/foo'")],
    ref: Annotated[str, typer.Option(help="Ref to fetch (default HEAD)")] = "HEAD",
) -> None:
    """Fetch a GitHub repo's README.md and store it under 'github:<repo>'."""
    configure_logging()
    from .portfolio.ingest import ingest_github_readme

    async def _go():
        try:
            return await ingest_github_readme(repo, ref=ref)
        finally:
            await close_pools()

    r = asyncio.run(_go())
    console.print(
        f"[green]{r.source_key}[/green] chunks={r.chunks_inserted} errors={r.errors}"
    )


# ────────────────────────────────────────────────────────────────────────────
# classify
# ────────────────────────────────────────────────────────────────────────────

classify_app = typer.Typer(no_args_is_help=True, help="Classification pipeline (Stages 2–4 + rank).")
app.add_typer(classify_app, name="classify")


@classify_app.command("run")
def classify_run(
    limit: Annotated[int, typer.Option(help="Max postings to classify")] = 500,
) -> None:
    """Run the Stage-2 regex classifier against un-scored postings."""
    configure_logging()
    from .classify.regex_pass import classify

    async def _go():
        scored = 0
        try:
            async with aconn() as c:
                async with c.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, title, description_text
                        FROM postings
                        WHERE fit_score IS NULL
                          AND canonical_posting_id IS NULL
                          AND closed_at IS NULL
                        ORDER BY first_seen DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    rows = await cur.fetchall()

                for r in rows:
                    res = classify(r["title"], r["description_text"])
                    async with c.cursor() as cur:
                        await cur.execute(
                            """
                            UPDATE postings
                            SET fit_score = %s,
                                check_risk_score = %s,
                                role_category = %s,
                                strict_hits = %s::jsonb,
                                lenient_hits = %s::jsonb,
                                fit_hits = %s::jsonb
                            WHERE id = %s
                            """,
                            (
                                res.fit_score,
                                res.check_risk_score,
                                res.role_category,
                                json.dumps(res.strict_hits),
                                json.dumps(res.lenient_hits),
                                json.dumps(res.fit_hits),
                                r["id"],
                            ),
                        )
                    scored += 1
                await c.commit()
        finally:
            await close_pools()
        return scored

    n = asyncio.run(_go())
    console.print(f"[green]Classified {n} postings.[/green]")


@classify_app.command("embed")
def classify_embed(
    batch: Annotated[int, typer.Option(help="Postings per embedding batch")] = 32,
    max_batches: Annotated[int, typer.Option(help="Upper bound on batches this run")] = 20,
) -> None:
    """Stage 3: embed any un-embedded live postings via Ollama."""
    configure_logging()
    from .classify.embed_postings import embed_pending

    async def _go():
        try:
            return await embed_pending(batch_size=batch, max_batches=max_batches)
        finally:
            await close_pools()

    report = asyncio.run(_go())
    console.print(
        f"[green]Embedded {report.embedded} postings.[/green] remaining={report.remaining}"
    )


@classify_app.command("haiku")
def classify_haiku(
    batch: Annotated[int, typer.Option(help="Postings per Haiku call")] = 10,
    max_batches: Annotated[int, typer.Option(help="Upper bound on calls this run")] = 10,
    profile_dir: Annotated[Path, typer.Option("--profile-dir", help="Where to find resume/prefs for cached prefix")] = Path("profile"),
) -> None:
    """Stage 4: batched Haiku triage on cos-gated candidates."""
    configure_logging()
    from .classify.haiku import triage_pending

    async def _go():
        try:
            return await triage_pending(
                batch_size=batch, max_batches=max_batches, profile_dir=profile_dir
            )
        finally:
            await close_pools()

    report = asyncio.run(_go())
    console.print(
        f"[green]Haiku done.[/green] batches={report.batches} "
        f"classified={report.classified} gated={report.skipped_gate} errors={report.errors}"
    )


@classify_app.command("rank")
def classify_rank() -> None:
    """Recompute final_rank for every live posting."""
    configure_logging()
    from .classify.rank import rank_all

    async def _go():
        try:
            return await rank_all()
        finally:
            await close_pools()

    report = asyncio.run(_go())
    console.print(
        f"[green]Ranked {report.scored} postings.[/green] "
        f"skipped_missing_scores={report.skipped_missing_scores}"
    )


@classify_app.command("all")
def classify_all(
    profile_dir: Annotated[Path, typer.Option("--profile-dir")] = Path("profile"),
) -> None:
    """Run the full classify pipeline: regex → embed → haiku → rank."""
    configure_logging()
    from .classify.embed_postings import embed_pending
    from .classify.haiku import triage_pending
    from .classify.rank import rank_all
    from .classify.regex_pass import classify as regex_classify

    async def _regex() -> int:
        scored = 0
        async with aconn() as c:
            async with c.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, title, description_text FROM postings
                    WHERE fit_score IS NULL
                      AND canonical_posting_id IS NULL
                      AND closed_at IS NULL
                    ORDER BY first_seen DESC LIMIT 2000
                    """
                )
                rows = await cur.fetchall()
            for r in rows:
                res = regex_classify(r["title"], r["description_text"])
                async with c.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE postings
                        SET fit_score = %s, check_risk_score = %s, role_category = %s,
                            strict_hits = %s::jsonb, lenient_hits = %s::jsonb, fit_hits = %s::jsonb
                        WHERE id = %s
                        """,
                        (
                            res.fit_score,
                            res.check_risk_score,
                            res.role_category,
                            json.dumps(res.strict_hits),
                            json.dumps(res.lenient_hits),
                            json.dumps(res.fit_hits),
                            r["id"],
                        ),
                    )
                scored += 1
            await c.commit()
        return scored

    async def _go():
        try:
            n_regex = await _regex()
            emb = await embed_pending()
            triage = await triage_pending(profile_dir=profile_dir)
            rank = await rank_all()
        finally:
            await close_pools()
        return n_regex, emb, triage, rank

    n_regex, emb, triage, rank = asyncio.run(_go())
    console.print(f"[bold]regex:[/bold]  {n_regex} postings scored")
    console.print(f"[bold]embed:[/bold]  embedded={emb.embedded} remaining={emb.remaining}")
    console.print(
        f"[bold]haiku:[/bold]  batches={triage.batches} classified={triage.classified} "
        f"gated={triage.skipped_gate} errors={triage.errors}"
    )
    console.print(f"[bold]rank:[/bold]   scored={rank.scored} skipped={rank.skipped_missing_scores}")


# ────────────────────────────────────────────────────────────────────────────
# draft (Sprint 3)
# ────────────────────────────────────────────────────────────────────────────

draft_app = typer.Typer(no_args_is_help=True, help="Per-application drafter (Sonnet + RAG).")
app.add_typer(draft_app, name="draft")


@draft_app.command("one")
def draft_one(
    posting_id: Annotated[int, typer.Option("--posting-id", help="Target posting row id")],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Drafting mode override: 'tailor' (paraphrase) or 'curate' (selection-only). "
            "If omitted, uses the application row's stored mode (or settings default for new rows).",
        ),
    ] = "",
    model: Annotated[str, typer.Option(help="Anthropic model id")] = "claude-sonnet-4-6",
    profile_dir: Annotated[Path, typer.Option("--profile-dir")] = Path("profile"),
) -> None:
    """Draft one application for a specific posting."""
    configure_logging()
    from .config import settings
    from .drafter.draft import draft_for_posting

    chosen_mode = mode or settings.draft_mode_default
    if chosen_mode not in ("tailor", "curate"):
        console.print(f"[red]Invalid --mode {mode!r}; expected 'tailor' or 'curate'.[/red]")
        raise typer.Exit(code=2)

    async def _go():
        try:
            return await draft_for_posting(
                posting_id, mode=chosen_mode, model=model, profile_dir=profile_dir,
            )
        finally:
            await close_pools()

    r = asyncio.run(_go())
    console.print(
        f"[green]Drafted application {r.application_id}[/green] "
        f"(posting {r.posting_id}, mode={r.mode}, cache_read={r.cache_read_tokens}, "
        f"usd={round(r.usd_cost, 4)})"
    )


@draft_app.command("top")
def draft_top_cmd(
    limit: Annotated[int, typer.Option(help="How many top postings to draft for")] = 15,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="If set, only draft applications queued in this mode "
            "('tailor' or 'curate'). Default: draft both.",
        ),
    ] = "",
    model: Annotated[str, typer.Option(help="Anthropic model id")] = "claude-sonnet-4-6",
    profile_dir: Annotated[Path, typer.Option("--profile-dir")] = Path("profile"),
) -> None:
    """Draft queued applications. Per-row draft_mode is honoured (set when queued).

    Use `--mode tailor` or `--mode curate` to filter the batch to one mode.
    """
    configure_logging()
    from .drafter.draft import draft_top

    mode_filter: str | None = mode or None
    if mode_filter is not None and mode_filter not in ("tailor", "curate"):
        console.print(f"[red]Invalid --mode {mode!r}; expected 'tailor' or 'curate'.[/red]")
        raise typer.Exit(code=2)

    async def _go():
        try:
            return await draft_top(
                limit=limit, model=model, profile_dir=profile_dir,
                mode_filter=mode_filter,  # type: ignore[arg-type]
            )
        finally:
            await close_pools()

    report = asyncio.run(_go())
    console.print(
        f"[green]Drafted {report.drafted}[/green] errors={report.errors} "
        f"usd_total={round(report.total_cost_usd, 4)}"
    )


# ────────────────────────────────────────────────────────────────────────────
# application review
# ────────────────────────────────────────────────────────────────────────────

resume_app = typer.Typer(no_args_is_help=True, help="Render tailored résumé PDFs from existing draft data ($0 spend).")
app.add_typer(resume_app, name="resume")


@resume_app.command("master")
def resume_master_cmd(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Output PDF path (default: artifacts/resumes/master.pdf)"),
    ] = None,
    profile_dir: Annotated[Path, typer.Option("--profile-dir")] = Path("profile"),
    open_after: Annotated[bool, typer.Option("--open/--no-open")] = True,
) -> None:
    """Render the master profile/resume.md as a PDF (no per-application trimming)."""
    configure_logging()
    from .resume import render_master_pdf

    pdf_path = render_master_pdf(out_path=out, profile_dir=profile_dir)
    size_kb = pdf_path.stat().st_size / 1024
    console.print(f"[green]Wrote {pdf_path}[/green]  ({size_kb:.1f} KB)")
    if open_after:
        import os, sys
        if sys.platform == "win32":
            os.startfile(str(pdf_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{pdf_path}"')
        else:
            os.system(f'xdg-open "{pdf_path}"')


@resume_app.command("render")
def resume_render_cmd(
    posting_id: Annotated[int, typer.Option("--posting-id", help="Target posting row id")],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Output PDF path (default: artifacts/resumes/<slug>.pdf)"),
    ] = None,
    profile_dir: Annotated[Path, typer.Option("--profile-dir")] = Path("profile"),
    open_after: Annotated[
        bool,
        typer.Option("--open/--no-open", help="Open the PDF in the default viewer when done"),
    ] = True,
) -> None:
    """Render a tailored résumé PDF for one posting using existing draft data.

    Pure templating — reads master + curate selection from DB, applies trimming
    and emphasis-bolding, renders to PDF. No LLM calls, no API spend.
    """
    configure_logging()
    from .resume import render_for_posting

    async def _go():
        try:
            return await render_for_posting(posting_id, out_path=out, profile_dir=profile_dir)
        finally:
            await close_pools()

    pdf_path = asyncio.run(_go())
    size_kb = pdf_path.stat().st_size / 1024
    console.print(f"[green]Wrote {pdf_path}[/green]  ({size_kb:.1f} KB)")
    if open_after:
        import os, sys
        if sys.platform == "win32":
            os.startfile(str(pdf_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{pdf_path}"')
        else:
            os.system(f'xdg-open "{pdf_path}"')


app_subcmd = typer.Typer(no_args_is_help=True, help="Review drafted applications.")
app.add_typer(app_subcmd, name="app")


@app_subcmd.command("show")
def app_show(
    id: Annotated[int, typer.Option("--id", help="applications.id to show")],
) -> None:
    """Print a drafted application in a form you can paste into a submission."""
    configure_logging()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.status, a.drafted_at, a.cover_letter,
                       a.tailored_bullets, a.talking_points, a.red_flags,
                       p.title, p.url_canonical, p.location,
                       c.name AS company
                FROM applications a
                JOIN postings p ON p.id = a.posting_id
                JOIN companies c ON c.id = p.company_id
                WHERE a.id = %s
                """,
                (id,),
            )
            row = cur.fetchone()
    if not row:
        console.print(f"[red]No application with id={id}[/red]")
        raise typer.Exit(code=1)

    console.rule(f"application {row['id']} · {row['status']}")
    console.print(f"[bold]{row['company']}[/bold] — {row['title']}")
    console.print(f"[dim]{row['url_canonical']}[/dim]")
    console.print(f"Drafted: {row['drafted_at']}    Location: {row['location'] or '—'}")
    console.print()

    console.rule("cover letter")
    console.print(row["cover_letter"] or "(empty)")
    console.print()

    console.rule("tailored bullets")
    for b in row["tailored_bullets"] or []:
        console.print(f"  • [{b.get('section', '?')}] {b.get('bullet', '')}")
    console.print()

    console.rule("talking points")
    for tp in row["talking_points"] or []:
        console.print(f"  • {tp}")
    console.print()

    console.rule("red flags")
    for rf in row["red_flags"] or []:
        console.print(f"  [yellow]⚠[/yellow] {rf}")


# ────────────────────────────────────────────────────────────────────────────
# stats + top
# ────────────────────────────────────────────────────────────────────────────


@app.command("stats")
def stats() -> None:
    """DB-state snapshot: counts by table, by source, by stringency."""
    configure_logging()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM companies WHERE active")
            n_companies = cur.fetchone()["n"]

            cur.execute("SELECT count(*) AS n FROM postings WHERE canonical_posting_id IS NULL")
            n_postings = cur.fetchone()["n"]

            cur.execute(
                "SELECT count(*) AS n FROM postings WHERE fit_score IS NOT NULL "
                "AND canonical_posting_id IS NULL"
            )
            n_scored = cur.fetchone()["n"]

            cur.execute(
                """
                SELECT source, count(*) AS n FROM postings
                WHERE canonical_posting_id IS NULL
                GROUP BY source ORDER BY n DESC
                """
            )
            by_source = cur.fetchall()

            cur.execute(
                """
                SELECT c.bg_check_stringency, count(*) AS n
                FROM postings p JOIN companies c ON c.id = p.company_id
                WHERE p.canonical_posting_id IS NULL
                GROUP BY 1 ORDER BY n DESC
                """
            )
            by_stringency = cur.fetchall()

    console.print(f"[bold]Companies:[/bold] {n_companies}")
    console.print(f"[bold]Postings:[/bold] {n_postings}   [dim](classified: {n_scored})[/dim]")
    console.print("")
    console.print("[bold]By source:[/bold]")
    for r in by_source:
        console.print(f"  {r['source']:<20} {r['n']}")
    console.print("")
    console.print("[bold]By bg-check stringency:[/bold]")
    for r in by_stringency:
        console.print(f"  {r['bg_check_stringency']:<15} {r['n']}")


@app.command("top")
def top(
    limit: Annotated[int, typer.Option(help="How many rows")] = 20,
) -> None:
    """Show top-N postings by final_rank (post-classification)."""
    configure_logging()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.title, c.name AS company, p.location,
                       p.fit_score, p.check_risk_score, p.final_rank,
                       p.url_canonical
                FROM postings p JOIN companies c ON c.id = p.company_id
                WHERE p.canonical_posting_id IS NULL
                  AND p.closed_at IS NULL
                  AND p.fit_score IS NOT NULL
                ORDER BY p.final_rank DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    table = Table(title=f"Top {limit} postings by final_rank")
    for col in ("Rank", "Fit", "Check", "Company", "Title", "Location"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            f"{r['final_rank']:.3f}" if r["final_rank"] else "—",
            f"{r['fit_score']:.2f}" if r["fit_score"] else "—",
            f"{r['check_risk_score']:.2f}" if r["check_risk_score"] else "—",
            r["company"],
            r["title"][:60],
            (r["location"] or "—")[:30],
        )
    console.print(table)


# ────────────────────────────────────────────────────────────────────────────
# scrape (Sprint 5, opt-in: requires `.[browser]`)
# ────────────────────────────────────────────────────────────────────────────

scrape_app = typer.Typer(
    no_args_is_help=True,
    help="Playwright scrapers (LinkedIn/Indeed). Requires `pip install -e '.[browser]'`.",
)
app.add_typer(scrape_app, name="scrape")


@scrape_app.command("linkedin")
def scrape_linkedin(
    keyword: Annotated[list[str], typer.Option(help="Keyword(s); repeatable")] = [],
    location: Annotated[list[str], typer.Option(help="Location(s); repeatable")] = [],
    max_per_spec: Annotated[int, typer.Option(help="Max postings per (kw, loc) pair")] = 25,
) -> None:
    """Run the LinkedIn public-jobs scraper.

    With no keywords/locations, uses defaults from `scrape.linkedin`.
    """
    configure_logging()
    from .scrape.harness import MissingBrowserDep
    from .scrape.linkedin import SearchSpec, search_public

    specs: list[SearchSpec] | None = None
    if keyword or location:
        kws = keyword or [""]
        locs = location or [""]
        specs = [SearchSpec(keyword=k, location=loc) for k in kws for loc in locs]

    async def _go():
        try:
            return await search_public(specs, max_per_spec=max_per_spec)
        finally:
            await close_pools()

    try:
        out = asyncio.run(_go())
    except MissingBrowserDep as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]LinkedIn:[/green] {len(out)} postings captured")


@scrape_app.command("indeed")
def scrape_indeed(
    keyword: Annotated[list[str], typer.Option(help="Keyword(s); repeatable")] = [],
    location: Annotated[list[str], typer.Option(help="Location(s); repeatable")] = [],
    max_per_spec: Annotated[int, typer.Option(help="Max postings per (kw, loc) pair")] = 25,
) -> None:
    """Run the Indeed Canada scraper."""
    configure_logging()
    from .scrape.harness import MissingBrowserDep
    from .scrape.indeed import SearchSpec, search_canada

    specs: list[SearchSpec] | None = None
    if keyword or location:
        kws = keyword or [""]
        locs = location or [""]
        specs = [SearchSpec(keyword=k, location=loc) for k in kws for loc in locs]

    async def _go():
        try:
            return await search_canada(specs, max_per_spec=max_per_spec)
        finally:
            await close_pools()

    try:
        out = asyncio.run(_go())
    except MissingBrowserDep as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Indeed:[/green] {len(out)} postings captured")


# ────────────────────────────────────────────────────────────────────────────
# web (tracker UI) — Sprint 4
# ────────────────────────────────────────────────────────────────────────────

web_app = typer.Typer(no_args_is_help=True, help="Tracker UI (FastAPI + HTMX).")
app.add_typer(web_app, name="web")


@web_app.command("serve")
def web_serve(
    host: Annotated[str, typer.Option(help="Interface to bind")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 8000,
    reload: Annotated[bool, typer.Option(help="Auto-reload on source change")] = False,
) -> None:
    """Run the FastAPI tracker UI via uvicorn.

    Windows note: psycopg's async pool can't run on the ProactorEventLoop
    that uvicorn defaults to on Windows. We pre-set
    `WindowsSelectorEventLoopPolicy`, then override uvicorn's
    `setup_event_loop` so it doesn't clobber our policy at startup.
    """
    configure_logging()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    config = uvicorn.Config(
        "job_finder.ui.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_config=None,  # defer to structlog
        loop="asyncio",
    )

    if sys.platform == "win32":
        # Uvicorn's `asyncio_setup` forcibly installs WindowsProactorEventLoopPolicy
        # whenever loop="asyncio" on Windows. Neuter it so our SelectorEventLoop
        # policy stays in place for the run.
        config.setup_event_loop = lambda: None  # type: ignore[method-assign]

    server = uvicorn.Server(config)
    asyncio.run(server.serve())


# ────────────────────────────────────────────────────────────────────────────
# digest — Sprint 4
# ────────────────────────────────────────────────────────────────────────────

digest_app = typer.Typer(no_args_is_help=True, help="Daily digest (Resend).")
app.add_typer(digest_app, name="digest")


@digest_app.command("preview")
def digest_preview() -> None:
    """Build today's digest and print the plaintext rendering — no email sent."""
    configure_logging()
    from .notify.digest import build_digest, render_subject, render_text

    async def _go():
        try:
            return await build_digest()
        finally:
            await close_pools()

    d = asyncio.run(_go())
    console.rule(render_subject(d))
    console.print(render_text(d))


@digest_app.command("send")
def digest_send() -> None:
    """Build and send today's digest via Resend."""
    configure_logging()
    from .notify.digest import build_digest, render_subject, send_digest

    async def _go():
        try:
            return await build_digest()
        finally:
            await close_pools()

    d = asyncio.run(_go())
    try:
        resp = send_digest(d)
    except RuntimeError as e:
        console.print(f"[red]digest send aborted:[/red] {e}")
        raise typer.Exit(code=1)
    console.print(f"[green]Digest sent:[/green] {render_subject(d)}")
    if isinstance(resp, dict) and resp.get("id"):
        console.print(f"[dim]resend_id={resp['id']}[/dim]")


if __name__ == "__main__":
    app()
