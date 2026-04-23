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
from app.core.config import settings
from app.core.constants import OrderStatus

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
    record_type: Literal["order", "import", "revenue"],
    record_id: str,
) -> CheckRecordResult:
    if record_type == "order":
        return await _check_order(location_id, record_id)
    if record_type == "revenue":
        return await _check_revenue(location_id, record_id)
    return await _check_import(location_id, record_id)


async def _check_order(location_id: str, order_id: str) -> CheckRecordResult:
    if not order_id.isdigit() or not location_id.isdigit():
        logger.warning("Invalid order_id=%s or location_id=%s passed to _check_order", order_id, location_id)
        return CheckRecordResult(alerts_created=0, has_critical=False, alerts=[])
    rows = fetch_all(
        """
        SELECT od.UnitPrice AS unit_price,
               od.Quantity  AS quantity,
               si.ProductId AS product_id,
               (SELECT AVG(od2.UnitPrice)
                FROM OrderDetails od2
                JOIN Orders    o2  ON od2.OrderId   = o2.OrderId
                JOIN SaleItems si2 ON od2.SaleItemId = si2.SaleItemId
                JOIN Products  p2  ON si2.ProductId  = p2.ProductId
                WHERE si2.ProductId = si.ProductId
                  AND p2.BusinessLocationId = :location_id
                  AND o2.Status  = :order_status
                  AND o2.CreatedAt >= DATE_SUB(NOW(), INTERVAL 90 DAY)
               ) AS avg_price
        FROM OrderDetails od
        JOIN Orders    o  ON od.OrderId   = o.OrderId
        JOIN SaleItems si ON od.SaleItemId = si.SaleItemId
        WHERE o.OrderId = :order_id
        """,
        {"order_id": int(order_id), "location_id": int(location_id), "order_status": OrderStatus.COMPLETED},
    )

    alerts: list[AlertDetail] = []
    for row in rows:
        unit_price = float(row["unit_price"] or 0)
        quantity   = float(row["quantity"] or 0)
        avg_price  = float(row["avg_price"] or 0) if row["avg_price"] else None

        prefix = f"Đơn hàng #{order_id}: "

        if unit_price == 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description=f"{prefix}Phát hiện giá bán = 0đ. Vui lòng kiểm tra lại.",
            ))

        if quantity <= 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description=f"{prefix}Số lượng sản phẩm phải lớn hơn 0.",
            ))

        if avg_price and avg_price > 0 and unit_price > 0:
            ratio = unit_price / avg_price
            if ratio < 0.3 or ratio > 3.0:
                alerts.append(AlertDetail(
                    alert_type="DATA_QUALITY",
                    severity="WARNING",
                    description=(
                        f"{prefix}Giá bán ({unit_price:,.0f}đ) chênh lệch nhiều so với "
                        f"giá trung bình ({avg_price:,.0f}đ). Kiểm tra lại."
                    ),
                ))


    _write_alerts(location_id, order_id, alerts, tier="RULE_BASED")
    has_critical = any(a.severity == "CRITICAL" for a in alerts)
    return CheckRecordResult(alerts_created=len(alerts), has_critical=has_critical, alerts=alerts)


