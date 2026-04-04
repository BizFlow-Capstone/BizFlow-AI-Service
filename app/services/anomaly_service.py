"""
services/anomaly_service.py

Two-tier anomaly detection:

Tier 1 — Rule-based (realtime, called on every order/import save):
  • Evaluates hard business rules against a single record.
  • Runs in < 100 ms — no ML, no LLM, no network call.
  • Writes CRITICAL/WARNING alerts immediately to ai_anomaly_alerts.

Tier 2 — LLM pattern summary (nightly @ 02:00 AM):
  • GPT-4o-mini reviews 7-day aggregated data per location.
  • Identifies subtle pattern anomalies (quiet week, consistent drift).
  • Writes LLM_PATTERN alerts to ai_anomaly_alerts.
"""

import logging
import uuid
from typing import Literal

from pydantic import BaseModel

from app.db.mysql_client import execute_write, fetch_all
from app.ml import llm

logger = logging.getLogger(__name__)

MINIMUM_DAYS_TIER2 = 7


# ---------------------------------------------------------------------------
# Response schemas (shared with router)
# ---------------------------------------------------------------------------

class AlertDetail(BaseModel):
    alert_type: str
    severity: str
    description: str


class CheckRecordResult(BaseModel):
    alerts_created: int
    has_critical: bool
    alerts: list[AlertDetail]


class PatternCheckSummary(BaseModel):
    location_id: str
    alerts_created: int


# ---------------------------------------------------------------------------
# Tier 1: Rule-based checks
# ---------------------------------------------------------------------------

async def check_record_rules(
    location_id: str,
    record_type: Literal["order", "import"],
    record_id: str,
) -> CheckRecordResult:
    if record_type == "order":
        return await _check_order(location_id, record_id)
    return await _check_import(location_id, record_id)


async def _check_order(location_id: str, order_id: str) -> CheckRecordResult:
    rows = fetch_all(
        """
        SELECT si.unit_price, si.quantity, si.product_id,
               (SELECT AVG(si2.unit_price)
                FROM sale_items si2
                JOIN orders o2 ON si2.order_id = o2.id
                WHERE si2.product_id = si.product_id
                  AND o2.location_id = :location_id
                  AND o2.status = 'CONFIRMED'
                  AND o2.created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
               ) AS avg_price,
               o.is_debt, o.customer_id
        FROM sale_items si
        JOIN orders o ON si.order_id = o.id
        WHERE o.id = :order_id
        """,
        {"order_id": order_id, "location_id": location_id},
    )

    alerts: list[AlertDetail] = []
    for row in rows:
        unit_price = float(row["unit_price"] or 0)
        quantity   = float(row["quantity"] or 0)
        avg_price  = float(row["avg_price"] or 0) if row["avg_price"] else None
        is_debt    = bool(row["is_debt"])
        customer_id = row["customer_id"]

        if unit_price == 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description="Phát hiện đơn hàng có giá bán = 0đ. Vui lòng kiểm tra lại.",
            ))

        if quantity <= 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description="Số lượng sản phẩm phải lớn hơn 0.",
            ))

        if avg_price and avg_price > 0 and unit_price > 0:
            ratio = unit_price / avg_price
            if ratio < 0.3 or ratio > 3.0:
                alerts.append(AlertDetail(
                    alert_type="DATA_QUALITY",
                    severity="WARNING",
                    description=(
                        f"Giá bán ({unit_price:,.0f}đ) chênh lệch nhiều so với "
                        f"giá trung bình ({avg_price:,.0f}đ). Kiểm tra lại."
                    ),
                ))

        if is_debt and not customer_id:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="WARNING",
                description="Đơn hàng ghi nợ nhưng chưa chọn khách hàng.",
            ))

    _write_alerts(location_id, order_id, alerts, tier="RULE_BASED")
    has_critical = any(a.severity == "CRITICAL" for a in alerts)
    return CheckRecordResult(alerts_created=len(alerts), has_critical=has_critical, alerts=alerts)


