# Job-Finder Bot — Implementation Spec for Claude Code

> **Who this is for**: Claude Code (or any coding agent) building a personal job-discovery pipeline for a Toronto/Montreal tech search.
> **Scope**: discover → classify → rank → draft. **Do NOT auto-submit** (see §0 for why).
> **Target runtime**: single developer machine or small VPS. Two-month useful life. Optimize for speed-to-first-useful-output, not scale.

---

## 0. Non-negotiable constraint: the bot drafts, the human submits

The operator has a legal situation in which different employer consent-form questions ("Have you ever been convicted?" vs. "Have you ever been charged?") have materially different legally-correct answers. A silent auto-submitter that fills either question with a canned value is capable of producing a legal misrepresentation that destroys downstream defence strategy.

**Therefore, the application-submission step must always route through a human confirmation in the tracker UI.** The bot's job ends at "drafted cover letter + tailored resume + consent-form screenshot flagged for review." Every implementation ticket below assumes this boundary.

There is one exception: draft-save actions on ATS platforms that expose a draft API (Greenhouse Harvest API with candidate token) are acceptable because they do not constitute submission. Verify before implementing.

---

## 1. Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12 | Best LLM SDK ecosystem, Playwright maturity |
| Package manager | `uv` | Fast, reproducible |
| DB | Postgres 16 + `pgvector` + `pg_trgm` + `citext` | Single store for relational + embeddings + fuzzy text |
| Embeddings | Ollama `nomic-embed-text-v1.5` (768-dim) | Free, local, good enough for dedup + retrieval |
| LLM classification | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) batched 10/call | Cheap structured extraction |
| LLM drafting | Claude Opus 4.7 (`claude-opus-4-7`) or Sonnet 4.6 (`claude-sonnet-4-6`) with prompt caching | Quality matters for tailored cover letters; cache kills cost |
| Browser automation | Playwright (Chromium) | Only when ATS JSON unavailable |
| HTTP | `httpx` async | Connection pooling, HTTP/2 |
| Scheduling | `systemd` timers (Linux) / `launchd` (macOS) | Zero extra infra vs. Airflow/Temporal |
| Work queue | Postgres `FOR UPDATE SKIP LOCKED` | No Redis needed at this scale |
| UI | FastAPI + HTMX + Jinja2 | Kanban tracker in <500 LOC |
| Email | Resend free tier (3k/mo) | Daily digest |
| Errors | Sentry free tier (5k events/mo) | |
| Proxies | Decodo residential PAYG (~$2/GB) | Only for LinkedIn/Indeed/Glassdoor |

