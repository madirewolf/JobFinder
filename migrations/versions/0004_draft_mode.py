"""applications.draft_mode + curate_payload — two-mode drafter

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-25

Adds two columns to `applications`:

  draft_mode        TEXT NOT NULL DEFAULT 'tailor'
                    CHECK (draft_mode IN ('tailor','curate'))

      Per-application choice of drafter behaviour. Tailor mode (the original)
      lets the model paraphrase your bullets to match the posting. Curate mode
      keeps your master verbatim — the model only selects which projects to
      include, pulls VERBATIM emphasis quotes from your master, and writes
      the cover letter / talking points. See drafter/prompts.py for both.

  curate_payload    JSONB NULL

      Curate-mode-only blob:
          {
            "selected_projects": ["capstone-bell412", ...],
            "dropped_projects":  ["limiliminal", ...],
            "emphasis_quotes":   [{"source": "resume.md", "quote": "..."}],
            "suggested_phrasings": [{"rationale": "...", "suggestion": "..."}]
          }

      For tailor-mode rows this stays NULL; bullets land in `tailored_bullets`
      as before so existing queries / templates still work.

Default is 'tailor' so all currently-queued and previously-drafted rows stay
on the original behaviour. Switch the default to 'curate' globally via the
JFB_DRAFT_MODE env var or `prefs.md`'s default-mode setting.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


UPGRADE_SQL = """
ALTER TABLE applications
    ADD COLUMN draft_mode TEXT NOT NULL DEFAULT 'tailor'
        CHECK (draft_mode IN ('tailor','curate')),
    ADD COLUMN curate_payload JSONB;

CREATE INDEX idx_applications_draft_mode ON applications(draft_mode);
"""

DOWNGRADE_SQL = """
DROP INDEX IF EXISTS idx_applications_draft_mode;
ALTER TABLE applications
    DROP COLUMN IF EXISTS curate_payload,
    DROP COLUMN IF EXISTS draft_mode;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
