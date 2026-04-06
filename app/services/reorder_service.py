"""
services/reorder_service.py

Calculates reorder suggestions for all products at a location using:
  - Pandas rolling 14-day sales velocity (avg daily units sold)
  - Statistical reorder-point formula with safety stock
  - Current stock level from MySQL

Formula:
  Reorder Point  = avg_daily_sales × lead_time + safety_stock
  Safety Stock   = Z × σ_daily_sales × √lead_time   (Z=1.65, 95% service level)
  Suggested Qty  = max_stock_level − current_stock
  Max Stock Level = avg_daily_sales × 30  (30-day supply)

Urgency thresholds:
  HIGH   : days_until_stockout < 3
  MEDIUM : 3 ≤ days_until_stockout ≤ 7
  LOW    : days_until_stockout > 7
"""

import logging
import math
import uuid
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from app.db.mysql_client import execute_write, fetch_all
from app.core.constants import OrderStatus

logger = logging.getLogger(__name__)

MINIMUM_DAYS    = 14
LEAD_TIME_DAYS  = 3
Z_SCORE         = 1.65   # 95% service level
MAX_STOCK_DAYS  = 30


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class ReorderSummary(BaseModel):
    location_id: str
    suggestions_written: int
    high_urgency_count: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def run_reorder(location_id: str) -> ReorderSummary | None:
    # 1. Load sales history (last 30 days, product-level)
    sales_rows = fetch_all(
        """
        SELECT DATE(o.created_at) AS sale_date,
               si.product_id,
               SUM(si.quantity) AS qty_sold
        FROM sale_items si
        JOIN orders o ON si.order_id = o.id
        WHERE o.location_id = :location_id
          AND o.status = :order_status
          AND o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY DATE(o.created_at), si.product_id
        """,
        {"location_id": location_id, "order_status": OrderStatus.COMPLETED},
    )

    if not sales_rows:
        return None

    df = pd.DataFrame(sales_rows)
    df["qty_sold"] = pd.to_numeric(df["qty_sold"], downcast="float")

    unique_products = df["product_id"].unique().tolist()
    availability_check = df.groupby("product_id")["sale_date"].nunique()
    eligible = availability_check[availability_check >= MINIMUM_DAYS].index.tolist()

    if not eligible:
        logger.info("Reorder skipped for location %s: no product has %d+ days.", location_id, MINIMUM_DAYS)
        return None

    # 2. Load current stock
    stock_rows = fetch_all(
        """
        SELECT id AS product_id, stock_quantity
        FROM products
        WHERE location_id = :location_id
          AND status = 'ACTIVE'
        """,
        {"location_id": location_id},
    )
    stock_map = {r["product_id"]: float(r["stock_quantity"] or 0) for r in stock_rows}

    # 3. Calculate per product
    suggestions: list[dict] = []
    for product_id in eligible:
        product_df = df[df["product_id"] == product_id].copy()

        # Build full date range, fill missing days with 0
        date_range = pd.date_range(
            pd.to_datetime(product_df["sale_date"]).min(),
            periods=30,
            freq="D",
        )
        daily = (
            product_df
            .set_index(pd.to_datetime(product_df["sale_date"]))["qty_sold"]
            .reindex(date_range, fill_value=0.0)
        )

        avg_daily = float(daily.rolling(14).mean().iloc[-1])
        sigma_daily = float(daily.rolling(14).std().iloc[-1])

        if avg_daily <= 0:
            continue

        safety_stock  = Z_SCORE * sigma_daily * math.sqrt(LEAD_TIME_DAYS)
        reorder_point = avg_daily * LEAD_TIME_DAYS + safety_stock
        max_stock     = avg_daily * MAX_STOCK_DAYS
        current_stock = stock_map.get(product_id, 0.0)

        if current_stock > reorder_point:
            continue  # no need to reorder yet

        days_until_stockout = int(current_stock / avg_daily) if avg_daily > 0 else 999
        suggested_qty = max(0.0, max_stock - current_stock)
        urgency = _urgency(days_until_stockout)

        suggestions.append({
            "id":                  str(uuid.uuid4()),
            "location_id":         location_id,
            "product_id":          product_id,
            "current_stock":       round(current_stock, 3),
            "days_until_stockout": days_until_stockout,
            "suggested_quantity":  round(suggested_qty, 3),
            "avg_daily_sales":     round(avg_daily, 3),
            "urgency":             urgency,
        })

    # 4. Persist
    for row in suggestions:
        execute_write(
            """
            INSERT INTO ai_reorder_suggestions
                (id, location_id, product_id, current_stock, days_until_stockout,
                 suggested_quantity, avg_daily_sales, urgency, generated_at)
            VALUES
                (:id, :location_id, :product_id, :current_stock, :days_until_stockout,
                 :suggested_quantity, :avg_daily_sales, :urgency, NOW())
            ON DUPLICATE KEY UPDATE
                current_stock       = VALUES(current_stock),
                days_until_stockout = VALUES(days_until_stockout),
                suggested_quantity  = VALUES(suggested_quantity),
                avg_daily_sales     = VALUES(avg_daily_sales),
                urgency             = VALUES(urgency),
                generated_at        = NOW()
            """,
            row,
        )

    high_count = sum(1 for s in suggestions if s["urgency"] == "HIGH")
    return ReorderSummary(
        location_id=location_id,
        suggestions_written=len(suggestions),
        high_urgency_count=high_count,
    )


def _urgency(days: int) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if days < 3:
        return "HIGH"
    if days <= 7:
        return "MEDIUM"
    return "LOW"