**Dependencies to install (`pyproject.toml`)**: `anthropic`, `httpx`, `playwright`, `psycopg[binary,pool]`, `pgvector`, `pydantic`, `pydantic-settings`, `structlog`, `selectolax`, `typer`, `tenacity`, `ollama`, `feedparser`, `sentry-sdk`, `resend`, `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `weasyprint` (or `typst` via subprocess).

---

## 2. Database schema

Apply as the initial migration. Every field below is load-bearing — do not trim.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE remote_type_enum AS ENUM ('remote','hybrid','onsite','unspecified');
CREATE TYPE bg_stringency_enum AS ENUM ('unknown','lenient','moderate','strict','very_strict');
CREATE TYPE ats_platform_enum AS ENUM (
    'greenhouse','lever','ashby','workable','workday',
    'bamboohr','smartrecruiters','recruitee','icims','taleo',
    'eightfold','custom','linkedin','indeed','hn','remote_board','unknown'
);
CREATE TYPE application_status_enum AS ENUM (
    'queued','drafted','ready_for_human','applied',
    'acknowledged','phone','onsite','offer','rejected','withdrawn'
);

CREATE TABLE companies (
    id BIGSERIAL PRIMARY KEY,
    name CITEXT NOT NULL,
    domain CITEXT,
    ats_platform ats_platform_enum NOT NULL DEFAULT 'unknown',
    ats_token TEXT,                      -- e.g. Greenhouse board token, Lever company slug
    careers_url TEXT,
    bg_check_stringency bg_stringency_enum NOT NULL DEFAULT 'unknown',
    bg_check_reasoning TEXT,             -- why this stringency; human editable
    hq_city TEXT,
    hq_province TEXT,                    -- 'ON'/'QC' matters for legal ranking
    headcount_est INT,
    tier SMALLINT,                       -- 1..4 from target list
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, domain)
);
CREATE INDEX idx_companies_tier ON companies(tier) WHERE active;

CREATE TABLE postings (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,      -- lowercased, seniority/location stripped
    url_canonical TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,                -- 'greenhouse','lever','hn',...
    source_rank SMALLINT NOT NULL DEFAULT 5,  -- lower = more authoritative
    raw_json JSONB NOT NULL,             -- full original payload
    description_text TEXT NOT NULL,      -- HTML-stripped body
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    reposted_count INT NOT NULL DEFAULT 0,
    canonical_posting_id BIGINT REFERENCES postings(id),  -- set if this is a dupe
    remote_type remote_type_enum NOT NULL DEFAULT 'unspecified',
    location TEXT,
    seniority TEXT,                      -- 'intern','junior','mid','senior','staff','principal'
    salary_min INT,
    salary_max INT,
    salary_currency CHAR(3) DEFAULT 'CAD',
    tech_stack TEXT[],                   -- normalized tokens
    role_category TEXT,                  -- 'web','backend','graphics','games','systems','ml','security','mobile','devops'
    fit_score REAL,                      -- 0..1
    check_risk_score REAL,               -- 0..1, higher = more stringent check expected
    final_rank REAL,                     -- composite; see §5
    strict_hits JSONB,                   -- which strict keywords matched
    lenient_hits JSONB,
    fit_hits JSONB,
    title_company_hash CHAR(40) NOT NULL -- sha1(normalized_title + '::' + lower(company.name))
);
CREATE UNIQUE INDEX idx_postings_tch_live ON postings(title_company_hash)
    WHERE canonical_posting_id IS NULL AND closed_at IS NULL;
CREATE INDEX idx_postings_final_rank ON postings(final_rank DESC NULLS LAST)
    WHERE closed_at IS NULL AND canonical_posting_id IS NULL;
CREATE INDEX idx_postings_first_seen ON postings(first_seen DESC);
CREATE INDEX idx_postings_company ON postings(company_id);

CREATE TABLE posting_embeddings (
    posting_id BIGINT PRIMARY KEY REFERENCES postings(id) ON DELETE CASCADE,
    embedding vector(768) NOT NULL,
    model TEXT NOT NULL DEFAULT 'nomic-embed-text-v1.5',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_posting_emb_hnsw ON posting_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

CREATE TABLE applications (
    id BIGSERIAL PRIMARY KEY,
    posting_id BIGINT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    status application_status_enum NOT NULL DEFAULT 'queued',
    drafted_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    resume_version_id BIGINT,
    cover_letter TEXT,
    tailored_bullets JSONB,              -- array of {section, bullet}
    talking_points JSONB,                -- array of strings
    red_flags JSONB,                     -- array of strings flagged by LLM
    consent_form_notes TEXT,             -- human annotation after review
    tracking_notes TEXT,
    next_action_at TIMESTAMPTZ,
    referrer_email TEXT,
    referrer_name TEXT,
    submission_channel TEXT,             -- 'ats_direct','linkedin_easy_apply','email','referral'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_applications_posting ON applications(posting_id);
CREATE INDEX idx_applications_status ON applications(status);

CREATE TABLE resume_versions (
    id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL,                 -- 'web','graphics','systems_5g','ml_graphics','generic'
    template_path TEXT NOT NULL,
    rendered_pdf_path TEXT,
    payload JSONB NOT NULL,              -- structured resume content
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE portfolio_chunks (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                -- 'limiliminal','5gcx','vimy','github:<repo>','resume'
    project TEXT,                        -- project name within source
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                                         -- {skills:[], role_lanes:[], quantified:bool}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pchunks_emb_hnsw ON portfolio_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
CREATE INDEX idx_pchunks_source ON portfolio_chunks(source);

CREATE TABLE metric_events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL DEFAULT 1,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_metric_ts ON metric_events(metric, ts DESC);

CREATE TABLE llm_cost_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    model TEXT NOT NULL,
    operation TEXT NOT NULL,             -- 'classify','draft','embed'
    input_tokens INT,
    output_tokens INT,
    cache_read_tokens INT,
    cache_write_tokens INT,
    usd_cost NUMERIC(10,6)
);
```

**Work-queue pattern** — use this everywhere you fan work out to workers; do not add Redis:

```sql
-- Claim next posting to classify
UPDATE postings SET last_seen = now()
WHERE id = (
  SELECT id FROM postings
  WHERE fit_score IS NULL AND canonical_posting_id IS NULL
  ORDER BY first_seen ASC
  LIMIT 1 FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

---

## 3. Ingestion — ATS endpoints (the core asset)

Polling cadences assume the bot runs continuously. All endpoints below are **public / no-auth** unless noted. Send realistic headers (`User-Agent`, `Accept: application/json`, `Accept-Language: en-CA,en;q=0.9`) from every client.

| ATS | Endpoint | Auth | Cadence | Stability | Example companies |
|---|---|---|---|---|---|
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | None | 1h | Very stable | Cohere, Ada, League, Tenstorrent, Clearco, Lightspeed, Borrowell, Faire, Haven, Coveo |
| Lever | `GET https://api.lever.co/v0/postings/{company}?mode=json` | None (v0) | 1h | Stable | Waabi, BenchSci, Jane, Neo Financial, Behaviour, Moment Factory |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true` | None | 1h | Stable | Wealthsimple, 1Password, KOHO, Hopper, Shopify, Float |
| SmartRecruiters | `GET https://api.smartrecruiters.com/v1/companies/{companyId}/postings?city=Toronto` | None for GET | 2h | OpenAPI-documented | Ubisoft, Klick, Geotab, Rodeo FX, Don't Nod |
| Workable | `GET https://apply.workable.com/api/v1/widget/accounts/{company}` | None | 4h | Stable | Snowed In, Nuvei, Sangoma, Mila, Botpress |
| Recruitee | `GET https://{company}.recruitee.com/api/offers/` | None | 4h | Stable | various scale-ups |
| Workday | `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}` | None | 2–4h | Tenant-specific; headers matter | RBC, TD/Layer 6, Bell, TELUS, Autodesk, NVIDIA, Ciena, Nokia, CGI, EA, ServiceNow |
| Eightfold | `POST https://{company}.eightfold.ai/api/apply/v2/jobs?domain={company}.com&start=0&num=50` | None | 2h | Stable | Ericsson |

