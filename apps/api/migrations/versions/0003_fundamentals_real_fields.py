"""add real fundamentals fields

Revision ID: 0003_fundamentals_real_fields
Revises: 0002_refresh_job_names
Create Date: 2026-04-14 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_fundamentals_real_fields"
down_revision = "0002_refresh_job_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "valuation_snapshots",
        sa.Column("enterprise_value", sa.Numeric(24, 4), nullable=True),
    )
    op.add_column(
        "financial_metrics",
        sa.Column("operating_margin", sa.Numeric(10, 6), nullable=True),
    )
    op.add_column(
        "financial_metrics",
        sa.Column("roa", sa.Numeric(10, 6), nullable=True),
    )
    op.add_column(
        "financial_metrics",
        sa.Column("debt_to_equity", sa.Numeric(12, 6), nullable=True),
    )
    op.add_column(
        "financial_metrics",
        sa.Column("overseas_revenue_ratio", sa.Numeric(10, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("financial_metrics", "overseas_revenue_ratio")
    op.drop_column("financial_metrics", "debt_to_equity")
    op.drop_column("financial_metrics", "roa")
    op.drop_column("financial_metrics", "operating_margin")
    op.drop_column("valuation_snapshots", "enterprise_value")
