"""daily_metrics materialized view + llm_cost monthly rollup

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


UPGRADE_SQL = """
CREATE MATERIALIZED VIEW v_daily_metrics AS
SELECT date_trunc('day', ts) AS day,
       metric,
       sum(value) AS total
FROM metric_events
GROUP BY 1, 2;

CREATE UNIQUE INDEX idx_v_daily_metrics_day_metric
    ON v_daily_metrics(day, metric);

-- Monthly LLM spend rollup, cheap to query on every page load
CREATE VIEW v_llm_spend_monthly AS
SELECT date_trunc('month', ts) AS month,
       operation,
       model,
       sum(input_tokens) AS input_tokens,
       sum(output_tokens) AS output_tokens,
       sum(cache_read_tokens) AS cache_read_tokens,
       sum(cache_write_tokens) AS cache_write_tokens,
       sum(usd_cost) AS usd_cost
FROM llm_cost_log
GROUP BY 1, 2, 3;
"""

DOWNGRADE_SQL = """
DROP VIEW IF EXISTS v_llm_spend_monthly;
DROP MATERIALIZED VIEW IF EXISTS v_daily_metrics;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
