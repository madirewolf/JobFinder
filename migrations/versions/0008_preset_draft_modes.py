"""applications.draft_mode — allow preset pool modes

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-22

Widens the `draft_mode` CHECK constraint so the column can store preset pool
modes ("preset:autonomy-robotics", "preset:graphics-3d", …) in addition to
the original 'tailor' / 'curate'. Preset modes attach a pre-built, pool-
specific résumé verbatim — no LLM, no master transform.

The original inline check from migration 0004 is named
`applications_draft_mode_check` (Postgres' default for a column CHECK). We
drop it and re-create a named constraint that also accepts the `preset:`
prefix.

Reversal drops the widened constraint and restores the tailor/curate-only
one. (Any rows already at a preset mode would violate the restored check;
the downgrade therefore first rewrites them to 'curate' — lossless enough
for a personal-use dev DB.)
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_draft_mode_check")
    op.execute(
        """
        ALTER TABLE applications
            ADD CONSTRAINT applications_draft_mode_check
            CHECK (draft_mode IN ('tailor', 'curate') OR draft_mode LIKE 'preset:%')
        """
    )


def downgrade() -> None:
    op.execute("UPDATE applications SET draft_mode = 'curate' WHERE draft_mode LIKE 'preset:%'")
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_draft_mode_check")
    op.execute(
        """
        ALTER TABLE applications
            ADD CONSTRAINT applications_draft_mode_check
            CHECK (draft_mode IN ('tailor', 'curate'))
        """
    )
