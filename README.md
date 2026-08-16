# Job Finder Bot

Personal job-discovery pipeline for Toronto/Montreal tech search. Ingests from ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday), classifies postings against a personal profile, and drafts tailored application materials.

**The bot drafts, the human submits.** See [`docs/job_finder_bot_spec.md`](docs/job_finder_bot_spec.md) §0 for why this matters and do not remove that constraint. Deep-research backing is in [`docs/deep_research.md`](docs/deep_research.md).

**Want to run it locally?** See [`docs/running_locally.md`](docs/running_locally.md) for setup and day-to-day start/stop steps.

---

## Prerequisites

- Python 3.12+
- Docker + Docker Compose (for Postgres)
- [`uv`](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- (Sprint 2+) [Ollama](https://ollama.com) for local embeddings
- (Sprint 2+) Anthropic API key

---

## Quickstart

For local setup and running the UI, use **[`docs/running_locally.md`](docs/running_locally.md)**.

Development bootstrap (Linux/macOS with `make`):

```bash
cp .env.example .env         # fill in values (or leave blank for Sprint 0/1)
make bootstrap                # install + start postgres + migrate + seed companies
make ingest-one               # fetch Cohere's postings as a smoke test
make stats                    # check DB state
make ingest-all               # fetch all configured companies
```

---

## Project layout

```
job-finder-bot/
├── migrations/                  Alembic schema migrations
├── src/job_finder/
│   ├── config.py                env-backed settings
│   ├── db.py                    psycopg connection pool
│   ├── models.py                Pydantic models (RawPosting)
│   ├── cli.py                   Typer entry point (`jfb ...`)
│   ├── ranking.py               final_rank() composite scorer
│   ├── utils/                   URL canon, title hashing, HTML strip
│   ├── ats/                     One client per ATS platform
│   ├── ingest/                  Orchestrator + non-ATS sources
│   ├── classify/                Keywords + regex + embeddings + Haiku
│   ├── drafter/                 Per-application RAG + Sonnet draft
│   ├── llm/                     Anthropic client + cost logging
│   ├── ui/                      FastAPI + HTMX tracker UI
│   ├── notify/                  Daily digest (Resend) + related helpers
│   ├── portfolio/               Portfolio-site crawl + chunk + embed
│   ├── scrape/                  Playwright harness + LinkedIn/Indeed skeletons (opt-in)
│   ├── metrics.py               Fire-and-forget metric_events helper
│   └── seeds/                   Target company list
├── profile/                     Resume + portfolio (user-provided)
├── systemd/                     Example timer units
└── tests/
```

Sprint-2 flow:

```bash
ollama pull nomic-embed-text:v1.5   # once
cp profile/resume.example.md  profile/resume.md
cp profile/prefs.example.md   profile/prefs.md
# ... edit those files to be about you ...
jfb profile ingest                  # chunks + embeds your profile
jfb classify all                    # regex → embed → haiku → rank
jfb top --limit 30
```

Sprint-3 flow (per-application drafting):

```bash
jfb draft top --limit 15            # batch-draft top-15 by final_rank (cached system)
jfb draft one --posting-id 12345    # or draft a single posting
jfb app show --id 42                # print a draft for copy-paste into the submission
```

The bot writes `applications.status = 'ready_for_human'` on every draft —
you still submit. See `docs/job_finder_bot_spec.md` §0 for why this line
never moves.

Sprint-4 flow (tracker UI + digest):

```bash
jfb web serve --port 8000           # kanban + posting detail + /healthz
# open http://localhost:8000  (HTMX, no SPA; dark theme)
# → click "Mark as applied" on a posting — that's the ONLY path that sets applied_at

jfb digest preview                  # render today's digest to stdout
jfb digest send                     # email it via Resend (needs RESEND_API_KEY + RESEND_TO)
```

Metric events (`metric_events`) are written from every long-running step —
ingest, classify.haiku, rank, draft.done, application.applied — and rolled
up in the `v_daily_metrics` materialized view for the `/metrics` dashboard.

Sprint-5 flow (portfolio + opt-in scrapers + systemd):

```bash
jfb portfolio crawl-all                    # crawl limiliminal.com / 5gcx.ai / vimy.ai
jfb portfolio crawl --source vimy --url https://vimy.ai   # one site
jfb portfolio github --repo myorg/myrepo   # ingest a single GH README

# Opt-in browser scrapers (require `.[browser]`):
uv pip install -e '.[browser]' && uv run playwright install chromium
jfb scrape linkedin --keyword "ml engineer" --location "Toronto, ON"
jfb scrape indeed   --keyword "graphics"   --location "Montreal, QC"
```

The LinkedIn / Indeed parsers ship as **skeletons** — URL builders, CAPTCHA
detection, and a stealth-lite Chromium harness are pinned and tested, but
`_parse_results_page()` returns `[]` until you verify current DOM selectors.
The rest of the pipeline (dedup, classify, rank, draft) works unchanged.

See `systemd/` for service+timer examples:
  - `example-ingest.service` — hourly ATS ingest
  - `example-classify.service` — 2h classify pipeline
  - `example-draft.service` — 02:10 nightly batch drafter
  - `example-digest.service` — 07:00 daily Resend email
  - `example-portfolio.service` — monthly portfolio recrawl

---

## Sprint status (relative to SPEC.md)

| Sprint | Area | State |
|---|---|---|
| 0 | Foundation (schema, config, CLI) | ✅ Done |
| 1 | Ingestion (ATS clients) | ✅ Greenhouse / Lever / Ashby / SmartRecruiters / Workable / HN; 🟡 Workday + Eightfold stubs with per-tenant implementation notes |
| 2 | Classification (regex + embeddings + Haiku) | ✅ Stages 1–4 + final_rank; profile ingest via `jfb profile ingest` |
| 3 | Drafter (RAG + Sonnet) | ✅ Per-posting + batched; cached system prefix; `jfb draft one/top`, `jfb app show` |
| 4 | Tracker UI + monitoring | ✅ FastAPI + HTMX kanban, `/healthz`, Sentry, `v_daily_metrics`, Resend digest |
| 5 | Portfolio crawl + Playwright skeletons + systemd | ✅ Portfolio (`jfb portfolio`), scrape skeletons (`jfb scrape`), 5 timer examples |

---

## Operating notes

- All ATS clients are async and respect rate limits via `tenacity`.
- Dedup is handled by `title_company_hash` (partial unique index) + later by pgvector cosine.
- The `companies` table ships with ~45 seeded targets in four tiers. `tier=1` is apply-immediately.
- `check_risk_score` and `final_rank` are computed post-ingestion by the classifier (Sprint 2).

---

## License

Personal use. Not for redistribution.
