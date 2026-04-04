"""
app/db/models.py

SQLAlchemy ORM models for the AI-owned tables.

These tables are ONLY managed by this service (BizFlow AI Service).
All other tables (orders, products, customers, etc.) are owned by the
.NET backend and must NOT be defined or migrated here.

Naming convention:  ai_<feature>_<noun>
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Feature: Revenue Forecast
# ---------------------------------------------------------------------------

class AIRevenueForecast(Base):
    __tablename__ = "ai_revenue_forecasts"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]    = mapped_column(String(36), nullable=False, index=True)
    forecast_date: Mapped[str]  = mapped_column(String(10), nullable=False)   # YYYY-MM-DD
    forecast_revenue: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[float]  = mapped_column(Float, nullable=False)
    upper_bound: Mapped[float]  = mapped_column(Float, nullable=False)
    trend_note: Mapped[str | None]  = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime]  = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Feature: Anomaly Detection
# ---------------------------------------------------------------------------

class AIAnomalyAlert(Base):
    __tablename__ = "ai_anomaly_alerts"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]    = mapped_column(String(36), nullable=False, index=True)
    entity_type: Mapped[str]    = mapped_column(String(50), nullable=False)   # e.g. ORDER, IMPORT
    entity_id: Mapped[str]      = mapped_column(String(36), nullable=False)
    alert_type: Mapped[str]     = mapped_column(String(100), nullable=False)
    message: Mapped[str]        = mapped_column(Text, nullable=False)
    tier: Mapped[int]           = mapped_column(Integer, nullable=False)      # 1 = rule, 2 = LLM
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Feature: Reorder Suggestion
# ---------------------------------------------------------------------------

class AIReorderSuggestion(Base):
    __tablename__ = "ai_reorder_suggestions"

    id: Mapped[str]                 = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]        = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str]         = mapped_column(String(36), nullable=False)
    current_stock: Mapped[float]    = mapped_column(Float, nullable=False)
    reorder_point: Mapped[float]    = mapped_column(Float, nullable=False)
    suggested_reorder_qty: Mapped[float] = mapped_column(Float, nullable=False)
    generated_at: Mapped[datetime]  = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Feature: Product Insights
# ---------------------------------------------------------------------------

class AIProductInsight(Base):
    __tablename__ = "ai_product_insights"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]    = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str]     = mapped_column(String(36), nullable=False)
    insight_type: Mapped[str]   = mapped_column(String(50), nullable=False)   # TOP_SELLER | GROWTH_TREND | PROMOTE_CANDIDATE
    rank: Mapped[int]           = mapped_column(Integer, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    period_days: Mapped[int]    = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
