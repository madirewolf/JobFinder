# Toronto/Montreal tech job search and job-finder bot: comprehensive research report

A University of Toronto Computer Engineering graduate can realistically land two to five tech offers in Toronto or Montreal inside eight weeks, despite a pending criminal charge, because **Canada's standard name-based criminal record check returns convictions only, not pending charges** — and the legal, market, and technical conditions around that single fact shape every other decision in this plan. The 2025–26 Toronto/Montreal market is soft but not closed: Indeed Hiring Lab characterizes it as "soft but fairly stable," and CompTIA projects Toronto above 414,000 tech jobs in 2025. Quebec's Charter s.18.2 materially strengthens protection against conviction-based exclusion versus Ontario's Human Rights Code, and recent Tribunal des droits de la personne rulings (Proulx 2015; Absi 2025 QCTDP) have extended that protection to accused persons where the alleged offence has no objective connection to the job. The tactical frame is therefore harm reduction and strategic positioning, not moral guidance: choose employers whose check tier is conviction-only, treat Quebec as the legally safer jurisdiction, build a bot that ingests clean ATS JSON feeds, and run a disciplined 60-day pipeline with UofT-alumni referrals as the primary lever.

---

## 1. Canadian background-check landscape

**The single most load-bearing fact for decision-making**: a basic name-based CPIC criminal record check (RCMP "Criminal Record Check"; Ontario "Level 1" CRC; Toronto Police "CRC"; Certn basic; Sterling basic) is **designed to return unpardoned convictions only** — not outstanding charges, not withdrawn or stayed matters, not peace bonds, not absolute or conditional discharges. Enhanced products (Criminal Record and Judicial Matters Check / "Level 2" / Police Information Check; Certn Enhanced; Sterling E-PIC) *do* return outstanding charges, warrants, peace bonds, and discharges. Vulnerable Sector Checks (VSCs) go further and can include exceptional disclosure of non-conviction information. Fingerprint-based RCMP certified checks (CCRTIS) are the most comprehensive and are required for federal Reliability Status, Secret clearance, and Controlled Goods Program designation.

Two caveats matter. First, even a basic CPIC can return "Incomplete" when name+DOB produce a hit, effectively signalling that *something* exists on file without disclosing what — this can push the employer to fingerprints. Second, third-party vendors (Certn, Sterling, Mintz Global, HireRight, Triton, ISB) access CPIC through police-service MOUs, and most employers do not restrict themselves to the strict basic tier; the product actually ordered is determinative and is rarely visible to the candidate pre-offer.

| Check type | Searches | Convictions | Pending charges | Typical cost / TAT | Employer use |
|---|---|---|---|---|---|
| Name-based CPIC CRC (Level 1) | RCMP National Repository via name+DOB | Yes (unpardoned) | **No** (may flag "Incomplete") | $25–65 / same day–10 bd | Most standard SaaS/tech |
| Enhanced PIC / CRJMC (Level 2) | CPIC + local police + PIP + court records | Yes | **Yes** | $45–100 / 1–10 bd | Fintech, management, trust roles |
| Vulnerable Sector Check | Above + pardoned sex-offender databank; fingerprints on match | Yes + pardoned Schedule 2 | Yes + exceptional non-conviction | Free (volunteer) or ~$86 / 2–8 wk | Healthcare, edtech with minors |
| RCMP certified fingerprint | Full National Repository via biometrics | Yes | Yes | $25 + vendor ~$50–100 / 3–120 bd | Federal gov, CGP, immigration |
| Credit (Equifax/TransUnion Canada) | Consumer file only | N/A | No | $5–25 / 1–3 bd | OSFI banks, fintech, responsible-persons roles |
| Vendor bundles (Sterling, Certn, etc.) | Varies by tier | Yes | **Depends on tier** | $15–100+ / minutes–72h | Default for mid-to-large employers incl. tech |

**Legal framework.** Ontario's Human Rights Code protects only "record of offences" meaning (a) federal convictions for which a pardon has been granted and not revoked, or (b) provincial-enactment convictions. The OHRC's own guidance is explicit that the provision "applies to convictions only, and not to situations where charges only have been laid." *de Pelham v. Mytrak Health Systems*, 2009 HRTO 172 is the governing authority: **HRTO has no jurisdiction over a pending-charge dismissal in Ontario.** Quebec is materially stronger. Charter s.18.2 protects *unpardoned* convictions unless the employer proves an objective connection between the offence and employment duties, and Tribunal case law (*CDPDJ c. Québec*, Proulx 2015; *Absi c. Néolégal*, 2025 QCTDP) has extended this to accused-but-not-convicted persons in specific hiring contexts. The federal Canadian Human Rights Act (CHRA) covers federally regulated employers only and tracks Ontario's narrower scope (pardoned convictions).

