"""profile_vectors table + llm_classified_at flag

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


UPGRADE_SQL = """
CREATE TABLE profile_vectors (
    id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    embedding vector(768) NOT NULL,
    model TEXT NOT NULL DEFAULT 'nomic-embed-text-v1.5',
    source_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE postings ADD COLUMN llm_classified_at TIMESTAMPTZ;
CREATE INDEX idx_postings_llm_pending
    ON postings(first_seen DESC)
    WHERE llm_classified_at IS NULL
      AND canonical_posting_id IS NULL
      AND closed_at IS NULL;
"""

DOWNGRADE_SQL = """
DROP INDEX IF EXISTS idx_postings_llm_pending;
ALTER TABLE postings DROP COLUMN IF EXISTS llm_classified_at;
DROP TABLE IF EXISTS profile_vectors;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
