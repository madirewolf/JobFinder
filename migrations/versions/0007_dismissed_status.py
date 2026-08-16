"""applications.dismissed status — human says 'no thanks' to a posting

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-28

Adds a new terminal status `dismissed` for postings the operator manually
rejects from the browser (e.g. "Queensland-only", "no remote", "wrong
domain even though the bot scored it well"). Hidden from /top by default,
visible only via `?show_dismissed=1`. Different from `skipped_low_fit`
(bot decided) and `withdrawn` (operator quit mid-application).

Reversal path: re-queueing the row resets it to 'queued' as before.

PostgreSQL note: ALTER TYPE ADD VALUE must run outside any transaction
holding the type. Same autocommit-block trick as migration 0006.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status_enum ADD VALUE IF NOT EXISTS 'dismissed'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values cleanly. The value
    # stays harmlessly; nothing else to undo.
    pass