async def _check_revenue(location_id: str, revenue_id: str) -> CheckRecordResult:
    if not revenue_id.isdigit() or not location_id.isdigit():
        logger.warning("Invalid revenue_id=%s or location_id=%s passed to _check_revenue", revenue_id, location_id)
        return CheckRecordResult(alerts_created=0, has_critical=False, alerts=[])
    rows = fetch_all(
        """
        SELECT r.Amount AS amount,
               (SELECT AVG(r2.Amount)
                FROM Revenues r2
                WHERE r2.BusinessLocationId = :location_id
                  AND r2.DeletedAt IS NULL
                  AND r2.RevenueDate >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                  AND r2.RevenueId != :revenue_id
               ) AS avg_amount
        FROM Revenues r
        WHERE r.RevenueId = :revenue_id
          AND r.DeletedAt IS NULL
        """,
        {"revenue_id": int(revenue_id), "location_id": int(location_id)},
    )

    if not rows:
        return CheckRecordResult(alerts_created=0, has_critical=False, alerts=[])

    alerts: list[AlertDetail] = []
    row = rows[0]
    amount = float(row["amount"] or 0)
    avg_amount = float(row["avg_amount"]) if row["avg_amount"] else None

    prefix = f"Doanh thu #{revenue_id}: "

    if amount == 0:
        alerts.append(AlertDetail(
            alert_type="DATA_QUALITY",
            severity="CRITICAL",
            description=f"{prefix}Số tiền = 0đ. Vui lòng kiểm tra lại.",
        ))

    if avg_amount and avg_amount > 0 and amount > 0:
        ratio = amount / avg_amount
        if ratio > 100.0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description=(
                    f"{prefix}Số tiền ({amount:,.0f}đ) cao bất thường gấp {ratio:.0f} lần "
                    f"mức trung bình 90 ngày ({avg_amount:,.0f}đ). Có thể là lỗi nhập liệu."
                ),
            ))
        elif ratio > 10.0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="WARNING",
                description=(
                    f"{prefix}Số tiền ({amount:,.0f}đ) cao bất thường so với "
                    f"mức trung bình 90 ngày ({avg_amount:,.0f}đ). Kiểm tra lại."
                ),
            ))

    _write_alerts(location_id, revenue_id, alerts, tier="RULE_BASED")
    has_critical = any(a.severity == "CRITICAL" for a in alerts)
    return CheckRecordResult(alerts_created=len(alerts), has_critical=has_critical, alerts=alerts)


async def _check_import(location_id: str, import_id: str) -> CheckRecordResult:
    if not import_id.isdigit() or not location_id.isdigit():
        logger.warning("Invalid import_id=%s or location_id=%s passed to _check_import", import_id, location_id)
        return CheckRecordResult(alerts_created=0, has_critical=False, alerts=[])
    rows = fetch_all(
        """
        SELECT pi.Quantity  AS quantity,
               pi.CostPrice AS cost_per_unit
        FROM ProductImports pi
        WHERE pi.ImportId = :import_id
        """,
        {"import_id": int(import_id)},
    )

    alerts: list[AlertDetail] = []
    for row in rows:
        quantity      = float(row["quantity"] or 0)
        cost_per_unit = float(row["cost_per_unit"] or 0)

        prefix = f"Phiếu nhập #{import_id}: "

        if quantity <= 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="CRITICAL",
                description=f"{prefix}Số lượng nhập hàng phải lớn hơn 0.",
            ))

        if cost_per_unit == 0:
            alerts.append(AlertDetail(
                alert_type="DATA_QUALITY",
                severity="WARNING",
                description=f"{prefix}Đơn giá nhập hàng = 0đ. Kiểm tra lại phiếu nhập.",
            ))

    _write_alerts(location_id, import_id, alerts, tier="RULE_BASED")
    has_critical = any(a.severity == "CRITICAL" for a in alerts)
    return CheckRecordResult(alerts_created=len(alerts), has_critical=has_critical, alerts=alerts)


# ---------------------------------------------------------------------------
# Tier 2: LLM nightly pattern summary
# ---------------------------------------------------------------------------