**There is no general common-law duty to volunteer a pending charge unprompted** in either province (*Merritt v. Tigercat Industries*, 2016 ONSC 1214 confirms the right to silence). Disclosure becomes required only when a contract or policy requires it, a professional regulator requires it (PEO's P.Eng. application Q7/Q8 require disclosure of both guilt findings and active investigations), or a security clearance / Controlled Goods Program process is underway (Treasury Board Standard on Security Screening; files with pending charges are placed on hold until disposition).

**Industry stringency map.** Standard software/SaaS startups overwhelmingly use Certn or Sterling basic (conviction-only). OSFI-regulated fintechs and banks run enhanced criminal + credit as of OSFI's Integrity & Security Guideline (effective 31 July 2025). Federal Reliability Status requires fingerprint-based checks plus credit inquiry plus 5-year verification; Secret clearance adds a 10-year window plus CSIS assessment. Healthcare-adjacent, edtech with minors, and daycare trigger vulnerable sector checks. Controlled Goods Program (defence/aerospace) and crypto/MSB executive roles require criminal record checks with self-disclosure of pending charges. US-HQ firms typically run enhanced checks through Sterling/HireRight/Checkr's Canadian partners, bound by Canadian law for Canadian hires — Quebec s.18.2 still applies.

**Fair chance in Canada is thin.** Canada has no federal ban-the-box law. The John Howard Society of Ontario runs a Fair Chance Coalition and employer pledge, and published a 2025 Fair Chances Developer Toolkit — JHSO's own 2024 survey found **75% of 400 Canadian hiring managers had never knowingly employed someone with a criminal record**. No Canadian tech employer has a documented fair-chance hiring program. Shoppers Drug Mart and Home Depot Canada are sometimes cited in US contexts but Canadian-specific policies are not verifiable. The practical levers are therefore: (1) target Quebec employers where s.18.2 applies, (2) prefer employers likely to run only basic checks, (3) never lie on a consent form, (4) ensure bail conditions do not block role requirements, (5) avoid federal-clearance and CGP roles until disposition.

## 2. Target-employer mapping across Toronto and Montreal

### Toronto cluster (strong for systems, AI/ML, graphics hardware, fintech)

Toronto's highest-fit, highest-velocity, check-manageable opportunities cluster in four sub-industries. **Waabi** (Lever, 49+ open roles after a $750M Series C + $250M Uber commitment in September 2025) runs "Research Engineer, Sensor Simulation — neural rendering" and similar roles that directly bridge graphics, ML, and systems — the single highest-upside target. **AMD Markham** is Canada's graphics-hardware capital with active C++ GPU driver and graphics-ML roles; export control applies but is manageable for citizens/PRs. **SideFX** (Toronto HQ, Houdini) is a rare pure graphics-programming fit at smaller scale with explicit AI-workflow roles. **Ericsson Ottawa** and **Ciena Kanata** are the two cleanest matches for the user's 5gcx.ai networking background: both post 2026 new-grad 5G/networking SWE roles regularly; Ericsson uses Eightfold AI ATS, Ciena uses Workday.

In the second tier, **NVIDIA Toronto** (growing in 2026), **Cohere** (Greenhouse, Toronto HQ, hot hiring after $500M+ raises), **Tenstorrent** (Greenhouse, 20+ Toronto roles, but hard US-export-control citizenship gate), **Autodesk** (Workday, active Senior SWE Desktop Application + AI Research in Toronto), and **Uken Games** (custom ATS, F2P mobile) offer strong fit with medium stringency at worst.

The third tier contains good fits with high check stringency — **Wealthsimple** (Ashby, post-$750M raise at $10B valuation, OSFI-regulated → enhanced + credit), **Layer 6 AI / TD Bank** (Workday, highest stringency in the list — enhanced + credit + fingerprint), **Float** (likely Ashby, MSB-registered), **Koho** (Ashby, on banking-licence path), **Neo Financial** (Lever, public careers-page notice that security screening and background checks are required), **Borrowell** (Greenhouse, Equifax-tied), **Bell/Rogers/TELUS** (Workday, enhanced + credit confirmed via TELUS's public BackCheck consent form), **Nuvei** (Workable, PCI-DSS). Apply here only if credit is clean and the role is not safety/security-sensitive.

Toronto games/graphics beyond Waabi/AMD/NVIDIA/SideFX includes **Ubisoft Toronto** (SmartRecruiters), **Snowed In Studios** (Workable, Ottawa but remote-friendly), **Drinkbox Studios**, **Capybara Games**, **Untold Studios Toronto** (custom ATS). Drinkbox and Capybara are email-only and bot-unfriendly; SideFX, Autodesk, and Snowed In are the cleanest ATS integrations.

**Toronto companies with public background-check signals**: TELUS uses BackCheck (criminal + credit + employment + education). Neo Financial publicly requires "security screening and appropriate background checks." Tenstorrent publicly requires citizenship/PR documentation due to US export control. Cohere publicly pipelines through Greenhouse only.

### Montreal cluster (world capital for games/VFX, strong AI, s.18.2 advantage)

Montreal's legal environment is materially friendlier: Quebec's Charter s.18.2 strongly limits conviction-based employment filtering for non-sensitive roles, and private-sector tech hiring customarily runs ID + employment + education verification with criminal checks reserved for payments/healthcare/clearance contexts. **Law 25** further discourages speculative data collection. For a candidate with a pending charge, Montreal is the legally safer jurisdiction.

The ten highest-priority Montreal targets, in apply-order:

1. **Ericsson Montréal (BCSS + GAIA)** — bullseye for 5G networking; Cloud RAN, network APIs, AI-for-5G; $630M Strategic Innovation Fund through 2029; actively expanding.
2. **Matrox (Dorval)** — rare pure graphics-hardware + systems/networking fit; privately-held Quebec-owned; lowest-friction BG path; Montreal's Top Employer 2025 and 2026 Best Employer for Recent Grads.
3. **ServiceNow Montréal (ex-Element AI)** — Workday; flagship AI research lab; aggressive hiring on AI agents and applied AI FDE.
4. **EA Motive / SEED** — Workday; "Senior Software Developer (Gen AI) — SEED" is a direct ML-for-graphics match.
5. **Behaviour Interactive** — Lever; 28–35 open engineering roles, 4-day-week culture, English-primary.
6. **Moment Factory** — Lever; Unreal / creative-tech / CG Supervisor + backend roles; ~20 open.
7. **Ubisoft Montréal** — SmartRecruiters; despite RTO + restructuring, still hiring Golang platform and gameplay roles.
8. **Rodeo FX** — SmartRecruiters; graphics pipeline (Python/USD/Houdini); TPN site-security audits apply for Marvel/Disney work.
9. **Coveo** — Greenhouse; AI search; Quebec-HQ (strong s.18.2); continuous ML/SWE hiring.
10. **Shopify Montréal** — Ashby; remote-first with office drop-in; Ruby/Rails at scale.

Montreal companies to time-sensitively avoid or watch: **Eidos-Montréal** (124 laid off late 2025, only ~2 open roles), **WB Games Montreal** (March 2026 layoffs), **Hopper** (multi-wave cuts 2023–25), **Breather/Bench** (dormant), **Stradigi AI** (uncertain status). Highest-stringency Montreal employers where check exposure is real: **CGI** (Njoyn ATS; federal clearance); **Nuvei**, **Lightspeed payments roles** (PCI-DSS); **Dialogue / AlayaCare / Paper** (healthcare/edtech vulnerable-sector triggers); **Hydro-Québec**, **Bell Canada**, **Telesat**; and **Haven Studios (Sony)**, which is one of the few Montreal employers that **publicly discloses** offer-stage criminal checks ("may include criminal background checks for some roles").

Public hiring-practice documentation is rare; inference from industry/regulatory exposure is the dominant mode. ATS platform is discoverable by URL inspection for roughly 70% of targets — this is what makes bot automation feasible.

## 3. Job-board data sources and ATS scraping feasibility

The highest-ROI data architecture ignores the job-board arms race and targets ATS public endpoints directly. **Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, and Workday collectively cover the large majority of cleanly scrapable TO/MTL tech boards** — all with documented or well-known JSON patterns, most auth-free.

| ATS | Endpoint pattern | Auth | Stability | TO/MTL examples |
|---|---|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | None; no rate limit | Very stable, documented | Cohere, Ada, League, Tenstorrent, Clearco, Lightspeed, Borrowell, Faire, Haven, Coveo |
| Lever | `https://api.lever.co/v0/postings/{company}?mode=json` | None (v0 public) | Stable | Shopify legacy, Waabi, BenchSci, Jane App, Neo Financial, Behaviour, Moment Factory |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true` | None | Stable | Wealthsimple, 1Password, KOHO, Hopper, Shopify, Float |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{companyId}/postings?city=Toronto` | None for GET | Stable, OpenAPI-documented | Ubisoft, Klick, Geotab, Rodeo FX, Don't Nod |
| Workable | `https://apply.workable.com/api/v1/widget/accounts/{company}` | None | Stable | Snowed In, Nuvei, Sangoma, Mila, Botpress, Cinesite |
| Recruitee | `https://{company}.recruitee.com/api/offers/` | None | Stable | Smaller scale-ups |
| Workday | `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | None; send realistic headers | Stable but tenant-specific | RBC, TD/Layer 6, Bell, TELUS, Autodesk, NVIDIA, Ciena, Nokia, CGI, Shopify legacy, EA, ServiceNow |

BambooHR's `embed2.php` returns HTML only; Personio exposes `{company}.jobs.personio.de/xml` (EU-heavy, thin for Canada); JazzHR, iCIMS, Taleo, and SuccessFactors have no reliable public no-auth feeds and require per-tenant scraping.

**Major job boards:** LinkedIn has no open jobs API; Voyager reverse-engineering rotates every 4–8 weeks; Proxycurl was shut down July 2025 after LinkedIn litigation. Indeed's Publisher API is deprecated (~2023); HTML is Cloudflare-protected. Glassdoor's API closed 2021; scraping requires residential IPs. Wellfound, Welcome to the Jungle, BuiltIn Toronto, Jobboom, and Talent.com are all scrapable with varying friction. **HN Algolia API** is the single cleanest source for "Who is Hiring" monthly threads: `https://hn.algolia.com/api/v1/items/{thread_id}` at 10k req/hour, no auth. **Remote OK** (`remoteok.com/api` with attribution), **We Work Remotely RSS**, and **Remotive/Jobicy** all expose clean public feeds. **Job Bank Canada** provides an official XML feed for publishers on request and a monthly Open Data CSV via open.canada.ca.

Aggregators with developer APIs: **Adzuna** (`/v1/api/jobs/ca/search/1` — free developer tier, good Canadian coverage), **Jooble** (`jooble.org/api/{key}` with JSON body), **JSearch on RapidAPI** (wraps Google for Jobs, highest signal density, ~$0.01/req at paid tiers), **TheirStack** (paid, ~$199/mo, stack + hiring signals), **Fantastic.jobs** (54 ATS backend, commercial backstop at $49–200/mo).

**Recommended ingestion tiering**: (1) high signal / low maintenance — Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee polled every 1–2 hours + HN Algolia + Remote OK; (2) per-tenant — one generic Workday client handling the TO/MTL enterprise list (RBC, TD, BMO, CIBC, Scotia, NBC, Manulife, Sun Life, Desjardins, Bell, TELUS, CGI, CN, Bombardier, Air Canada); (3) scrape with Playwright — LinkedIn, Indeed, Glassdoor on 24h cadence behind residential proxies (Decodo ~$2/GB, Oxylabs ~$4/GB PAYG, Bright Data for hardest targets); (4) discovery — BuiltIn Toronto scraped for company lists → detect ATS from careers-page URL fingerprints → add to Tier 1 polling. Only add Playwright scraping after ATS feeds are exhausted; consider ScrapFly/ScraperAPI as unblocker wrappers to avoid the fingerprinting arms race.

## 4. NLP signals for classification

Three keyword taxonomies drive posting classification. **Strict-check indicators** cluster in four categories: government/defence ("public trust clearance", "Reliability status", "Secret clearance", "Canadian citizen required", "controlled goods program", "ITAR", "EAR", "CSIS", "CSE", "DND", "PSPC"); financial services ("SOC 2", "PCI-DSS", "PIPEDA compliance officer", "OSFI-regulated", "bondable", "FINTRAC", "IIROC", "AML/KYC"); healthcare/vulnerable ("vulnerable sector check", "PHIPA", "HIPAA", "working with minors", "fingerprint check required"); generic elevated screening ("Sterling", "HireRight", "Checkr enhanced", "7-year employment verification"). **Lenient indicators** include company-size/stage signals ("founding engineer", "seed-stage", "YC", "<20 people", "bootstrapped"), async/open-source culture ("remote-first", "we contribute upstream"), contract employment types, and explicit non-requirements ("no clearance needed"). **Role-fit keywords** get weighted heavily for the user's profile: 5G/networking (3.0), graphics/rendering (3.0), ML-for-graphics (3.5), systems/C++/Rust/CUDA (2.5), games/Unreal/Unity (2.5), web (1.5). Anti-keywords (PHP/WordPress/COBOL/mainframe) carry -2.0 penalty.

**Classifier architecture**: the recommended hybrid pipeline is regex → local embedding → Claude Haiku — each stage filters aggressively before paying LLM cost. At Anthropic April-2026 pricing (Haiku 4.5 $1/$5 per MTok; Sonnet 4.6 $3/$15 per MTok; batch API 50% off; prompt caching cache-read 0.1× input), batched Haiku processing of 10 postings per call costs roughly **$2.53 per 1,000 postings standalone or ~$0.77 per 1,000 with a regex+embedding gate that passes only 30% to Claude**. Zero-shot Sonnet would run ~$7.59 per 1,000. Fine-tuned DistilBERT is theoretically cheapest at scale but requires 5–10k labeled postings the user does not have time to produce.

```
raw posting
  → HTML strip + boilerplate removal       (~2 ms, free)
  → regex pass: strict/lenient/fit_kw      (~5 ms, free)
  → drop obvious non-fits
  → local Ollama nomic-embed-text (768-dim)(~50 ms, free)
  → cosine vs precomputed profile vector   (<1 ms)
  → if cos ≥ 0.55 or fit_kw_hits ≥ 2
     → Haiku 4.5 batched (10/call) for structured extraction
  → final_rank = fit × (1 - 0.6 × check_risk) × freshness × salary × remote_flex
```

At 500 postings/day × 30 = 15,000/month, classification costs ~$11.50/month; drafting with Sonnet 4.6 and cached portfolio prefix costs ~$3.30/month for 150 applications; proxy and tooling bring total Claude + infra spend to **~$19–22/month**.

## 5. Bot architecture built with Claude Code

The stack prioritizes speed-to-first-application over scalability. A single-user bot with a two-month horizon does not need Temporal, Prefect, or Kubernetes. **Python 3.12 + uv + Postgres 16 with pgvector + systemd timers + Playwright + Anthropic SDK + Ollama** is the entire production environment.

**Ingestion layer.** One Python module per source family (`ingest/hn.py`, `ingest/greenhouse.py`, etc.) invoked from systemd timers (launchd on macOS). Polling cadence: Greenhouse/Lever/Ashby/SmartRecruiters every 1–2 hours; Workable/Recruitee every 4 hours; Workday tenants every 2–4 hours; LinkedIn/Indeed/Glassdoor every 12–24 hours via Playwright + residential proxy; HN Algolia thread parsed monthly. Playwright context includes realistic user agent, `en-CA` locale, `America/Toronto` timezone, and `navigator.webdriver` nulled. Proxy budget: expect <$3/month at this throughput using Decodo PAYG residential; datacenter proxies suffice for most non-LinkedIn sources.

**Deduplication** runs in four layers: canonical URL extraction strips UTMs/session IDs; title+company sha1 hashing (normalized: lowercase, strip seniority prefixes, strip trailing location) produces a unique index; pgvector cosine on description embeddings at threshold 0.92 catches near-duplicates within a company over a 90-day window; cross-source rank prefers the ATS row over LinkedIn/Indeed when both exist.

**Classification pipeline** emits `check_risk_score`, `fit_score`, and `final_rank` into the `postings` table (see schema below). Top 20 by `final_rank` are queued nightly for the drafter.

**Application drafter** ingests the user's portfolio — limiliminal writeups, 5gcx.ai technical posts, vimy.ai content, GitHub READMEs, master resume — chunked at 512 tokens with 50-token overlap, embedded via Ollama, stored in `portfolio_chunks` with skill-tag metadata. Per-application prompt structure: cached system block (base resume + top-40 portfolio chunks ≈ 8k tokens, `cache_control: {type: "ephemeral"}`) + per-posting body + top-8 retrieved chunks + JSON schema for output (`tailored_bullets[]`, `cover_letter`, `talking_points[]`, `red_flags[]`). First call pays 1.25× cache-write (~$0.03); subsequent calls within 5 minutes pay 0.1× cache-read; effective per-application cost ≈ $0.02 on Sonnet 4.6. Batch applications consecutively to maximize cache reuse.

**Tracker database (Postgres 16 + pgvector, core schema sketch):**

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE remote_type_enum AS ENUM ('remote','hybrid','onsite','unspecified');
CREATE TYPE bg_stringency_enum AS ENUM ('unknown','lenient','moderate','strict','very_strict');
CREATE TYPE ats_platform_enum AS ENUM ('greenhouse','lever','ashby','workable','workday',
    'bamboohr','smartrecruiters','recruitee','icims','taleo','custom','linkedin','unknown');
CREATE TYPE application_status_enum AS ENUM ('queued','applied','acknowledged','phone',
    'onsite','offer','rejected','withdrawn');

CREATE TABLE companies (
    id BIGSERIAL PRIMARY KEY,
    name CITEXT NOT NULL, domain CITEXT,
    ats_platform ats_platform_enum NOT NULL DEFAULT 'unknown',
    bg_check_stringency bg_stringency_enum NOT NULL DEFAULT 'unknown',
    hq_location TEXT, headcount_est INT, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, domain));

CREATE TABLE postings (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title TEXT NOT NULL, title_normalized TEXT NOT NULL,
    url_canonical TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL, source_rank SMALLINT NOT NULL DEFAULT 5,
    raw_json JSONB NOT NULL, description_text TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ, reposted_count INT NOT NULL DEFAULT 0,
    canonical_posting_id BIGINT REFERENCES postings(id),
    remote_type remote_type_enum NOT NULL DEFAULT 'unspecified',
    location TEXT, seniority TEXT,
    salary_min INT, salary_max INT, salary_currency CHAR(3) DEFAULT 'CAD',
    tech_stack TEXT[], role_category TEXT,
    fit_score REAL, check_risk_score REAL, final_rank REAL,
    strict_hits JSONB, lenient_hits JSONB,
    title_company_hash CHAR(40) NOT NULL);
CREATE UNIQUE INDEX idx_postings_hash ON postings(title_company_hash)
    WHERE canonical_posting_id IS NULL;
CREATE INDEX idx_postings_final_rank ON postings(final_rank DESC NULLS LAST)
    WHERE closed_at IS NULL;

CREATE TABLE posting_embeddings (
    posting_id BIGINT PRIMARY KEY REFERENCES postings(id) ON DELETE CASCADE,
    embedding vector(768) NOT NULL,
    model TEXT NOT NULL DEFAULT 'nomic-embed-text-v1.5');
CREATE INDEX idx_posting_emb_hnsw ON posting_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

CREATE TABLE applications (
    id BIGSERIAL PRIMARY KEY,
    posting_id BIGINT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    status application_status_enum NOT NULL DEFAULT 'queued',
    applied_at TIMESTAMPTZ, resume_version_id BIGINT,
    cover_letter TEXT, tracking_notes TEXT, next_action_at TIMESTAMPTZ,
    referrer_email TEXT, referrer_name TEXT,
    submission_channel TEXT);
CREATE UNIQUE INDEX idx_applications_posting ON applications(posting_id);

CREATE TABLE portfolio_chunks (
    id BIGSERIAL PRIMARY KEY, source TEXT NOT NULL, project TEXT,
    content TEXT NOT NULL, embedding vector(768) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb);
CREATE INDEX idx_pchunks_emb_hnsw ON portfolio_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

CREATE TABLE metric_events (
    id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric TEXT NOT NULL, value DOUBLE PRECISION NOT NULL DEFAULT 1,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb);
```

Use `SELECT ... FOR UPDATE SKIP LOCKED` for the work queue — Redis is unnecessary at this scale. **Token efficiency patterns**: prompt cache the 8k-token resume+portfolio prefix (cache-read is 10% of input cost); batch 10 postings per Haiku call; strip HTML/boilerplate before sending (typical 60–75% input reduction); route Haiku for classification, Sonnet only for drafting. Monitoring via Sentry free tier (5k events/month) and a `metric_events` table rollup view; daily Resend digest email (free tier 3k/mo) with top 15 new postings by `final_rank`, applications sent, follow-ups due, and running API spend.

## 6. Application strategy for an urgent sub-60-day timeline

The 2025–26 Toronto/Montreal market rewards tailored-plus-referral over pure volume. Ontario's Professional, Scientific & Technical postings dropped –57.4% YoY per Toronto Workforce Innovation Group mid-2025, yet Toronto added 95,900 tech jobs over the preceding five years (CompTIA). Each requisition in this regime attracts 200–500 applicants, so a cold Easy-Apply averages 2–5% response while targeted direct apply with tailored resume hits 8–15% and referrals hit 30–50%. **Target 10–15 quality applications per day across three tiers**: Tier A (10–15 dream companies, full custom, referral sought, ~2/day), Tier B (40–60 good-fit companies, lightly tailored with swap-in lead projects, ~5–8/day), Tier C (Easy-Apply volume, no cover letter, ~5–10/day). Over 45 working days this produces 300–450 apps, ~20–30 first-round screens at blended 5–7%, and realistically **2–5 offers in eight weeks**.

**Resume structure** is a single master resume with a swappable "Selected Projects" block under a constant header. Lead with limiliminal for web roles (Next.js/TypeScript/Tailwind with Lighthouse + TTFB numbers); lead with shader demos and WebGL/WebGPU for graphics roles (ShaderToy links, Gaussian splatting, Houdini procedural); lead with 5gcx.ai and UofT ECE coursework for systems/5G/CompE (packet-processing throughput in Gbps, latency deltas, SystemVerilog pipeline projects); lead with vimy.ai and NeRF/splat experiments for ML-for-graphics (PSNR/SSIM deltas, training-stability notes). Every bullet quantifies an outcome. Canadian recruiters scan 7–10 seconds per resume, so the top third does all the work.

**Cover letters move the needle in Canada more than in the US.** A 2023 Resume Genius survey found 83% of hiring managers frequently or always read them, and Canadian norms (per Arlyn Recruiting, HRD Canada, Robert Walters) reward researched fit and quantified evidence. For Toronto/Montreal startups and mid-size tech, always include one; for FAANG Easy-Apply, skip. The 150-word structure: address a named hiring manager, one concrete product-specific sentence demonstrating research, three reasons with one quantified result each, a direct ask for a 20-minute conversation. Never apologize, never mention gaps, never write anything you would prefer not to have in writing.

**Referral pathways** are the single highest-leverage tactic. UofT primary: the Engineering CONNECT platform (56,000+ grads), Engineering Alumni Network events, the Engineering Career Centre job board (accessible for two years post-grad), UofT CSC and UTMIST Discords, and a LinkedIn search of `"University of Toronto" + "Computer Engineering" + [Company]` to surface alumni at every target. Toronto community: TechTO (monthly events + Slack), Civic Tech Toronto, r/cscareerquestionsCAD. Montreal community: MTL NewTech, Built In Montreal, Montreal Startups Slack, MILA alumni channels. Graphics/games-specific: the Graphics Programming Discord (21,500+ members), Handmade Network Discord, r/GraphicsProgramming. Cold outreach format: messages under 400 characters lift responses by 22%; personalization by 27%; Tue–Thu outperforms Fri/Sat by 8% (LinkedIn InMail analysis).

**Freshness decay is substantial.** LinkedIn's own analysis shows applications within 24 hours have ~64% higher interview-conversion rates; 65% of InMail responses come within 24 hours. Set alerts on LinkedIn, BuiltIn, Wellfound, and every target company's ATS; apply within 24–72 hours or route through referral instead.

**Sixty-day sequencing:** Week 1 builds the pipeline (finalize master resume + 4 role variants, update limiliminal, pin six GitHub repos with real READMEs, assemble 50-company target spreadsheet with ATS URLs and 1–2 internal contacts per company, activate LinkedIn Open-to-Work recruiters-only mode, set alerts — 0 apps). Weeks 2–3 run high volume across Tier A/B plus 3–5 UofT alumni + 2–3 target-engineer referral messages per day. Weeks 3–5 follow up on Week-2 apps at 7–10 days, screens begin, maintain 8/day top-of-funnel, prep LeetCode-medium and system-design in parallel. Weeks 4–7 are technical rounds and onsites; drop new apps to 3–5/day, prioritize rest before onsites. Weeks 6–8 are offers, negotiation, stall-to-align, close.

## 7. Portfolio leverage: limiliminal, 5gcx.ai, vimy.ai, GitHub, LinkedIn

Canadian recruiters typically spend under 60 seconds on a personal site, so every element must pull weight. **limiliminal structure**: above-fold name + one-line positioning + location + "Open to X roles — email"; 3–5 flagship project cards with image/GIF thumbnail, one-sentence result, stack badges, and links to demo + code + writeup; three-sentence About; direct contact not a form; optional blog where one technical deep-dive outperforms ten shallow posts. Avoid slow intro animations, full-screen autoplay video, or "passionate about" filler — ship-signal beats aesthetic-signal.

**5gcx.ai positioning shifts by role lane.** For systems/networking/infra, it is the primary artifact with a dedicated writeup page: problem → architecture → results with latency/throughput numbers, diagrams, and GitHub link. For ML or general ML-for-graphics, frame it as "applied engineering at telecom scale." For web roles, de-emphasize to a single summary line. **vimy.ai positioning depends on content**: if ML/research, lead with papers/preprints/notebooks and reproducibility; if graphics, video/GIF demos and ShaderToy/Sketchfab embeds front-and-centre; if systems, performance numbers, flame graphs, before/after benchmarks. In all cases give it a tagline that makes its purpose legible in five seconds.

**GitHub optimization**: pin six repos balancing breadth (best graphics, best systems/perf, best web, 5gcx-related, vimy-related, one contribution to a well-known OSS repo). Every pinned repo needs a real README following this order: animated header GIF, one-sentence bold "what this is," live demo link, tech-stack badges, results/metrics table, architecture diagram or bulleted flow, tested setup instructions, roadmap/limitations, license + contact. Contribution graph matters — **commit something real daily for the next 60 days** (docs, tests, refactors — not commit-spam scripts). Small PRs to well-known libraries build external credibility faster than solo repos.

**LinkedIn optimization for Canadian recruiters**. Headline formula: `[What you do] | [Tech/domain] | [Location/availability]`; avoid "Aspiring…" or "Seeking…". Featured section pins in order: limiliminal, best GitHub repo, 5gcx.ai, vimy.ai, one writeup. Open-to-Work default is **recruiters-only** (LinkedIn reports ~40% lift in InMail responses, 3× more messages; ex-recruiter commentary treats the public green banner as mildly negative for senior roles). After two weeks of thin inbound, switch to public banner. Skills section: pack ATS-friendly terms (TypeScript, React, Next.js, Python, C++, Rust, CUDA, WebGPU, WebGL, Unity, Unreal Engine, PyTorch, Distributed Systems, Computer Graphics, 5G, Networking, Real-Time Rendering) up to LinkedIn's cap of 50; search weights top three. Experience bullets use STAR format with quantified outcomes. Posting cadence: 1–2 short technical posts per week during the search; comment substantively on 3–5 posts from people at target companies.

## 8. Interview, offer, and disclosure handling (high sensitivity)

**This section is strategic positioning and harm reduction, not legal advice or moral guidance. Review every script and every disclosure decision with criminal defence counsel and, at offer stage, with an employment lawyer in the relevant province.**

### The disclosure-trigger grid

No general common-law duty exists to volunteer a pending charge unprompted in Ontario or Quebec. *Merritt v. Tigercat Industries*, 2016 ONSC 1214 confirmed an employee's right to silence and the presumption of innocence carry into the workplace. In Quebec, Fasken's 2025 commentary on the ALT explicitly confirms failure to disclose unprompted is not itself grounds for dismissal. Triggers that convert silence into risk are bounded:

| Trigger | Ontario | Quebec |
|---|---|---|
| Direct question "Have you been charged…?" | Lying is for-cause termination risk; refusing is lawful but may cost the offer | Same — Quebec case law flags lying when asked as just cause for dishonesty, not for the charge |
| Signed BG-check consent form | Refusing is lawful; offer typically rescinded | Same; Law 25 requires consent |
| Contractual duty-to-report | Enforceable if clear and job-related | Enforceable but must still pass s.18.2 connection test |
| Federal Reliability / Secret clearance | **Must disclose**; file placed on hold until disposition | Same |
| PEO P.Eng. initial licensure or reinstatement | **Must disclose** — Q7 asks about guilt findings, Q8 about active investigations | Same, via OIQ |
| Bare SWE offer at Toronto SaaS startup using Certn basic | **No legal trigger** — answer "No" to a conviction question truthfully | Same, and s.18.2 may extend additional protection |

The "ever charged" vs "ever convicted" distinction on any form is the single highest-stakes moment. A conviction question: if there is no conviction, **answer "No" truthfully**. A charge question: lying is for-cause termination; truthful minimal acknowledgment or declining consent are the two lawful options. Read every form word-for-word, and have counsel review before signing.

### Script options, spectrum

**Script 1 — Silent (form asks only about convictions).** Answer "No." This is the default for most standard-tier Toronto/Montreal tech roles using Certn basic or Sterling basic.

**Script 2 — Minimal acknowledgment if directly asked.** *"I want to answer your question directly. There is a matter currently before the courts in which I have been charged and am defending. I am presumed innocent, the matter has not been tried, and on the advice of counsel I'm not able to discuss the details or the underlying allegations. If your process requires more at a later stage, I'd be glad to have my lawyer of record correspond with your legal or HR team. I'm fully able to perform the duties of the role and my availability is unaffected."*

**Script 3 — Proactive heads-up at conditional offer when enhanced check likely.** *"Before [Company] proceeds with the background verification, I want to flag one item proactively so you're not caught off guard. There is a matter currently before the courts in which I am an accused person. I am presumed innocent; the matter is being defended; I'm represented by counsel; and on counsel's advice I'm not in a position to discuss specifics. The matter is wholly unrelated to [the duties of this role], and it has not affected and will not affect my ability to perform the work. My lawyer, [Name], at [Firm], is available to confirm the procedural status in writing if your team finds that helpful. I'd ask that this be treated with the usual confidentiality you'd extend to any pre-employment medical or legal information."*

**Script 4 — Fuller context, lawyer-coordinated.** Use only for senior/fiduciary roles, regulated professions, or federal clearance, and only after counsel review. Frame: charge category only (no narration of conduct), procedural stage, counsel contact, release-conditions statement regarding operational capacity, non-nexus to duties, request for confidentiality arrangement.

**Script 5 — Decline-and-document.** *"Thanks for sending the consent form. I'm happy to consent to verification of identity, education, prior employment, and professional references. I'm not in a position to consent to an enhanced police information check or vulnerable-sector check for this role, as I understand the position does not involve [working with vulnerable populations / classified information], and the Police Record Checks Reform Act contemplates proportionality. If [Company] regards this check as essential, I'd appreciate a written explanation of the specific, job-related reason, so I can reconsider."* Most employers will rescind; this preserves a paper trail useful for wrongful-dismissal argument.

Core linguistic rules across all scripts: do not narrate facts, do not admit conduct, do not apologize in a way implying guilt, reference the presumption of innocence, offer lawyer of record as a contact channel rather than details.

### Reference vs background checks in the funnel

References typically occur at final round or verbal offer; background checks after written conditional offer and before start. References are a defamation-risk channel — a referee who learns of the charge from media and volunteers it creates exposure. Mitigations: select referees who don't know; brief tightly on what they'll be asked; use supervisors from roles ended before the charge; if a referee knows, a calm preparatory conversation asking them to refer the topic back to you; avoid media-adjacent referees. Accelerating reference collection to get a written offer in hand before the background-check stage strengthens any later wrongful-dismissal posture (*Kim v. BT Express*).

### If a conditional offer is rescinded

First 72 hours: do not sign anything. Request written reasons in specific terms ("the specific finding in the background report that caused the rescission, and the specific condition of the offer that you consider unmet"). Request a copy of the background report under PRCRA and PIPEDA rights. Request reconsideration via written, lawyer-drafted submission covering presumption of innocence, non-nexus, and any mitigating context not prejudicing criminal defence. Keep every communication in writing; turn phone calls into email recaps.

Legal recourse. **Ontario HRTO is weak on bare pending charges** (de Pelham line) but may offer an angle if the rescission implicates a secondary protected ground. Wrongful dismissal / breach of conditional offer in Superior Court or Small Claims is the stronger Ontario lever (*Kim v. BT Express Freight Systems*; *Lawrence v. Norwood Industries*) — even new hires routinely recover three-plus months of common-law reasonable notice. Consumer Reporting Act claim against the vendor if the report is inaccurate. **Quebec is stronger**: CDPDJ complaint under s.18.2 where no objective connection is proven (Proulx 2015, Absi 2025 QCTDP) yields moral and punitive damages; Tribunal administratif du travail s.124 applies if already hired; Civil Code parallels Ontario wrongful dismissal.

Employment-lawyer shortlist. Toronto: Whitten & Lublin, Samfiru Tumarkin LLP, Monkhouse Law (rescinded-offer alumni), Rudner Law (PRCRA + record-check proportionality), Achkar Law, Grosman Gale Fletcher Hopkins. Montreal: Fasken (s.18.2 commentary), Norton Rose Fulbright Montréal, Poudrier Bradet, Melançon Marceau Grenier Cohen, Roy Bélanger Avocats. For criminal-defence-employment crossover: Mark Zinck (Toronto, accused.ca), Daniel Brown Law.

Reputational containment: prefer private negotiation over public filing (HRTO and court filings are indexable); if settling, insist on full confidentiality, a scripted neutral reference for future employers, mutual non-disparagement, no admission, and return/destruction of the background-check file; avoid social-media posts; watch for news coverage and discuss publication bans with defence counsel.

### Practical reality check

Confirmed across multiple sources (Certn's own docs, Dickinson-Wright on Ontario PRCRA, Commissionaires, RCMP dissemination policy): **basic name-based CPIC checks that dominate standard tech hiring return conviction information only**, not pending charges. Enhanced / Level 2 / CRJMC products do return outstanding charges and judicial orders. Vulnerable Sector Checks add exceptional disclosure of non-conviction information. Federal Reliability and Secret clearance processes require self-disclosure of pending charges and will place the file on hold until disposition. US CBP has direct CPIC access and can see pending charges at the border — relevant for any role requiring US travel, independent of Canadian employment disclosure.

Operational checklist: retain defence counsel who will receive procedural inquiries from HR on your behalf; order your own name-based CPIC now so you know what a basic check shows; identify release conditions affecting work; for each role, ask before signing consent which vendor and which tier they use; match script to tier; if rescinded, preserve the email trail and retain employment counsel within five business days; never discuss allegations with anyone but defence counsel.

## 9. Risk management

**Timeline realism**. The pending charge does not automatically derail a sub-60-day offer timeline because most Toronto/Montreal private-sector tech employers run conviction-only checks. Timeline compressors: strong UofT alumni referrals, pre-built pipeline, public GitHub activity, willingness to work on-site, broad role flexibility. Timeline extenders: defence-contractor / banking / healthcare / government roles (broader checks); roles requiring security clearance; large-enterprise bureaucracy (4–8 weeks offer cycle). For a UofT CompE grad with a credible portfolio in the current market, **two to five offers is a reasonable expectation if the pipeline is run at the volumes and sequences above**. Do not be discouraged by Week 1–2 silence — response lag is 1–3 weeks.

**Contract and freelance bridge income**. Platform background-check summary:

| Platform | Verification | Criminal check |
|---|---|---|
| Upwork | Government ID + video identity verification | No criminal check by default; Enterprise engagements can request, candidate can decline |
| Toptal | Language + personality interview → technical screen → test project; 3–8 week process | No criminal check for standard freelance engagements (internal Toptal roles differ) |
| Braintrust | Profile + 10-minute video screen | Per ToS, no criminal check unless specifically agreed per engagement |
| Contra | Government ID + Stripe payment verification | No criminal check — identity only |
| Direct clients | Whatever they decide — usually nothing for short contracts | Generally none |

Direct-client acquisition is the safest and highest-rate path: X/Twitter founder circles, Indie Hackers, cold LinkedIn outreach to seed/Series A founders, UofT EAN, agency subcontracting (Toronto Shopify Plus agencies, Jam3-adjacent shops), StaffEng and Rands Leadership Slack communities. Canadian senior SWE contract rates in 2025–26: platform rates ~$35–80 CAD/hr (Glassdoor, ZipRecruiter); Robert Half 2026 Guide pegs Toronto senior SWE salary at $125–170k annualized; direct-client rates for a UofT CompE grad with a niche portfolio realistically start at $75–100 CAD/hr and scale to $150+ with one repeat client.

Tax considerations: sole proprietor (simplest, T2125 flow-through); incorporation as CCPC (worth it above ~$90–100k/yr net or where liability matters; $300–1,500 setup + $1.5–3k/yr accounting); GST/HST registration threshold **$30,000 in worldwide taxable supplies over four consecutive quarters** (ON 13% HST, QC 5% GST + 9.975% QST); Quick Method election via Form GST74 often favourable.

**Trial dates and start dates**. Do not reveal trial dates to recruiters or hiring managers — ever. Negotiate standard 2–4 week start dates. If a conflict arises, use neutral language ("I have a prior commitment that week"). Longer deferrals (8+ weeks) are awkward for most tech employers; avoid unless unavoidable. After verdict, if acquitted or charges withdrawn, apply to local police and the RCMP for destruction/purging of non-conviction records in CPIC to prevent future checks from surfacing the incident.

**Insurance for contract work**. Professional liability (E&O) is the core policy — $1–2M CAD coverage, premiums ~$700–1,800/yr via Zensurance, Apollo, or Foxquilt. Commercial General Liability often bundled. Cyber liability recommended if handling client data. Directors & Officers only if taking an officer role. Personal umbrella $1–2M at ~$200–400/yr. Most clients require a Certificate of Insurance; Zensurance/Apollo issue these in 15 minutes.

**Mental health and pacing**. Evidence-based stack: 9-8-8 Suicide Crisis Helpline (988.ca, 24/7 bilingual, operated by CAMH); CAMH outpatient programs (family-doctor referral or Connex Ontario 1-866-531-2600); **John Howard Society of Ontario** specifically supports accused persons (Bail Verification & Supervision, community/housing/employment/mental-health navigation at Toronto/Hamilton/Ottawa chapters); Elizabeth Fry Society; private forensic-familiar psychologists ($180–250/session, OHIP doesn't cover but benefits often do).

Sustainable search rhythm: **6 hours of focused job-search work per day, not 12**; one full day per week off; 30–45 minutes daily exercise; consistent sleep 7–9 hours; doom-spiral circuit breaker (close laptop, walk, eat, re-evaluate after 2 hours); minimum 2 non-transactional human interactions per week; peer support via CMHA chapters or JHS-facilitated groups. Work with both criminal defence counsel and a therapist who knows counsel exists — they do different jobs. Financial stress management: cut discretionary spending in Week 1 not Month 3; recalculate runway weekly; arrange a personal line of credit before it's needed (banks assess on recent employment); check Service Canada EI eligibility even if not claiming.

## 10. Final deliverables

### 10.1 Top 50 target companies ranked by role-fit × check-leniency × hiring velocity

Ranked for a CompE grad with 5G/networking + graphics + web + ML-for-graphics profile and pending-charge constraint. Composite scoring: role fit (high/med/low), check stringency (lower = better for this candidate), velocity (hot/steady/slow). **Montreal weighted up one notch given s.18.2 legal advantage.**

**Tier 1 — apply immediately (highest composite)**

| # | Company | City | Rationale | ATS |
|---|---|---|---|---|
| 1 | Ericsson Montréal (BCSS/GAIA) | MTL | 5gcx.ai bullseye; $630M Innovation Fund; medium stringency; hot | Eightfold |
| 2 | Matrox | MTL (Dorval) | Rare graphics-hardware + systems fit; private Quebec-owned; low-med stringency | Custom |
| 3 | Waabi | TOR | Neural rendering + ML + systems convergence; $750M Series C; medium stringency | Lever |
| 4 | SideFX (Houdini) | TOR | Pure graphics fit; AI-workflow roles; low-med stringency | Custom |
| 5 | Ericsson / Ciena Ottawa | Ottawa remote | 5G + networking; steady 2026 new-grad roles | Eightfold / Workday |
| 6 | ServiceNow Montréal (ex-Element AI) | MTL | AI research flagship; medium stringency; hot | Workday |
| 7 | Behaviour Interactive | MTL | 28–35 open eng roles; 4-day week; low-med stringency | Lever |
| 8 | AMD Markham | TOR | Graphics drivers + graphics-ML; export control (citizen/PR only) | Custom |
| 9 | EA Motive / SEED | MTL | Gen-AI-for-games research; medium stringency | Workday |
| 10 | Moment Factory | MTL | Unreal + creative tech + backend; 20+ open; low-med stringency | Lever |
| 11 | NVIDIA Toronto | TOR | Graphics + ML; expanding 2026; medium stringency | Workday |
| 12 | Cohere | TOR | LLM systems/ML; hot; Greenhouse-only pipeline (publicly stated) | Greenhouse |
| 13 | Ubisoft Montréal | MTL | Golang platform + gameplay; medium stringency; s.18.2 | SmartRecruiters |
| 14 | Coveo | MTL/QC | AI search; Quebec-HQ (strong s.18.2); steady | Greenhouse |
| 15 | Shopify Montréal / Toronto | Both | Remote-first; Ruby/Rails at scale; medium stringency | Ashby |

**Tier 2 — strong fit, apply Week 2–3**

| # | Company | City | Rationale | ATS |
|---|---|---|---|---|
| 16 | Autodesk TOR/MTL | Both | Maya/Fusion + AI Research; medium stringency | Workday |
| 17 | Tenstorrent | TOR | AI HW/SW; check citizenship (export control) first | Greenhouse |
| 18 | Uken Games | TOR | F2P mobile + backend; med stringency | Custom |
| 19 | Rodeo FX | MTL | Graphics pipeline (Python/USD/Houdini); TPN stringency | SmartRecruiters |
| 20 | 1Password | TOR | Web + security systems; SOC2 med-high stringency | Ashby |
| 21 | Ada | TOR | AI customer-service agents; low stringency | Greenhouse |
| 22 | Faire | TOR | Marketplace backend + ML; medium stringency | Greenhouse |
| 23 | Geotab | TOR (Oakville) | Telematics/IoT + cloud; new Toronto office; med-high | SmartRecruiters |
| 24 | Snowed In Studios | Ottawa | AAA co-dev; remote-Toronto possible; low-med | Workable |
| 25 | Haven Studios | MTL | Unreal AAA; medium-high (publicly discloses offer-stage criminal checks) | Greenhouse |
| 26 | Compulsion Games | MTL | Unreal gameplay; Microsoft parent; medium stringency | SmartRecruiters |
| 27 | Gameloft Montréal | MTL | Cross-platform gameplay + data science; low-med stringency | SmartRecruiters |
| 28 | Mila | MTL | Academic ML research; low stringency | Workable |
| 29 | Lightspeed Montreal/Toronto | Both | POS + payments; medium-high for payments roles | Greenhouse |
| 30 | Framestore Montréal | MTL | VFX pipeline; TPN medium-high | Greenhouse |

**Tier 3 — good fit with higher check stringency or narrower hiring**

| # | Company | City | Rationale | ATS |
|---|---|---|---|---|
| 31 | Red Barrels / Thunder Lotus / Tribute Games | MTL | Indie Quebec games; low stringency; slow-steady | Custom/email |
| 32 | Drinkbox / Capybara | TOR | Indie games; low stringency; email-only (manual) | Custom/email |
| 33 | BenchSci | TOR | Pharma ML; med-high stringency | Lever |
| 34 | Jane.app | Remote (Van HQ) | Rails healthcare; med-high (PHIPA/HIPAA) | Lever |
| 35 | League | TOR | Healthcare platform + AI agents; med-high | Greenhouse |
| 36 | Klick Health | TOR | Applied Sciences + tech; med-high | SmartRecruiters |
| 37 | AlayaCare | MTL | Home healthcare SaaS; high (HIPAA + Law 25) | Greenhouse |
| 38 | Hopper | MTL | Travel + payments; med-high; cautious hiring | Ashby |
| 39 | Hivestack / Sharethrough | MTL/TOR | Adtech systems; low-med stringency | Greenhouse/Lever |
| 40 | GSoft (Workleap) | MTL | .NET/React SaaS; low-med | Greenhouse |

**Tier 4 — valid but highest stringency; only apply with clean credit and accepted risk**

| # | Company | City | Rationale | ATS |
|---|---|---|---|---|
| 41 | Wealthsimple | TOR | OSFI-regulated fintech; enhanced + credit; post-$750M raise | Ashby |
| 42 | Layer 6 AI / TD Bank | TOR | Highest stringency in set (enhanced + credit + fingerprint) | Workday |
| 43 | Float | TOR | MSB fintech; high | Likely Ashby |
| 44 | KOHO | TOR | Banking-licence path; high | Ashby |
| 45 | Neo Financial | TOR | Publicly states screening required; high | Lever |
| 46 | Nuvei | MTL | PCI-DSS payments; high | Workable |
| 47 | Bell / Rogers / TELUS | Both | Telecom; high (enhanced + credit via BackCheck) | Workday |
| 48 | CGI Montréal | MTL | Gov contractor; high (Reliability/Secret required for many roles) | Njoyn |
| 49 | Qualcomm Canada | TOR (Markham) | 5G modem + graphics; high (US export control) | Workday |
| 50 | Ciena Kanata | Ottawa | Optical/5G systems; med-high | Workday |

**Explicit avoid (until disposition)**: federal-clearance positions; Controlled Goods Program designated roles; vulnerable-sector positions; roles explicitly requiring fingerprint-based RCMP checks. For Tier-4 companies, the decision is an individual risk call — Quebec-HQ entities (Nuvei, CGI Montreal) benefit from s.18.2 even at high stringency.

### 10.2 Bot feature spec — prioritized implementation tickets

Ready to paste into Claude Code. Sized for single developer, two-month horizon.

**Sprint 0 — Foundation (Days 1–3)**
- **TKT-001**: Bootstrap repo with `uv`, Python 3.12, pyproject dependencies (anthropic, httpx, playwright, psycopg, pgvector, pydantic-settings, structlog, selectolax, typer, tenacity, ollama, feedparser, sentry-sdk, resend).
- **TKT-002**: Install Postgres 16 + pgvector locally; apply the schema in §5 verbatim; write `alembic` migrations.
- **TKT-003**: Install Ollama; pull `nomic-embed-text-v1.5`; verify 768-dim output.
- **TKT-004**: Seed 50 target companies (Tier 1–3 from §10.1) into `companies` with ATS platform, stringency classification, and canonical careers URL.

**Sprint 1 — Ingestion (Days 4–10)**
- **TKT-010**: Implement `ats/greenhouse.py` client: `GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`; parse to canonical posting schema; idempotent upsert keyed on `url_canonical`.
- **TKT-011**: Implement `ats/lever.py`: `GET api.lever.co/v0/postings/{company}?mode=json`.
- **TKT-012**: Implement `ats/ashby.py`: `GET api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true`.
- **TKT-013**: Implement `ats/smartrecruiters.py`: `GET api.smartrecruiters.com/v1/companies/{id}/postings?city=Toronto|Montreal`.
- **TKT-014**: Implement `ats/workable.py`: `GET apply.workable.com/api/v1/widget/accounts/{company}`.
- **TKT-015**: Implement `ats/workday.py` as a generic tenant client accepting `(tenant, wd_server, site)` speaking `POST /wday/cxs/{tenant}/{site}/jobs` with pagination.
- **TKT-016**: Implement `ingest/hn.py` using HN Algolia API; parse monthly "Who is Hiring" thread.
- **TKT-017**: Implement `ingest/remote_boards.py`: Remote OK JSON, We Work Remotely RSS, Remotive, Jobicy.
- **TKT-018**: Implement `ingest/adzuna.py`: Canadian aggregator safety net.
- **TKT-019**: systemd timer units (or launchd plists) for each ingester with cadences from §5.

**Sprint 2 — Classification & Dedup (Days 11–15)**
- **TKT-020**: Canonical URL extractor (strip UTMs, session IDs); `normalize_title()` function.
- **TKT-021**: `title_company_hash` sha1; unique index.
- **TKT-022**: Build regex pattern libraries for strict/lenient/fit keywords (§4); emit `strict_hits` JSONB.
- **TKT-023**: Precompute user profile embedding vector from master resume + portfolio manifest.
- **TKT-024**: Embed every ingested posting via Ollama; store in `posting_embeddings`; HNSW index.
- **TKT-025**: Cosine near-duplicate detection at threshold 0.92 within `company_id` over 90-day window; set `canonical_posting_id`.
- **TKT-026**: Cross-source rank preference: prefer ATS over LinkedIn/Indeed.
- **TKT-027**: Haiku 4.5 batched structured extraction (10 postings/call): seniority, salary, remote_type, location, tech_stack, role_category, final fit_score. JSON response format.
- **TKT-028**: Compute `final_rank = fit_score × (1 - 0.6 × check_risk_score) × freshness_decay × salary_factor × remote_flex`.

**Sprint 3 — Portfolio RAG + Drafter (Days 16–20)**
- **TKT-030**: Portfolio ingestion pipeline: fetch limiliminal, 5gcx.ai, vimy.ai, GitHub READMEs, master resume; chunk at 512 tokens / 50 overlap via recursive splitter; attach skill-tag metadata; embed; store in `portfolio_chunks`.
- **TKT-031**: Drafter: retrieve top-8 portfolio chunks by cosine against posting; construct cached system prompt (resume + top-40 general chunks, `cache_control: ephemeral`); Sonnet 4.6 call with JSON schema (tailored_bullets, cover_letter, talking_points, red_flags).
- **TKT-032**: Resume-renderer: template (LaTeX or Typst or markdown→PDF via WeasyPrint) accepts tailored bullets; outputs `resume_versions.rendered_pdf_path`.

**Sprint 4 — Tracker UI + Monitoring (Days 21–25)**
- **TKT-040**: Minimal web UI via FastAPI + HTMX: kanban board over `applications` table (queued → applied → acknowledged → phone → onsite → offer → rejected); click-through to posting detail.
- **TKT-041**: Daily Resend digest email: top 15 new postings by final_rank, applications sent yesterday, follow-ups due today, running API spend.
- **TKT-042**: Sentry integration (DSN, `traces_sample_rate=0.1`); wrap every scraper with `@sentry_sdk.trace`.
- **TKT-043**: `metric_events` emit helpers; `v_daily_metrics` view.

**Sprint 5 — Scraping Expansion (Days 26–35, optional)**
- **TKT-050**: Playwright LinkedIn public jobs search (authenticated optional); residential proxy via Decodo PAYG.
- **TKT-051**: Playwright Indeed Canada; Cloudflare-aware; 24h cadence.
- **TKT-052**: BuiltIn Toronto discovery scraper → detect ATS from careers-page URL fingerprints → enqueue new companies.
- **TKT-053**: CAPTCHA fallback via 2Captcha (only if needed).

**Watch-out in implementation**: never wire the bot to an auto-submit action without an explicit per-posting human confirmation in the tracker UI. The reason is not ToS — it is that consent forms and required fields vary enough that silent submission will produce misrepresentations (e.g., the "ever charged" question) that destroy the defence strategy. The bot drafts; the human submits.

### 10.3 30/60/90-day action plan

**Days 1–7 (Week 1) — foundation.** Retain criminal defence counsel for procedural inquiries; order your own name-based CPIC; review release conditions for work conflicts. Finalize master resume + 4 role variants (web, graphics, systems/5G, ML-for-graphics). Update limiliminal hero + 5 project cards; audit 5gcx.ai for role-lane writeups; clarify vimy.ai tagline. Pin 6 GitHub repos with real READMEs; begin daily real commits. Stand up LinkedIn: headline, Featured section (limiliminal + best repo + 5gcx.ai + vimy.ai + one writeup), skills packed, Open-to-Work recruiters-only. Build pipeline spreadsheet of 50 Tier 1–3 companies from §10.1 with ATS URL + 1–2 alumni/engineers per company. Stand up bot sprints 0–1 in parallel. **Day 7 output: 0 apps, pipeline loaded, bot ingesting from 50 companies.**

**Days 8–21 (Weeks 2–3) — high-volume outreach.** Run 10–15 apps/day: 2 Tier-A full-custom + 5–8 Tier-B tailored + 5–10 Tier-C Easy-Apply. 5 UofT alumni / target-engineer referral messages daily. Finish bot sprints 2–3 so classification and drafting are live by Day 14. Begin parallel LeetCode-medium and system-design prep 1 hour/day. Weekly: post one short technical update on LinkedIn; comment on 3–5 posts from people at target companies. **Day 21 output: ~180 applications sent, 30–50 referral conversations in flight.**

**Days 22–35 (Weeks 4–5) — conversion.** Follow up on Week-2 applications at 7–10 days. First screens begin landing. Maintain 8 apps/day top-of-funnel; begin stepping through technical screens; protect sleep before every phone screen. Decide per-role which disclosure script to use based on ATS and check tier. Consult defence counsel before signing any consent form. **Day 35 output: ~290 apps sent, 15–25 screens completed, 5–10 technical rounds active.**

**Days 36–50 (Weeks 6–7) — technical rounds + onsites.** Drop new apps to 3–5/day; redirect energy to onsite prep. Line up references (2–3 per active process; brief them tightly). For any conditional offer, review consent form with counsel before signing; use Script 1 / 2 / 3 based on check tier. **Day 50 output: 2–4 onsites completed, 1–3 conditional offers likely.**

**Days 51–60 (Week 8) — offers, negotiation, close.** Stall lagging processes to align timing. Compare offers on TC + start date + remote policy + check tier + cultural fit. Negotiate 2–4 week start dates (never disclose trial schedule). If any offer is rescinded post-check: do not sign anything, request written reasons, retain employment counsel within five business days. **Day 60 target: 1–3 signed offers; if none, pivot the remaining 30-day buffer to contract-bridge income via direct clients (§9), continue search at reduced volume.**

Parallel bot rollout track: sprints 0–1 complete Day 10; sprints 2–3 complete Day 20; sprint 4 complete Day 25; sprint 5 (scraping expansion) only if still searching Day 26+.

### 10.4 Watch-outs — highest-impact mistakes to avoid

**Misreading the consent form.** "Have you ever been convicted?" and "Have you ever been charged?" are legally different questions. Answering "No" to a conviction question when there is no conviction is truthful and correct; answering "No" to a charge question when there is a pending charge is for-cause termination exposure. Read every form word-for-word; route through counsel before signing.

**Assuming all check tiers are equivalent.** Basic name-based CPIC returns convictions only; enhanced and vulnerable-sector products do return pending charges. Ask the employer (before consenting) which vendor and which tier they use — frame it as "I want to make sure I complete the right consent."

**Applying to clearance-triggering roles prematurely.** Federal Reliability Status, Secret clearance, CGP designation, and vulnerable-sector positions require self-disclosure of pending charges and will place the file on hold until disposition. Avoid until resolved unless disclosure is affirmatively chosen.

**Volunteering information unprompted.** There is no general duty to volunteer a pending charge in either province. Silence where legally permissible is the default; Script 3 (proactive heads-up) is only for conditional-offer situations where an enhanced check is confirmed imminent. Never disclose in an interview unless directly and unambiguously asked.

**Relying on LinkedIn/Indeed alone.** Each requisition there pulls 200–500 Easy-Apply candidates in 48 hours; response rates are 2–5% cold. The data architecture that actually wins is ATS direct (Greenhouse/Lever/Ashby/SmartRecruiters) plus UofT-alumni referrals — route through both before cold LinkedIn.

**Treating the bot as an auto-submit machine.** The consent-form landmine makes silent submission categorically unsafe in this situation. The bot discovers, classifies, drafts, and tracks; the human reviews every consent screen before submission.

**Over-tailoring Tier C, under-tailoring Tier A.** The inverted allocation is common under time pressure. Tier A deserves full research and custom first paragraphs; Tier C is Easy-Apply-and-move-on. Mismatching the ratio wastes the scarcest resource (attention).

**Skipping references.** A sloppy reference check at the verbal-offer stage can derail a process the background check would have cleared. Brief every referee tightly; prefer supervisors from roles ended before the charge; where a referee knows of the matter, pre-agree with them to refer the topic back to you.

**Ignoring bail conditions that affect the role.** A role requiring US travel (common for Toronto/Montreal tech serving US clients) may be impossible under a bail no-travel condition, and US CBP can see pending charges in CPIC regardless of the employer. A role requiring specific hours or device access may conflict with curfew or electronic restrictions. Screen roles against conditions before investing application effort.

**Drifting away from mental-health infrastructure.** Isolation amplifies both job-search and pre-trial distress; sustained 12-hour search days destroy interview performance faster than rejections do. The 6-hour cap, one-day-off rule, daily exercise, and the dual-support model (criminal defence counsel + forensic-familiar therapist) are not optional — they are the binding constraints on everything else succeeding.

---

### Evidence-thinness flags

Several conclusions carry weaker evidence and should be treated as best-inference: (1) extension of Quebec s.18.2 to pending charges rests on Tribunal des droits de la personne decisions (Proulx 2015, Absi 2025 QCTDP), not Court of Appeal or SCC rulings squarely on pending charges; expect employer counsel to argue the textual "convicted" limitation. (2) Specific response rates for Toronto/Montreal tech are extrapolated from LinkedIn global data, Jobvite/Lever US studies, and Canadian aggregator reports — treat as directional, not precise. (3) Vendor product tiers (Certn/Sterling/Mintz/HireRight/Triton/ISB) change; confirm at the specific employer pre-consent. (4) "Shoppers Drug Mart / Home Depot Canada fair-chance hiring" claims in general commentary are not confirmed in primary Canadian sources. (5) Platform background-check policies (Upwork/Toptal/Braintrust/Contra) reflect current docs and community reports; verify at engagement time. (6) PEO continuing-disclosure obligations for non-licensees are ambiguous — PEO applications/reinstatements clearly require disclosure, but there is no publicly clear continuing self-report duty absent a complaint. None of the foregoing substitutes for advice from your own criminal defence counsel and, at offer stage, an employment lawyer in the relevant province.