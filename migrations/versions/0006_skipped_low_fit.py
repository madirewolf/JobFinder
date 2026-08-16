"""applications.skipped_low_fit status + skip_reason text

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-26

Adds a new terminal application status `skipped_low_fit` plus a `skip_reason`
column. Used by the new fit-gate that runs (cheap Haiku) before any curation
work. Postings that fail the gate land at this terminal status with a one-
sentence reason — and are NOT re-evaluated on subsequent `jfb draft top` runs
because the drafter only picks `queued` / `drafted` rows.

If you want to re-evaluate a `skipped_low_fit` row later (e.g. after editing
the master to demonstrate the missing domain), re-queue it via the UI — the
queue endpoint resets status to `queued`.

PostgreSQL note: `ALTER TYPE … ADD VALUE` cannot run inside a transaction in
the same statement as other DDL, so we use Alembic's `autocommit_block()`
to run it standalone first.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ADD VALUE must run outside a transaction
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status_enum ADD VALUE IF NOT EXISTS 'skipped_low_fit'")
    op.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS skip_reason TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_applications_skipped "
        "ON applications(status) WHERE status = 'skipped_low_fit'"
    )


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values cleanly. Drop the
    # column + index; the enum value persists harmlessly.
    op.execute("DROP INDEX IF EXISTS idx_applications_skipped")
    op.execute("ALTER TABLE applications DROP COLUMN IF EXISTS skip_reason")
