"""
services/product_insights_service.py

Computes three types of product performance insights using pure Pandas + SQL.
No ML model, no LLM — all results are derived from the location's own data.

Insight types:
  TOP_SELLER        — products ranked by revenue / units over 7 and 30 days
  GROWTH_TREND      — products whose 7-day velocity > 1.5× their 30-day average
  PROMOTE_CANDIDATE — high-margin products with above-average stock levels
"""

import logging
import uuid
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from app.db.mysql_client import execute_write, fetch_all

logger = logging.getLogger(__name__)

GROWTH_RATIO_THRESHOLD = 1.5   # 7d velocity must be ≥ 1.5× the 30d average
TOP_N = 10                      # max rows per insight type per period


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class InsightsSummary(BaseModel):
    location_id: str
    top_sellers_written: int
    growth_trends_written: int
    promote_candidates_written: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def run_product_insights(location_id: str) -> InsightsSummary | None:
    # 1. Load last 30 days of order line items
    sales_rows = fetch_all(
        """
        SELECT DATE(o.created_at)    AS sale_date,
               si.product_id,
               SUM(si.quantity)      AS qty_sold,
               SUM(si.quantity * si.unit_price) AS revenue
        FROM sale_items si
        JOIN orders o ON si.order_id = o.id
        WHERE o.location_id = :location_id
          AND o.status = 'CONFIRMED'
          AND o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY DATE(o.created_at), si.product_id
        """,
        {"location_id": location_id},
    )

    if not sales_rows:
        logger.info("Product insights skipped for location %s: no sales data.", location_id)
        return None

    df = pd.DataFrame(sales_rows)
    df["qty_sold"]  = pd.to_numeric(df["qty_sold"],  downcast="float")
    df["revenue"]   = pd.to_numeric(df["revenue"],   downcast="float")
    df["sale_date"] = pd.to_datetime(df["sale_date"])

    cutoff_7d  = df["sale_date"].max() - pd.Timedelta(days=7)
    df_7d  = df[df["sale_date"] > cutoff_7d]
    df_30d = df

    # 2. Top sellers (7-day)
    top_7  = _top_sellers(df_7d,  period_days=7)
    # Top sellers (30-day)
    top_30 = _top_sellers(df_30d, period_days=30)

    # 3. Growth trends
    trends = _growth_trends(df_7d, df_30d)

    # 4. Promote candidates
    product_rows = fetch_all(
        """
        SELECT id AS product_id,
               stock_quantity,
               (selling_price - cost_price) / NULLIF(selling_price, 0) AS margin_ratio
        FROM products
        WHERE location_id = :location_id
          AND status = 'ACTIVE'
          AND selling_price > 0
        """,
        {"location_id": location_id},
    )
    promote = _promote_candidates(product_rows)

    # 5. Persist
    all_rows = top_7 + top_30 + trends + promote
    _upsert_insights(location_id, all_rows)

    return InsightsSummary(
        location_id=location_id,
        top_sellers_written=len(top_7) + len(top_30),
        growth_trends_written=len(trends),
        promote_candidates_written=len(promote),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _top_sellers(df: pd.DataFrame, period_days: int) -> list[dict]:
    if df.empty:
        return []
    agg = (
        df.groupby("product_id", observed=True)
        .agg(total_revenue=("revenue", "sum"), total_qty=("qty_sold", "sum"))
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .head(TOP_N)
    )
    result = []
    for rank, (_, row) in enumerate(agg.iterrows(), start=1):
        result.append({
            "product_id":   row["product_id"],
            "insight_type": "TOP_SELLER",
            "rank":         rank,
            "metric_value": round(float(row["total_revenue"]), 4),
            "period_days":  period_days,
        })
    return result


def _growth_trends(df_7d: pd.DataFrame, df_30d: pd.DataFrame) -> list[dict]:
    if df_7d.empty or df_30d.empty:
        return []

    vel_7  = df_7d.groupby("product_id",  observed=True)["qty_sold"].sum() / 7
    vel_30 = df_30d.groupby("product_id", observed=True)["qty_sold"].sum() / 30

    ratios = (vel_7 / vel_30.replace(0, float("nan"))).dropna()
    trending = ratios[ratios >= GROWTH_RATIO_THRESHOLD].sort_values(ascending=False).head(TOP_N)

    result = []
    for rank, (product_id, ratio) in enumerate(trending.items(), start=1):
        result.append({
            "product_id":   product_id,
            "insight_type": "GROWTH_TREND",
            "rank":         rank,
            "metric_value": round(float(ratio), 4),
            "period_days":  7,
        })
    return result


def _promote_candidates(product_rows: list[dict]) -> list[dict]:
    if not product_rows:
        return []

    df = pd.DataFrame(product_rows)
    df["stock_quantity"] = pd.to_numeric(df["stock_quantity"], downcast="float")
    df["margin_ratio"]   = pd.to_numeric(df["margin_ratio"],   downcast="float")
    df = df.dropna(subset=["margin_ratio"])

    avg_stock  = df["stock_quantity"].mean()
    avg_margin = df["margin_ratio"].mean()

    candidates = (
        df[(df["margin_ratio"] >= avg_margin) & (df["stock_quantity"] >= avg_stock)]
        .sort_values("margin_ratio", ascending=False)
        .head(TOP_N)
    )

    result = []
    for rank, (_, row) in enumerate(candidates.iterrows(), start=1):
        result.append({
            "product_id":   row["product_id"],
            "insight_type": "PROMOTE_CANDIDATE",
            "rank":         rank,
            "metric_value": round(float(row["margin_ratio"]), 4),
            "period_days":  30,
        })
    return result


def _upsert_insights(location_id: str, rows: list[dict]) -> None:
    # Clear previous insights for this location before writing new ones
    execute_write(
        "DELETE FROM ai_product_insights WHERE location_id = :location_id",
        {"location_id": location_id},
    )
    for row in rows:
        execute_write(
            """
            INSERT INTO ai_product_insights
                (id, location_id, product_id, insight_type, rank, metric_value, period_days, generated_at)
            VALUES
                (:id, :location_id, :product_id, :insight_type, :rank, :metric_value, :period_days, NOW())
            """,
            {"id": str(uuid.uuid4()), "location_id": location_id, **row},
        )