async def _check_import(location_id: str, import_id: str) -> CheckRecordResult:
    rows = fetch_all(
        """
        SELECT pi.quantity, pi.unit_price AS cost_per_unit
        FROM product_imports pi
        WHERE pi.import_id = :import_id
        """,
        {"import_id": import_id},
    )

    alerts: list[AlertDetail] = []
    for row in rows:
        quantity     = float(row["quantity"] or 0)
        cost_per_unit = float(row["cost_per_unit"] or 0)

        if quantity <= 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description="Số lượng nhập hàng phải lớn hơn 0.",
            ))

        if cost_per_unit == 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="WARNING",
                description="Đơn giá nhập hàng = 0đ. Kiểm tra lại phiếu nhập.",
            ))

    _write_alerts(location_id, import_id, alerts, tier="RULE_BASED")
    has_critical = any(a.severity == "CRITICAL" for a in alerts)
    return CheckRecordResult(alerts_created=len(alerts), has_critical=has_critical, alerts=alerts)


# ---------------------------------------------------------------------------
# Tier 2: LLM nightly pattern summary
# ---------------------------------------------------------------------------

async def run_pattern_check(location_id: str) -> PatternCheckSummary | None:
    rows = fetch_all(
        """
        SELECT DATE(created_at) AS day,
               SUM(total_amount)       AS revenue,
               COUNT(*)                AS order_count,
               AVG(total_amount)       AS avg_order_value
        FROM orders
        WHERE location_id = :location_id
          AND status = 'CONFIRMED'
          AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day
        """,
        {"location_id": location_id},
    )

    if len(rows) < MINIMUM_DAYS_TIER2:
        logger.info("Tier-2 anomaly skipped for location %s: insufficient data.", location_id)
        return None

    csv_data = "ngay,doanh_thu,so_don,gia_trung_binh\n"
    for r in rows:
        csv_data += f"{r['day']},{r['revenue']:.0f},{r['order_count']},{r['avg_order_value']:.0f}\n"

    system = (
        "Bạn là trợ lý phân tích dữ liệu kinh doanh. "
        "Hãy xem xét dữ liệu 7 ngày qua và chỉ ra các điểm bất thường (nếu có). "
        "Trả lời ngắn gọn bằng tiếng Việt dành cho chủ hộ kinh doanh nhỏ. "
        "Nếu không có gì bất thường, hãy nói 'Dữ liệu 7 ngày qua bình thường.'."
    )
    user = f"Dữ liệu kinh doanh 7 ngày:\n{csv_data}\n\nCó điểm gì bất thường không?"

    description = await llm.chat(system_prompt=system, user_prompt=user, temperature=0.4, max_tokens=300)

    # Only persist if the LLM found something noteworthy
    if "bình thường" not in description.lower():
        alert = AlertDetail(
            alert_type="REVENUE_ANOMALY",
            severity="WARNING",
            description=description,
        )
        _write_alerts(location_id, None, [alert], tier="LLM_PATTERN")
        return PatternCheckSummary(location_id=location_id, alerts_created=1)

    return PatternCheckSummary(location_id=location_id, alerts_created=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_alerts(
    location_id: str,
    reference_id: str | None,
    alerts: list[AlertDetail],
    tier: Literal["RULE_BASED", "LLM_PATTERN"],
) -> None:
    for alert in alerts:
        execute_write(
            """
            INSERT INTO ai_anomaly_alerts
                (id, location_id, alert_type, severity, tier, reference_date,
                 description, reference_id, is_acknowledged, generated_at)
            VALUES
                (:id, :location_id, :alert_type, :severity, :tier, CURDATE(),
                 :description, :reference_id, FALSE, NOW())
            """,
            {
                "id":           str(uuid.uuid4()),
                "location_id":  location_id,
                "alert_type":   alert.alert_type,
                "severity":     alert.severity,
                "tier":         tier,
                "description":  alert.description,
                "reference_id": reference_id,
            },
        )
