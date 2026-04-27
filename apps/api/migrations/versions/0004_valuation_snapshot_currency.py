"""add valuation currency

Revision ID: 0004_valuation_snapshot_currency
Revises: 0003_fundamentals_real_fields
Create Date: 2026-04-15 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_valuation_snapshot_currency"
down_revision = "0003_fundamentals_real_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "valuation_snapshots",
        sa.Column("currency", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("valuation_snapshots", "currency")