**Non-ATS sources** (all free or free-tier):

| Source | Endpoint | Notes |
|---|---|---|
| HN Who-is-Hiring | `https://hn.algolia.com/api/v1/items/{thread_id}` | 10k req/h, no auth. Scrape once per month. |
| Remote OK | `https://remoteok.com/api` | Attribution required in UI |
| We Work Remotely | RSS | `https://weworkremotely.com/remote-jobs.rss` |
| Remotive | `https://remotive.com/api/remote-jobs` | |
| Adzuna CA | `https://api.adzuna.com/v1/api/jobs/ca/search/1?app_id=...&app_key=...` | Free dev tier |
| Jooble | `POST https://jooble.org/api/{key}` JSON body | |
| Job Bank Canada | Monthly CSV at open.canada.ca | Low signal but free |

**Do not start with** LinkedIn, Indeed, or Glassdoor. They require Playwright + residential proxies + anti-bot work, and the ATS tier above already covers ~70% of Toronto/Montreal tech postings. Add Playwright scrapers only after ATS tier is fully landed and a gap is identified.

**Canonical posting shape** (every ingester normalizes to this before DB insert):

```python
class RawPosting(BaseModel):
    source: Literal['greenhouse','lever','ashby','smartrecruiters','workable',
                    'recruitee','workday','eightfold','hn','remote_ok',
                    'wwr','remotive','adzuna','jooble','linkedin','indeed','custom']
    source_rank: int = 5                # 1=ATS direct, 3=aggregator, 5=scraped board
    external_id: str                    # whatever the source calls it
    company_name: str
    company_domain: str | None = None
    title: str
    description_html: str
    description_text: str                # pre-stripped, no HTML
    location_raw: str | None = None
    remote_raw: str | None = None
    posted_at: datetime | None = None
    url_canonical: str                   # after UTM/session strip
    raw_json: dict                       # source payload for forensics
```

**Idempotent upsert key**: `url_canonical`. On conflict, update `last_seen`, `reposted_count += 1`.

---

## 4. Classification — NLP signals

### 4.1 Keyword taxonomies

**Strict-check keywords** (every match adds to `check_risk_score`; multi-match is superlinear):

