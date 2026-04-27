"""add refresh job names

Revision ID: 0002_refresh_job_names
Revises: 0001_initial_schema
Create Date: 2026-04-14 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_refresh_job_names"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_jobs",
        sa.Column("job_name", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE refresh_jobs
        SET job_name = CASE
            WHEN job_type = 'MARKET_DATA_REFRESH' THEN 'refresh-prices'
            WHEN job_type = 'NEWS_REFRESH' THEN 'refresh-news'
            WHEN job_type = 'AI_REFRESH' THEN 'analyze-mock'
            WHEN job_type = 'SCORING_REFRESH' THEN 'score-universe'
            WHEN job_type = 'DAILY_REFRESH' THEN 'refresh-mock'
            ELSE 'manual-job'
        END
        """
    )
    op.alter_column(
        "refresh_jobs",
        "job_name",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=sa.text("'manual-job'"),
    )
    op.create_index("ix_refresh_jobs_job_name", "refresh_jobs", ["job_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_refresh_jobs_job_name", table_name="refresh_jobs")
    op.drop_column("refresh_jobs", "job_name")
