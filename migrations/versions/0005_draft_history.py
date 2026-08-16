"""applications.draft_history — keep prior drafts when re-drafting

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-25

Adds `applications.draft_history JSONB DEFAULT '[]'::jsonb`. Each time the
drafter overwrites an existing application's payload (cover letter, bullets,
talking points, red flags, curate_payload), the OLD payload gets snapshotted
into the front of `draft_history` so it stays accessible for review/compare.

Snapshot shape (newest first):
    [
      {
        "draft_mode": "tailor" | "curate",
        "drafted_at": "<isoformat>",
        "cover_letter": "...",
        "tailored_bullets": [...] | null,
        "talking_points": [...],
        "red_flags": [...],
        "curate_payload": {...} | null
      },
      ...
    ]

Pairs with a relaxed queue_for_draft that lets the human re-queue a posting
from 'ready_for_human' / 'drafted' back to 'queued' (status='applied' and
beyond stay protected — those reflect real external state).
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
ALTER TABLE applications
    ADD COLUMN draft_history JSONB NOT NULL DEFAULT '[]'::jsonb;
"""

DOWNGRADE_SQL = """
ALTER TABLE applications DROP COLUMN IF EXISTS draft_history;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