```python
STRICT_KEYWORDS = {
    # Government / defence (highest weight 1.0)
    "public trust clearance": 1.0, "reliability status": 1.0,
    "secret clearance": 1.0, "top secret": 1.0,
    "canadian citizen required": 0.9, "canadian citizenship required": 0.9,
    "controlled goods program": 1.0, "cgp": 0.6,
    "itar": 1.0, "ear": 0.7, "export control": 0.7,
    "csis": 1.0, "cse": 0.9, "dnd": 0.8, "pspc": 0.7,
    # Financial services (weight 0.7)
    "soc 2": 0.5, "soc2": 0.5, "pci-dss": 0.8, "pci dss": 0.8,
    "osfi-regulated": 0.9, "osfi": 0.7,
    "bondable": 0.9, "fintrac": 0.8, "iiroc": 0.8,
    "aml/kyc": 0.6, "anti-money laundering": 0.6,
    # Healthcare / vulnerable (weight 0.8)
    "vulnerable sector check": 1.0, "vulnerable sector": 0.9,
    "phipa": 0.7, "hipaa": 0.6,
    "working with minors": 1.0, "working with children": 1.0,
    # Generic elevated
    "fingerprint check": 1.0, "fingerprints required": 1.0,
    "enhanced police check": 0.9, "enhanced background check": 0.8,
    "credit check required": 0.8,
    "sterling": 0.3, "hireright": 0.3, "checkr enhanced": 0.6,
    "7-year employment verification": 0.5,
    "background check required": 0.4,   # generic, weak signal alone
}

LENIENT_KEYWORDS = {
    "founding engineer": 0.6, "seed stage": 0.5, "seed-stage": 0.5,
    "y combinator": 0.4, "yc-backed": 0.4,
    "bootstrapped": 0.5, "open source": 0.3,
    "we contribute upstream": 0.4, "async-first": 0.3,
    "no clearance": 0.8, "no security clearance": 0.8,
    "contract": 0.5, "freelance": 0.6, "1099": 0.5,
    "certn basic": 0.9,
}

FIT_KEYWORDS = {  # for role_category + fit_score
    # 5G / networking (weight 3.0)
    "5g": 3.0, "oran": 3.0, "o-ran": 3.0, "ran": 2.5, "lte": 2.0,
    "network function": 2.5, "p4 programming": 2.5,
    "dpdk": 2.5, "sdn": 2.0, "nfv": 2.0, "srv6": 2.0,
    # Graphics / rendering (weight 3.0)
    "opengl": 3.0, "webgl": 3.0, "webgpu": 3.5, "vulkan": 3.0,
    "directx": 2.5, "metal api": 2.5, "shader": 3.0, "glsl": 3.0, "hlsl": 3.0,
    "raytracing": 3.0, "ray tracing": 3.0, "path tracing": 3.0,
    "rasterization": 2.5, "real-time rendering": 3.0,
    "gaussian splatting": 3.5, "nerf": 3.0, "neural rendering": 3.5,
    # ML for graphics (weight 3.5)
    "diffusion": 2.5, "gen ai": 2.0, "generative": 2.0,
    "pytorch": 2.0, "cuda": 2.5, "triton": 2.0,
    # Systems / CompE (weight 2.5)
    "c++": 2.5, "rust": 2.5, "systems programming": 2.5,
    "embedded": 2.0, "firmware": 2.0, "fpga": 2.5,
    "compiler": 2.5, "llvm": 2.5, "linker": 2.0,
    # Games (weight 2.5)
    "unreal engine": 2.5, "unreal": 2.5, "unity": 2.5,
    "game engine": 2.5, "gameplay programmer": 2.5,
    # Web (weight 1.5)
    "typescript": 1.5, "react": 1.5, "next.js": 1.5,
    "tailwind": 1.0, "node.js": 1.5,
}

ANTI_KEYWORDS = {   # -2.0 each
    "wordpress", "php developer", "cobol", "mainframe",
    "sharepoint administrator", "sap consultant",
    "salesforce administrator", "rpa developer",
}
```

### 4.2 Classifier pipeline (4 stages, LLM is last)

```
raw_posting
  → (1) HTML strip + boilerplate removal       [~2ms, free]
      - Strip <script>, <style>, nav/footer classes
      - Collapse whitespace, keep paragraph breaks
  → (2) Regex/keyword pass                      [~5ms, free]
      - Tokenize case-insensitive
      - Compute raw strict_hits, lenient_hits, fit_hits, anti_hits
      - Short-circuit drop if anti_hits > 1 AND fit_hits == 0
  → (3) Embedding + cosine vs. profile vector   [~50ms, free local Ollama]
      - Skip Haiku if cos < 0.35 AND fit_hits < 2  (likely non-fit)
  → (4) Haiku 4.5 batched (10 postings/call)   [~$0.0003/posting]
      - Structured extraction: seniority, salary (min/max/currency),
        remote_type, location_normalized, tech_stack[],
        role_category, fit_score_refined, check_risk_refined
      - JSON response_format enforced
```

**Why this order**: regex kills obvious non-fits for free; embeddings kill near-misses for free; the LLM only sees candidates worth real token spend. At 500 postings/day this costs ~$0.40/day in Claude tokens.

### 4.3 Composite scoring

```python
def final_rank(p: Posting, now: datetime) -> float:
    freshness = math.exp(-hours_since(p.first_seen) / 72)   # half-life ~2 days
    salary_factor = (
        1.2 if (p.salary_min or 0) >= 130_000 else
        1.0 if (p.salary_min or 0) >= 90_000 else
        0.85
    )
    remote_flex = {'remote':1.1,'hybrid':1.05,'onsite':1.0,'unspecified':0.95}[p.remote_type]
    location_match = 1.0 if p.in_toronto_or_montreal_or_remote_canada else 0.3
    qc_bonus = 1.08 if p.company.hq_province == 'QC' else 1.0   # s.18.2 legal advantage
    return (
        p.fit_score
        * (1 - 0.6 * p.check_risk_score)
        * freshness
        * salary_factor
        * remote_flex
        * location_match
        * qc_bonus
    )
```

The `qc_bonus` and the `check_risk_score` discount reflect the operator's specific legal posture — do not remove them when adapting the bot for others.

### 4.4 Haiku batched classifier prompt

System (cached once per batch):

```
You extract structured fields from tech job postings for a personal job-search tool.
Respond with JSON matching the provided schema. No prose. No markdown fences.
For each posting, produce:
- seniority: "intern"|"junior"|"mid"|"senior"|"staff"|"principal"|"unknown"
- salary: {min:int|null, max:int|null, currency:"CAD"|"USD"|null}
- remote_type: "remote"|"hybrid"|"onsite"|"unspecified"
- location_normalized: e.g. "Toronto, ON" or "Montreal, QC" or "Remote Canada"
- tech_stack: array of normalized tokens (e.g. ["typescript","react","postgres"])
- role_category: "web"|"backend"|"graphics"|"games"|"systems"|"ml"|"5g_networking"|"security"|"mobile"|"devops"|"other"
- fit_score: 0.0..1.0 based on candidate profile below
- check_risk_score: 0.0..1.0, higher = stricter background check likely
- rationale: ≤20 words

Candidate profile: UofT Computer Engineering grad. Strong in 5G/networking (5gcx.ai),
graphics programming, web dev, ML-for-graphics (vimy.ai), systems. Located Toronto or Montreal.
```

