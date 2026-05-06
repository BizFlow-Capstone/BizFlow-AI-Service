"""
app/db/models.py

SQLAlchemy ORM models for the AI-owned tables.

These tables are ONLY managed by this service (BizFlow AI Service).
All other tables (orders, products, customers, etc.) are owned by the
.NET backend and must NOT be defined or migrated here.

Naming convention:  ai_<feature>_<noun>
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Feature: Revenue Forecast
# ---------------------------------------------------------------------------

class AIRevenueForecast(Base):
    __tablename__ = "ai_revenue_forecasts"
    __table_args__ = (
        UniqueConstraint("location_id", "forecast_date", name="uq_forecast_location_date"),
    )

    id: Mapped[str]             = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]    = mapped_column(String(36), nullable=False, index=True)
    forecast_date: Mapped[str]  = mapped_column(String(10), nullable=False)   # YYYY-MM-DD
    predicted_revenue: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[float]  = mapped_column(Float, nullable=False)
    upper_bound: Mapped[float]  = mapped_column(Float, nullable=False)
    trend_note: Mapped[str | None]  = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime]  = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Feature: Anomaly Detection
# ---------------------------------------------------------------------------

class AIAnomalyAlert(Base):
    __tablename__ = "ai_anomaly_alerts"

    id: Mapped[str]                  = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]         = mapped_column(String(36), nullable=False, index=True)
    alert_type: Mapped[str]          = mapped_column(String(100), nullable=False)  # DATA_QUALITY | REVENUE_ANOMALY
    severity: Mapped[str]            = mapped_column(String(20), nullable=False)   # CRITICAL | WARNING
    tier: Mapped[str]                = mapped_column(String(20), nullable=False)   # RULE_BASED | LLM_PATTERN
    reference_date: Mapped[date]     = mapped_column(Date, nullable=False)
    description: Mapped[str]         = mapped_column(Text, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    record_type: Mapped[str | None]  = mapped_column(String(20), nullable=True)   # order | revenue | import | cost | None (LLM_PATTERN)
    is_acknowledged: Mapped[bool]    = mapped_column(Boolean, nullable=False, default=False)
    generated_at: Mapped[datetime]   = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Feature: Reorder Suggestion
# ---------------------------------------------------------------------------

class AIReorderSuggestion(Base):
    __tablename__ = "ai_reorder_suggestions"
    __table_args__ = (
        UniqueConstraint("location_id", "product_id", name="uq_reorder_location_product"),
    )

    id: Mapped[str]                 = mapped_column(String(36), primary_key=True)
    location_id: Mapped[str]        = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str]         = mapped_column(String(36), nullable=False)
    current_stock: Mapped[float]    = mapped_column(Float, nullable=False)
    days_until_stockout: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_daily_sales: Mapped[float]  = mapped_column(Float, nullable=False)
    urgency: Mapped[str]            = mapped_column(String(10), nullable=False)  # HIGH | MEDIUM | LOW
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