async def run_pattern_check(location_id: str) -> PatternCheckSummary | None:
    total_alerts = 0

    # --- Tier 2a: Rule-based revenue spike detection (nightly sweep on today's revenues) ---
    spike_rows = fetch_all(
        """
        SELECT r.RevenueId AS revenue_id,
               r.Amount    AS amount,
               (SELECT AVG(r2.Amount)
                FROM Revenues r2
                WHERE r2.BusinessLocationId = :location_id
                  AND r2.DeletedAt IS NULL
                  AND r2.RevenueDate >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                  AND r2.RevenueId != r.RevenueId
               ) AS avg_90d
        FROM Revenues r
        WHERE r.BusinessLocationId = :location_id
          AND r.DeletedAt IS NULL
          AND r.RevenueDate = CURDATE()
        """,
        {"location_id": int(location_id)},
    )
    for row in spike_rows:
        amount = float(row["amount"] or 0)
        avg_90d = float(row["avg_90d"]) if row["avg_90d"] else None
        if avg_90d and avg_90d > 0 and amount > 0:
            ratio = amount / avg_90d
            if ratio > 100.0:
                severity = "CRITICAL"
                desc = (
                    f"Doanh thu #{row['revenue_id']}: Số tiền ({amount:,.0f}đ) cao bất thường gấp {ratio:.0f} lần "
                    f"mức trung bình 90 ngày ({avg_90d:,.0f}đ). Có thể là lỗi nhập liệu."
                )
            elif ratio > 10.0:
                severity = "WARNING"
                desc = (
                    f"Doanh thu #{row['revenue_id']}: Số tiền ({amount:,.0f}đ) cao bất thường so với "
                    f"mức trung bình 90 ngày ({avg_90d:,.0f}đ). Kiểm tra lại."
                )
            else:
                continue
            _write_alerts(
                location_id,
                str(row["revenue_id"]),
                [AlertDetail(alert_type="REVENUE_SPIKE", severity=severity, description=desc)],
                tier="RULE_BASED",
            )
            total_alerts += 1

    # --- Tier 2b: LLM order pattern summary ---
    rows = fetch_all(
        """
        SELECT DATE(o.CreatedAt)     AS day,
               SUM(o.TotalAmount)   AS revenue,
               COUNT(*)             AS order_count,
               AVG(o.TotalAmount)   AS avg_order_value
        FROM Orders o
        WHERE o.Status = :order_status
          AND o.CreatedAt >= DATE_SUB(NOW(), INTERVAL 7 DAY)
          AND EXISTS (
              SELECT 1 FROM OrderDetails od
              JOIN SaleItems si ON si.SaleItemId = od.SaleItemId
              JOIN Products  p  ON p.ProductId   = si.ProductId
              WHERE od.OrderId = o.OrderId
                AND p.BusinessLocationId = :location_id
          )
        GROUP BY DATE(o.CreatedAt)
        ORDER BY day
        """,
        {"location_id": int(location_id), "order_status": OrderStatus.COMPLETED},
    )

    if len(rows) < MINIMUM_DAYS_TIER2:
        logger.info("Tier-2 anomaly skipped for location %s: insufficient order data for LLM.", location_id)
        return PatternCheckSummary(location_id=location_id, alerts_created=total_alerts)

    # Only numeric/date fields are included — no free-text columns that could carry prompt injection.
    csv_data = "ngay,doanh_thu,so_don,gia_trung_binh\n"
    for r in rows:
        csv_data += (
            f"{str(r['day'])[:10]},"          # date truncated to YYYY-MM-DD, no extra chars
            f"{float(r['revenue']):.0f},"
            f"{int(r['order_count'])},"
            f"{float(r['avg_order_value']):.0f}\n"
        )

    system = (
        "Bạn là trợ lý phân tích dữ liệu kinh doanh. "
        "Hãy xem xét dữ liệu 7 ngày qua và chỉ ra các điểm bất thường (nếu có). "
        "Trả lời ngắn gọn bằng tiếng Việt dành cho chủ hộ kinh doanh nhỏ. "
        "Nếu không có gì bất thường, hãy nói 'Dữ liệu 7 ngày qua bình thường.'."
    )
    user = f"Dữ liệu kinh doanh 7 ngày:\n{csv_data}\n\nCó điểm gì bất thường không?"

    description = await llm.chat(system_prompt=system, user_prompt=user, temperature=settings.llm_anomaly_temperature, max_tokens=settings.llm_anomaly_max_tokens)

    # Only persist if the LLM found something noteworthy
    if "bình thường" not in description.lower():
        # Remove today's LLM_PATTERN alerts before writing to avoid duplicates on re-runs
        execute_write(
            """
            DELETE FROM ai_anomaly_alerts
            WHERE location_id = :location_id
              AND tier = 'LLM_PATTERN'
              AND DATE(generated_at) = CURDATE()
            """,
            {"location_id": location_id},
        )
        alert = AlertDetail(
            alert_type="REVENUE_ANOMALY",
            severity="WARNING",
            description=description,
        )
        _write_alerts(location_id, None, [alert], tier="LLM_PATTERN")
        total_alerts += 1

    return PatternCheckSummary(location_id=location_id, alerts_created=total_alerts)


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