User message contains `postings: [{id, title, company, description_text_truncated_2000}]`. Call with `max_tokens: 2000`, `temperature: 0`.

---

## 5. Drafter — RAG + prompt caching

### 5.1 Portfolio ingestion (one-time, re-run monthly)

Sources to crawl and chunk:

- `https://limiliminal.com` (full site)
- `https://5gcx.ai` (full site)
- `https://vimy.ai` (full site)
- GitHub: fetch all public repos, pull README, architecture docs
- Master resume (markdown file under version control in repo)

Chunking: recursive text splitter, 512 tokens, 50 overlap. Metadata per chunk:

```python
{
    "skills": ["webgpu","glsl","real-time-rendering"],  # extract via regex + Haiku pass
    "role_lanes": ["graphics","ml_graphics"],
    "quantified": True,                                  # contains a number with unit
    "project": "vimy-nerf-demo",
    "source_url": "https://vimy.ai/projects/nerf"
}
```

### 5.2 Per-application drafter prompt (cacheable)

Structure exploits Anthropic prompt caching — everything before `<posting>` stays constant across calls made within 5 minutes and re-bills cache-read (0.1× input) instead of full input rate.

```
[SYSTEM — cache_control: ephemeral]
You are drafting a tailored application package for a single job posting.
The candidate is a UofT Computer Engineering grad.
<master_resume>...full 1-page resume text...</master_resume>
<top_40_portfolio_chunks>...concatenated...</top_40_portfolio_chunks>
<writing_rules>
  - Quantify outcomes. If no number, don't make one up.
  - First paragraph: one concrete product-specific sentence showing you read their posting.
  - Max 150 words for cover letter.
  - Never apologize, never mention gaps, never volunteer personal information.
  - Match terminology from the posting.
</writing_rules>
<output_schema>
{
  "tailored_bullets": [{"section": "Experience|Projects", "bullet": "..."}],
  "cover_letter": "...",
  "talking_points": ["...","...","..."],
  "red_flags": ["..."],          # things in the posting that might not fit candidate
  "suggested_resume_variant": "web|graphics|systems_5g|ml_graphics|generic"
}
</output_schema>

[USER — not cached]
<posting>
  Company: {company_name}
  Title: {title}
  Location: {location}
  Description: {description_text}
</posting>
<top_8_relevant_portfolio_chunks>
  {chunks retrieved via cosine against posting embedding}
</top_8_relevant_portfolio_chunks>
```

Model: `claude-sonnet-4-6` (or `claude-opus-4-7` for top-tier companies where marginal quality matters). Temp 0.3. Max tokens 2000.

**Batch drafter runs consecutively** against top 15–20 queued applications per night so the cache stays warm. Log cache-hit token counts to `llm_cost_log` — you want to see cache_read_tokens ≫ input_tokens after the first call.

### 5.3 Resume rendering

Keep the master resume as structured JSON under version control. Template it with Typst (preferred) or WeasyPrint.

```python
class ResumePayload(BaseModel):
    header: dict    # name, email, phone, links
    summary: str
    experience: list[dict]    # each with bullets: list[str]
    projects: list[dict]      # selectable/swappable
    education: list[dict]
    skills: list[str]
```

Variant selection per application: substitute the `projects` block based on `suggested_resume_variant` from the drafter output. Render to PDF, store path in `resume_versions.rendered_pdf_path`, FK from `applications.resume_version_id`.

---

## 6. Tracker UI

FastAPI + HTMX. No SPA framework needed. Five routes:

```
GET  /                        → kanban board over applications, grouped by status
GET  /posting/{id}            → posting detail, drafted materials, "Mark as applied" button
POST /posting/{id}/apply      → transitions status queued→ready_for_human→applied (MANUAL, human-triggered only)
GET  /companies               → list of target companies + posting counts + avg fit_score
GET  /metrics                 → dashboard from metric_events rollup
```

The "Mark as applied" button is the only mutation endpoint that changes `applied_at`. **Do not expose a bulk-apply button.** Each posting requires a separate human click after reviewing the cover letter and the consent-form screenshot.

Daily Resend digest (`cron` at 07:00 local):

- Top 15 new postings by `final_rank` (last 24h)
- Applications sent yesterday
- Follow-ups due today (applications in `applied` status > 7 days with no status change)
- Running API spend MTD (sum of `llm_cost_log.usd_cost`)

---

## 7. Monitoring

