"""add_record_type_to_anomaly_alerts

Revision ID: a1b2c3d4e5f6
Revises: 278c5207c508
Create Date: 2026-05-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '278c5207c508'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_anomaly_alerts",
        sa.Column("record_type", sa.String(20), nullable=True),  # order | revenue | import | null (LLM_PATTERN)
    )


def downgrade() -> None:
    op.drop_column("ai_anomaly_alerts", "record_type")
