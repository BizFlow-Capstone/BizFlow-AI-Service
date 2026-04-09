"""
services/forecast_service.py

Revenue forecasting using Pandas EMA + GPT-4o-mini Vietnamese explanation.

Flow (per location):
  1. SELECT daily revenue for last 3 months from MySQL
  2. Validate: ≥ 14 days of data required
  3. Pandas EMA (span=7) → 7 future forecast points + ±1σ confidence band
  4. GPT-4o-mini → 2–3 sentence Vietnamese trend note
  5. UPSERT results into ai_revenue_forecasts
"""

import logging
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.core.exceptions import InsufficientDataError
from app.db.mysql_client import fetch_all, execute_write
from app.ml import llm
from app.core.config import settings

logger = logging.getLogger(__name__)

MINIMUM_DAYS = 14
FORECAST_HORIZON = 7  # days ahead


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class ForecastSummary(BaseModel):
    location_id: str
    forecast_days: int
    trend_note: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def run_forecast(location_id: str) -> ForecastSummary | None:
    """
    Run the full forecasting pipeline for one location.
    Returns None if there is insufficient data (skipped gracefully).
    """
    if not location_id.isdigit():
        logger.warning("Invalid location_id=%s passed to run_forecast", location_id)
        return None

    # 1. Load data — đọc từ Revenues (gộp cả sale + manual, tránh double-count với Orders)
    # Revenues.BusinessLocationId trực tiếp, không cần join phức tạp
    rows = fetch_all(
        """
        SELECT RevenueDate AS ds, SUM(Amount) AS y
        FROM Revenues
        WHERE BusinessLocationId = :location_id
          AND DeletedAt IS NULL
          AND RevenueDate >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
        GROUP BY RevenueDate
        ORDER BY ds
        """,
        {"location_id": int(location_id)},
    )

    if len(rows) < MINIMUM_DAYS:
        logger.info(
            "Forecast skipped for location %s: %d days available, need %d.",
            location_id, len(rows), MINIMUM_DAYS,
        )
        _write_insufficient_flag(location_id)
        return None

    # 2. Build DataFrame, fill missing days with 0
    df = pd.DataFrame(rows)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = pd.to_numeric(df["y"], downcast="float")

    full_range = pd.date_range(df["ds"].min(), df["ds"].max(), freq="D")
    df = df.set_index("ds").reindex(full_range, fill_value=0).reset_index()
    df.rename(columns={"index": "ds"}, inplace=True)

    # 3. EMA forecast
    ema = df["y"].ewm(span=7, adjust=False).mean()
    residuals = df["y"] - ema
    sigma = float(residuals.iloc[-14:].std())

    last_date: date = df["ds"].iloc[-1].date()
    forecast_rows: list[dict] = []
    last_ema = float(ema.iloc[-1])

    for i in range(1, FORECAST_HORIZON + 1):
        forecast_date = last_date + timedelta(days=i)
        predicted = max(0.0, last_ema)
        forecast_rows.append({
            "id":                str(uuid.uuid4()),
            "location_id":       location_id,
            "forecast_date":     forecast_date.isoformat(),
            "predicted_revenue": round(predicted, 2),
            "lower_bound":       round(max(0.0, predicted - sigma), 2),
            "upper_bound":       round(predicted + sigma, 2),
        })

    # 4. GPT trend note (uses last 30 days as context)
    trend_note = await _generate_trend_note(df.tail(30))

    # 5. Persist
    _upsert_forecasts(forecast_rows, trend_note)

    return ForecastSummary(
        location_id=location_id,
        forecast_days=FORECAST_HORIZON,
        trend_note=trend_note,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _generate_trend_note(df_30: pd.DataFrame) -> str:
    # Enforce numeric types before building CSV to prevent prompt injection
    # via unexpected string values that could appear if column dtypes drift.
    safe = df_30[["ds", "y"]].copy()
    safe["ds"] = pd.to_datetime(safe["ds"]).dt.strftime("%Y-%m-%d")  # strict date format
    safe["y"]  = pd.to_numeric(safe["y"], errors="coerce").fillna(0).round(0).astype(int)
    csv_preview = safe.to_csv(index=False)
    system = (
        "Bạn là chuyên gia phân tích kinh doanh. "
        "Hãy viết 2–3 câu tiếng Việt đơn giản, dễ hiểu cho chủ hộ kinh doanh nhỏ "
        "về xu hướng doanh thu của họ. Đề cập đến ngày nổi bật nếu có."
    )
    user = f"Dữ liệu doanh thu 30 ngày qua:\n{csv_preview}\n\nHãy nhận xét xu hướng."
    return await llm.chat(system_prompt=system, user_prompt=user, temperature=settings.llm_forecast_temperature, max_tokens=settings.llm_forecast_max_tokens)


def _upsert_forecasts(rows: list[dict], trend_note: str) -> None:
    for row in rows:
        execute_write(
            """
            INSERT INTO ai_revenue_forecasts
                (id, location_id, forecast_date, predicted_revenue, lower_bound, upper_bound, trend_note, generated_at)
            VALUES
                (:id, :location_id, :forecast_date, :predicted_revenue, :lower_bound, :upper_bound, :trend_note, NOW())
            ON DUPLICATE KEY UPDATE
                predicted_revenue = VALUES(predicted_revenue),
                lower_bound       = VALUES(lower_bound),
                upper_bound       = VALUES(upper_bound),
                trend_note        = VALUES(trend_note),
                generated_at      = NOW()
            """,
            {**row, "trend_note": trend_note},
        )


def _write_insufficient_flag(location_id: str) -> None:
    """Store a sentinel row so the client can show 'not enough data' instead of an empty chart."""
    execute_write(
        """
        INSERT INTO ai_revenue_forecasts
            (id, location_id, forecast_date, predicted_revenue, lower_bound, upper_bound, trend_note, generated_at)
        VALUES
            (:id, :location_id, CURDATE(), 0, 0, 0, 'not_enough_data', NOW())
        ON DUPLICATE KEY UPDATE
            trend_note   = 'not_enough_data',
            generated_at = NOW()
        """,
        {"id": str(uuid.uuid4()), "location_id": location_id},
    )