- Sentry DSN from env; `traces_sample_rate=0.1`; wrap every ingester with `@sentry_sdk.trace`.
- Emit to `metric_events` on: ingester start/end, postings fetched/new/duplicate, classification batches run, drafts generated, applications marked applied.
- Rollup view for the dashboard:

```sql
CREATE MATERIALIZED VIEW v_daily_metrics AS
SELECT date_trunc('day', ts) AS day,
       metric,
       sum(value) AS total
FROM metric_events
GROUP BY 1, 2;
```

Refresh every hour via cron. Health-check endpoint `GET /healthz` that checks DB + Ollama + Anthropic key presence.

---

## 8. Seed data — target companies

Insert these into `companies` on first run. `ats_token` values are what each ATS client needs. `bg_check_stringency` is pre-classified from research — treat as starting point, refine as you see real job posting text.

```python
SEED_COMPANIES = [
    # Tier 1 — apply immediately
    ("Ericsson Canada", "ericsson.com", "eightfold", "ericsson", "moderate", 1, "Montreal", "QC"),
    ("Matrox", "matrox.com", "custom", None, "lenient", 1, "Dorval", "QC"),
    ("Waabi", "waabi.ai", "lever", "waabi", "moderate", 1, "Toronto", "ON"),
    ("SideFX", "sidefx.com", "custom", None, "lenient", 1, "Toronto", "ON"),
    ("Ciena", "ciena.com", "workday", "ciena", "moderate", 1, "Ottawa", "ON"),
    ("ServiceNow", "servicenow.com", "workday", "servicenow", "moderate", 1, "Montreal", "QC"),
    ("Behaviour Interactive", "bhvr.com", "lever", "behaviour", "lenient", 1, "Montreal", "QC"),
    ("AMD", "amd.com", "custom", None, "moderate", 1, "Markham", "ON"),
    ("Electronic Arts", "ea.com", "workday", "ea", "moderate", 1, "Montreal", "QC"),
    ("Moment Factory", "momentfactory.com", "lever", "momentfactory", "lenient", 1, "Montreal", "QC"),
    ("NVIDIA", "nvidia.com", "workday", "nvidia", "moderate", 1, "Toronto", "ON"),
    ("Cohere", "cohere.com", "greenhouse", "cohere", "moderate", 1, "Toronto", "ON"),
    ("Ubisoft", "ubisoft.com", "smartrecruiters", "ubisoft", "moderate", 1, "Montreal", "QC"),
    ("Coveo", "coveo.com", "greenhouse", "coveo", "moderate", 1, "Quebec City", "QC"),
    ("Shopify", "shopify.com", "ashby", "shopify", "moderate", 1, "Toronto", "ON"),
    # Tier 2
    ("Autodesk", "autodesk.com", "workday", "autodesk", "moderate", 2, "Toronto", "ON"),
    ("Tenstorrent", "tenstorrent.com", "greenhouse", "tenstorrent", "strict", 2, "Toronto", "ON"),  # US export control
    ("Uken Games", "uken.com", "custom", None, "moderate", 2, "Toronto", "ON"),
    ("Rodeo FX", "rodeofx.com", "smartrecruiters", "rodeofx", "moderate", 2, "Montreal", "QC"),
    ("1Password", "1password.com", "ashby", "1password", "strict", 2, "Toronto", "ON"),
    ("Ada Support", "ada.cx", "greenhouse", "ada", "lenient", 2, "Toronto", "ON"),
    ("Faire", "faire.com", "greenhouse", "faire", "moderate", 2, "Toronto", "ON"),
    ("Geotab", "geotab.com", "smartrecruiters", "geotab", "moderate", 2, "Oakville", "ON"),
    ("Snowed In Studios", "snowedinstudios.com", "workable", "snowedin", "lenient", 2, "Ottawa", "ON"),
    ("Haven Studios", "havenstudios.com", "greenhouse", "haven", "strict", 2, "Montreal", "QC"),
    ("Compulsion Games", "compulsiongames.com", "smartrecruiters", "compulsiongames", "moderate", 2, "Montreal", "QC"),
    ("Gameloft", "gameloft.com", "smartrecruiters", "gameloft", "lenient", 2, "Montreal", "QC"),
    ("Mila", "mila.quebec", "workable", "mila", "lenient", 2, "Montreal", "QC"),
    ("Lightspeed", "lightspeedhq.com", "greenhouse", "lightspeed", "strict", 2, "Montreal", "QC"),
    ("Framestore", "framestore.com", "greenhouse", "framestore", "moderate", 2, "Montreal", "QC"),
    # Tier 3
    ("BenchSci", "benchsci.com", "lever", "benchsci", "strict", 3, "Toronto", "ON"),
    ("Jane Software", "jane.app", "lever", "jane", "strict", 3, "Remote", "BC"),
    ("League", "league.com", "greenhouse", "league", "strict", 3, "Toronto", "ON"),
    ("Klick Health", "klick.com", "smartrecruiters", "klick", "strict", 3, "Toronto", "ON"),
    ("AlayaCare", "alayacare.com", "greenhouse", "alayacare", "very_strict", 3, "Montreal", "QC"),
    ("Hopper", "hopper.com", "ashby", "hopper", "strict", 3, "Montreal", "QC"),
    ("Workleap", "workleap.com", "greenhouse", "workleap", "lenient", 3, "Montreal", "QC"),
    # Tier 4 — highest check stringency; include but rank penalizes
    ("Wealthsimple", "wealthsimple.com", "ashby", "wealthsimple", "very_strict", 4, "Toronto", "ON"),
    ("TD Bank", "td.com", "workday", "td", "very_strict", 4, "Toronto", "ON"),
    ("Neo Financial", "neofinancial.com", "lever", "neofinancial", "very_strict", 4, "Toronto", "ON"),
    ("Nuvei", "nuvei.com", "workable", "nuvei", "very_strict", 4, "Montreal", "QC"),
    ("TELUS", "telus.com", "workday", "telus", "very_strict", 4, "Toronto", "ON"),
    ("CGI", "cgi.com", "custom", "cgi-njoyn", "very_strict", 4, "Montreal", "QC"),
]
```

