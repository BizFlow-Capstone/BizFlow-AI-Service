"""create_ai_tables

Revision ID: 278c5207c508
Revises: 
Create Date: 2026-04-03 20:23:50.898784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '278c5207c508'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ai_revenue_forecasts — EMA 7-day forecasts per location
    op.create_table(
        "ai_revenue_forecasts",
        sa.Column("id",               sa.String(36),  primary_key=True),
        sa.Column("location_id",      sa.String(36),  nullable=False),
        sa.Column("forecast_date",    sa.String(10),  nullable=False),    # YYYY-MM-DD
        sa.Column("forecast_revenue", sa.Float(),     nullable=False),
        sa.Column("lower_bound",      sa.Float(),     nullable=False),
        sa.Column("upper_bound",      sa.Float(),     nullable=False),
        sa.Column("trend_note",       sa.Text(),      nullable=True),
        sa.Column("generated_at",     sa.DateTime(),  nullable=False),
    )
    op.create_index("ix_ai_revenue_forecasts_location_id", "ai_revenue_forecasts", ["location_id"])

    # ai_anomaly_alerts — rule-based (tier 1) + LLM (tier 2) alerts
    op.create_table(
        "ai_anomaly_alerts",
        sa.Column("id",          sa.String(36),   primary_key=True),
        sa.Column("location_id", sa.String(36),   nullable=False),
        sa.Column("entity_type", sa.String(50),   nullable=False),   # ORDER | IMPORT
        sa.Column("entity_id",   sa.String(36),   nullable=False),
        sa.Column("alert_type",  sa.String(100),  nullable=False),
        sa.Column("message",     sa.Text(),       nullable=False),
        sa.Column("tier",        sa.Integer(),    nullable=False),   # 1 = rule, 2 = LLM
        sa.Column("created_at",  sa.DateTime(),   nullable=False),
    )
    op.create_index("ix_ai_anomaly_alerts_location_id", "ai_anomaly_alerts", ["location_id"])

    # ai_reorder_suggestions — reorder-point formula results
    op.create_table(
        "ai_reorder_suggestions",
        sa.Column("id",                    sa.String(36), primary_key=True),
        sa.Column("location_id",           sa.String(36), nullable=False),
        sa.Column("product_id",            sa.String(36), nullable=False),
        sa.Column("current_stock",         sa.Float(),    nullable=False),
        sa.Column("reorder_point",         sa.Float(),    nullable=False),
        sa.Column("suggested_reorder_qty", sa.Float(),    nullable=False),
        sa.Column("generated_at",          sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_reorder_suggestions_location_id", "ai_reorder_suggestions", ["location_id"])

    # ai_product_insights — TOP_SELLER / GROWTH_TREND / PROMOTE_CANDIDATE
    op.create_table(
        "ai_product_insights",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("location_id",  sa.String(36), nullable=False),
        sa.Column("product_id",   sa.String(36), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("rank",         sa.Integer(),  nullable=False),
        sa.Column("metric_value", sa.Float(),    nullable=False),
        sa.Column("period_days",  sa.Integer(),  nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_product_insights_location_id", "ai_product_insights", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_product_insights_location_id",  table_name="ai_product_insights")
    op.drop_table("ai_product_insights")

    op.drop_index("ix_ai_reorder_suggestions_location_id", table_name="ai_reorder_suggestions")
    op.drop_table("ai_reorder_suggestions")

    op.drop_index("ix_ai_anomaly_alerts_location_id", table_name="ai_anomaly_alerts")
    op.drop_table("ai_anomaly_alerts")

    op.drop_index("ix_ai_revenue_forecasts_location_id", table_name="ai_revenue_forecasts")
    op.drop_table("ai_revenue_forecasts")
