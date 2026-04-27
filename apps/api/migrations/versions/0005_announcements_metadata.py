"""add announcement metadata and scheduler job type

Revision ID: 0005_announcements_metadata
Revises: 0004_valuation_snapshot_currency
Create Date: 2026-04-15 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_announcements_metadata"
down_revision = "0004_valuation_snapshot_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE refresh_job_type ADD VALUE IF NOT EXISTS 'ANNOUNCEMENTS_REFRESH'")

    op.add_column(
        "announcements",
        sa.Column("provider", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column("exchange_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column("language", sa.String(length=16), nullable=False, server_default="zh"),
    )
    op.add_column(
        "announcements",
        sa.Column("as_of_date", sa.Date(), nullable=True),
    )
    op.execute("UPDATE announcements SET as_of_date = DATE(published_at) WHERE published_at IS NOT NULL")
    op.alter_column("announcements", "language", server_default=None)


def downgrade() -> None:
    op.drop_column("announcements", "as_of_date")
    op.drop_column("announcements", "language")
    op.drop_column("announcements", "exchange_code")
    op.drop_column("announcements", "provider")