Auto-discovery of new companies: scrape BuiltIn Toronto's company list, fetch each company's careers page, fingerprint the ATS by URL pattern (`boards.greenhouse.io/…` → greenhouse; `jobs.lever.co/…` → lever; `jobs.ashbyhq.com/…` → ashby; `jobs.smartrecruiters.com/…` → smartrecruiters; `apply.workable.com/…` → workable; `*.myworkdayjobs.com` → workday). Insert with `bg_check_stringency='unknown'`; flag for human review in the UI.

---

## 9. Implementation tickets (sprint-ordered)

### Sprint 0 — Foundation (Days 1–3)

- **TKT-001** Bootstrap repo with `uv init`, Python 3.12, add all pyproject deps from §1. Set up pre-commit with `ruff` and `pyright`.
- **TKT-002** Install Postgres 16 + pgvector locally (or docker-compose). Apply §2 schema via Alembic.
- **TKT-003** Install Ollama, `ollama pull nomic-embed-text:v1.5`, verify 768-dim output with a test string.
- **TKT-004** Load `SEED_COMPANIES` from §8 into `companies` table via a `seeds/load.py` script.
- **TKT-005** Set up Anthropic SDK with API key from env; verify Haiku 4.5 and Sonnet 4.6 are reachable; log to `llm_cost_log`.

### Sprint 1 — Ingestion (Days 4–10)

- **TKT-010** `ats/greenhouse.py`: fetch, parse to `RawPosting`, upsert. Test against Cohere, Faire, Ada.
- **TKT-011** `ats/lever.py`: v0 endpoint, same flow. Test against Waabi, Behaviour, Moment Factory.
- **TKT-012** `ats/ashby.py`: posting-api endpoint. Test against Shopify, 1Password, Hopper.
- **TKT-013** `ats/smartrecruiters.py`: city-filtered postings. Test against Ubisoft, Klick, Rodeo FX.
- **TKT-014** `ats/workable.py`: widget API. Test against Snowed In, Nuvei, Mila.
- **TKT-015** `ats/workday.py`: generic tenant client accepting `(tenant, wd_server, site_path)`, POST body, pagination. Test against Autodesk, NVIDIA, Ciena, EA, ServiceNow.
- **TKT-016** `ats/eightfold.py`: test against Ericsson.
- **TKT-017** `ingest/hn.py`: Algolia API, parse monthly "Who is Hiring" thread.
- **TKT-018** `ingest/remote_boards.py`: Remote OK, WWR RSS, Remotive.
- **TKT-019** `ingest/adzuna.py`: Canadian aggregator. Requires free app_id/app_key signup.
- **TKT-020** `systemd` units / `launchd` plists for each ingester with cadences from §3. Include retry with `tenacity` (exponential backoff, 3 attempts).
- **TKT-021** Canonical URL extractor (strip UTMs, session IDs, sort remaining query params). `normalize_title(title)` that lowercases, strips seniority prefixes, strips `(Toronto)`/`(Remote)` suffixes.

### Sprint 2 — Classification + Dedup (Days 11–15)

- **TKT-030** `title_company_hash` = sha1(`normalize_title(title) + '::' + lower(company.name)`). Upsert conflict handling: if existing row's `url_canonical` differs, treat as repost (bump `reposted_count`, update `last_seen`), do not create duplicate.
- **TKT-031** Regex pattern library from §4.1. `classify_keywords(text) -> (strict_hits, lenient_hits, fit_hits, anti_hits)`.
- **TKT-032** Precompute user profile embedding: concatenate master resume + top-40 highest-quality portfolio chunks, embed, cache in a single `profile_vectors` row. Re-generate on portfolio edit.
- **TKT-033** Posting embedding worker: pull unembedded postings via `FOR UPDATE SKIP LOCKED`, embed title + first 1500 chars of description via Ollama, insert into `posting_embeddings`.
- **TKT-034** Near-duplicate detection: for each new posting, cosine-search within same `company_id` over last 90 days; if max cosine ≥ 0.92, set `canonical_posting_id` to the older posting.
- **TKT-035** Haiku batched classifier using prompt from §4.4. Batch size 10. Cost-log every call.
- **TKT-036** `compute_final_rank()` per §4.3. Recompute nightly for all open postings (freshness decays).

