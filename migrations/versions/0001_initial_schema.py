"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


UPGRADE_SQL = """
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
    ats_token TEXT,
    careers_url TEXT,
    bg_check_stringency bg_stringency_enum NOT NULL DEFAULT 'unknown',
    bg_check_reasoning TEXT,
    hq_city TEXT,
    hq_province TEXT,
    headcount_est INT,
    tier SMALLINT,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, domain)
);
CREATE INDEX idx_companies_tier ON companies(tier) WHERE active;

CREATE TABLE postings (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,
    url_canonical TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_rank SMALLINT NOT NULL DEFAULT 5,
    raw_json JSONB NOT NULL,
    description_text TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    reposted_count INT NOT NULL DEFAULT 0,
    canonical_posting_id BIGINT REFERENCES postings(id),
    remote_type remote_type_enum NOT NULL DEFAULT 'unspecified',
    location TEXT,
    seniority TEXT,
    salary_min INT,
    salary_max INT,
    salary_currency CHAR(3) DEFAULT 'CAD',
    tech_stack TEXT[],
    role_category TEXT,
    fit_score REAL,
    check_risk_score REAL,
    final_rank REAL,
    strict_hits JSONB,
    lenient_hits JSONB,
    fit_hits JSONB,
    title_company_hash CHAR(40) NOT NULL
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
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE TABLE resume_versions (
    id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    template_path TEXT NOT NULL,
    rendered_pdf_path TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE applications (
    id BIGSERIAL PRIMARY KEY,
    posting_id BIGINT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    status application_status_enum NOT NULL DEFAULT 'queued',
    drafted_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    resume_version_id BIGINT REFERENCES resume_versions(id),
    cover_letter TEXT,
    tailored_bullets JSONB,
    talking_points JSONB,
    red_flags JSONB,
    consent_form_notes TEXT,
    tracking_notes TEXT,
    next_action_at TIMESTAMPTZ,
    referrer_email TEXT,
    referrer_name TEXT,
    submission_channel TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_applications_posting ON applications(posting_id);
CREATE INDEX idx_applications_status ON applications(status);

CREATE TABLE portfolio_chunks (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    project TEXT,
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pchunks_emb_hnsw ON portfolio_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
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
    operation TEXT NOT NULL,
    input_tokens INT,
    output_tokens INT,
    cache_read_tokens INT,
    cache_write_tokens INT,
    usd_cost NUMERIC(10, 6)
);
CREATE INDEX idx_llm_cost_ts ON llm_cost_log(ts DESC);
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS llm_cost_log CASCADE;
DROP TABLE IF EXISTS metric_events CASCADE;
DROP TABLE IF EXISTS portfolio_chunks CASCADE;
DROP TABLE IF EXISTS applications CASCADE;
DROP TABLE IF EXISTS resume_versions CASCADE;
DROP TABLE IF EXISTS posting_embeddings CASCADE;
DROP TABLE IF EXISTS postings CASCADE;
DROP TABLE IF EXISTS companies CASCADE;
DROP TYPE IF EXISTS application_status_enum;
DROP TYPE IF EXISTS ats_platform_enum;
DROP TYPE IF EXISTS bg_stringency_enum;
DROP TYPE IF EXISTS remote_type_enum;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