### Sprint 3 — Portfolio RAG + Drafter (Days 16–20)

- **TKT-040** Portfolio crawlers: `portfolio/limiliminal.py`, `portfolio/fivegcx.py`, `portfolio/vimy.py`, `portfolio/github.py`. Fetch, extract text (use `selectolax`), store raw in a `portfolio_raw` staging table.
- **TKT-041** Chunker: recursive splitter, 512 tokens, 50 overlap. Skills extraction via regex pass against `FIT_KEYWORDS`. Role-lane tagging via Haiku pass (one-off, small cost).
- **TKT-042** Embed all chunks, insert into `portfolio_chunks`.
- **TKT-043** Drafter service: input posting_id; retrieve top-8 portfolio chunks by cosine against posting embedding; construct Sonnet 4.6 call with cached system prompt per §5.2; parse JSON response; persist to `applications.tailored_bullets`/`cover_letter`/`talking_points`/`red_flags`.
- **TKT-044** Resume renderer: Typst template + JSON payload → PDF in `./artifacts/resumes/`. Record in `resume_versions`, FK from `applications`.

### Sprint 4 — Tracker UI + Monitoring (Days 21–25)

- **TKT-050** FastAPI app skeleton. Jinja2 templates for kanban, posting detail, companies, metrics.
- **TKT-051** Kanban: columns `queued | drafted | ready_for_human | applied | phone | onsite | offer | rejected`. Drag-and-drop via HTMX `hx-post` on status change.
- **TKT-052** Posting detail view: renders drafted cover letter, tailored bullets, red_flags, links to resume PDF, and **a prominent consent-form warning checklist** before the "Mark as applied" button becomes active. No bulk-apply.
- **TKT-053** Daily Resend digest: cron at 07:00; template with top 15 new, yesterday's applications, follow-ups due, MTD spend.
- **TKT-054** Sentry integration; `metric_events` emit helpers.
- **TKT-055** `GET /healthz` — DB + Ollama + Anthropic key + last ingestion timestamps.

### Sprint 5 — Scraping Expansion (Days 26–35, optional)

Only start if Tier A–C pipeline from sprints 1–4 is landing <5 relevant postings/day.

- **TKT-060** Playwright harness with stealth plugin, `en-CA` locale, `America/Toronto` timezone, residential proxy support via env.
- **TKT-061** LinkedIn public jobs scraper (no login): search by keyword list × `Toronto`/`Montreal`/`Remote Canada`. 24h cadence. Expect CAPTCHA occasionally; degrade gracefully.
- **TKT-062** Indeed Canada scraper. Cloudflare-aware: randomized delays, residential IP.
- **TKT-063** BuiltIn Toronto company discovery: scrape company list, fingerprint ATS from their `/careers` URL, auto-insert into `companies` with `bg_check_stringency='unknown'`. Human reviews in the UI.

---

## 10. Budget envelope (sanity check)

At 500 postings/day, 15k/month, 150 drafted applications/month:

| Item | Monthly |
|---|---|
| Haiku classification (30% pass-through from regex/embed gate, batched) | ~$0.77 |
| Sonnet drafting with cache (~$0.02/app × 150) | ~$3.30 |
| Ollama embeddings (local) | $0 |
| Postgres (local / $5 VPS tier) | $0–$5 |
| Residential proxies (only if Sprint 5) | $0–$10 |
| Resend (free tier) | $0 |
| Sentry (free tier) | $0 |
| **Total** | **~$5–$20/mo** |

Set a soft alert in `llm_cost_log` if MTD spend > $30.

---

## 11. Things explicitly out of scope

- Auto-submission of applications (see §0).
- Scraping LinkedIn while logged in (ToS risk, account-ban risk; operator will decide case-by-case).
- Credential stuffing across ATSes (operator manages accounts manually).
- Fine-tuning a classifier (Haiku zero-shot is good enough given data volumes).
- Multi-user support (this is a single-operator tool).
- Mobile app / notifications beyond email (add later if needed).

---

## 12. First-run sanity test

After Sprint 1 completes, these five assertions should pass:

1. `SELECT count(*) FROM companies WHERE tier <= 3` returns ~40.
2. `SELECT count(*) FROM postings WHERE source = 'greenhouse'` returns > 50 within first 24h.
3. `SELECT count(DISTINCT source) FROM postings` returns ≥ 5 within first 48h.
4. No duplicate `url_canonical` violations in logs.
5. Health endpoint returns 200 with all subsystems green.

If any fail, debug the corresponding ingester before moving to Sprint 2.
