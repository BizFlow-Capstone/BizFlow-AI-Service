"""
services/draft_order_service.py

Orchestrates: STT → RAG product matching → LLM extraction → DraftOrderResult

Flow:
  1. audio_bytes → ml.stt.transcribe() → transcript (vi-VN text)
  2. transcript → ml.vector_store.query_products() → top-3 matching products from catalog
  3. DB enrich: fetch SaleItems + active default prices for each matched product
  4. (transcript + enriched catalog) → ml.llm.chat() → structured JSON order with sale_item_id
  5. Parse JSON → resolve unit_price from DB → compute line_total → DraftOrderResult
"""

import json
import logging
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import LLMError, STTError
from app.core.config import settings
from app.db.mysql_client import fetch_all
from app.ml import llm, stt, vector_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class DraftOrderItem(BaseModel):
    product_id: str | None = None
    sale_item_id: str | None = None
    product_name: str
    matched: bool = False
    quantity: float
    unit: str
    unit_price: float | None = None
    line_total: float | None = None
    customer_name: str | None = None
    is_debt: bool = False


class DraftOrderResult(BaseModel):
    items: list[DraftOrderItem]
    raw_transcript: str
    confidence: str  # "high" | "medium" | "low"
    total_amount: float | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Bạn là trợ lý nhận đơn hàng cho hộ kinh doanh nhỏ ở Việt Nam.
Nhiệm vụ: từ câu nói hoặc đoạn hội thoại giữa chủ shop và khách hàng, trích xuất các mặt hàng đã CHỐT mua thành JSON.

Quy tắc xử lý hội thoại:
- Chỉ lấy các mặt hàng đã được XÁC NHẬN mua, bỏ qua câu hỏi thăm dò giá, hỏi còn hàng không, hoặc món bị hủy/từ chối.
- Nếu cùng 1 sản phẩm được đề cập nhiều lần với số lượng khác nhau, lấy số lượng CUỐI CÙNG được chốt.
- Bỏ qua các câu như "giá bao nhiêu?", "có không?", "loại nào?", "thôi khỏi", "không cần".
- "is_debt" là true nếu có từ "nợ", "ghi sổ", "chịu", "thiếu tiền".
- "customer_name" lấy từ tên khách được nhắc đến trong hội thoại (nếu có).
- "product_id" và "sale_item_id" chỉ điền nếu tìm được sản phẩm + đơn vị bán khớp trong danh sách catalog.
- Chọn "sale_item_id" dựa trên đơn vị tính ("unit") mà khách hoặc chủ shop xác nhận.
- Nếu không xác định được thông tin, để null.
- Chỉ trả về JSON hợp lệ, không giải thích thêm.

Output format:
{
  "items": [
    {
      "product_id": "<id hoặc null>",
      "sale_item_id": "<sale_item_id khớp đơn vị hoặc null>",
      "product_name": "<tên sản phẩm>",
      "quantity": <số lượng>,
      "unit": "<đơn vị>",
      "customer_name": "<tên khách hoặc null>",
      "is_debt": <true/false>
    }
  ]
}"""


async def process_draft_order(
    audio_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> DraftOrderResult:
    # Step 1: Speech-to-Text
    transcript = await stt.transcribe(audio_bytes, mime_type)
    if not transcript.strip():
        return DraftOrderResult(items=[], raw_transcript="", confidence="low")

    # Step 2: RAG — find matching products in catalog
    matched_products = await vector_store.query_products(
        location_id=location_id,
        query_text=transcript,
        top_k=5,
    )

    # Step 3: DB enrich — fetch SaleItems + active prices for each matched product
    product_ids = [p["product_id"] for p in matched_products if p.get("product_id")]
    sale_items_map = _fetch_sale_items_with_price(product_ids)

    # Step 4: LLM extraction with enriched catalog
    catalog_context = _format_catalog(matched_products, sale_items_map)
    user_prompt = (
        f"Danh sách sản phẩm trong kho:\n{catalog_context}\n\n"
        f"Nội dung hội thoại/câu đặt hàng:\n\"\"\"\n{transcript}\n\"\"\"\n\n"
        "Trích xuất các mặt hàng đã chốt mua theo format JSON đã quy định."
    )

    raw_json = await llm.chat(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=settings.llm_draft_order_temperature,
        max_tokens=settings.llm_draft_order_max_tokens,
        response_format={"type": "json_object"},
    )

    # Step 5: Parse result, resolve price, compute totals
    items, confidence = _parse_llm_response(raw_json, matched_products, sale_items_map)
    total_amount = sum(i.line_total for i in items if i.line_total is not None) or None

    return DraftOrderResult(
        items=items,
        raw_transcript=transcript,
        confidence=confidence,
        total_amount=total_amount,
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _fetch_sale_items_with_price(product_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """
    For each product_id, return its SaleItems with the active default price.
    Returns: {product_id: [{"sale_item_id": str, "unit": str, "price": float|None}, ...]}
    """
    if not product_ids:
        return {}

    placeholders = ", ".join(f":pid{i}" for i in range(len(product_ids)))
    params: dict[str, Any] = {f"pid{i}": pid for i, pid in enumerate(product_ids)}

    rows = fetch_all(
        f"""
        SELECT
            si.SaleItemId,
            si.ProductId,
            si.Unit,
            pp.Price
        FROM SaleItems si
        LEFT JOIN ProductPricePolicies pp
               ON pp.SaleItemId = si.SaleItemId
              AND pp.IsDefault = 1
              AND (pp.EndAt IS NULL OR pp.EndAt > CURDATE())
        WHERE si.ProductId IN ({placeholders})
          AND si.DeletedAt IS NULL
        ORDER BY si.ProductId, si.SaleItemId
        """,
        params,
    )

    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        pid = str(row["ProductId"])
        result.setdefault(pid, []).append({
            "sale_item_id": str(row["SaleItemId"]),
            "unit":         row["Unit"] or "",
            "price":        float(row["Price"]) if row["Price"] is not None else None,
        })
    return result


def _get_price_by_sale_item_id(
    sale_item_id: str,
    sale_items_map: dict[str, list[dict[str, Any]]],
) -> float | None:
    """Look up price for a given sale_item_id from the already-fetched map."""
    for items in sale_items_map.values():
        for si in items:
            if si["sale_item_id"] == sale_item_id:
                return si["price"]
    return None


# ---------------------------------------------------------------------------
# Formatting / parsing helpers
# ---------------------------------------------------------------------------

def _format_catalog(
    products: list[dict[str, Any]],
    sale_items_map: dict[str, list[dict[str, Any]]],
) -> str:
    if not products:
        return "(Không tìm thấy sản phẩm nào phù hợp trong kho)"

    lines: list[str] = []
    for p in products:
        pid = p["product_id"]
        sale_items = sale_items_map.get(pid, [])
        if sale_items:
            units_str = ", ".join(
                f"[sale_item_id={si['sale_item_id']}, unit={si['unit']}"
                + (f", price={si['price']:,.0f}đ" if si["price"] is not None else "")
                + "]"
                for si in sale_items
            )
            lines.append(f"- product_id={pid}, Tên: {p['name']}, Đơn vị bán: {units_str}")
        else:
            lines.append(
                f"- product_id={pid}, Tên: {p['name']}, Đơn vị: {p.get('unit', '')}"
            )
    return "\n".join(lines)


def _parse_llm_response(
    raw_json: str,
    matched_products: list[dict[str, Any]],
    sale_items_map: dict[str, list[dict[str, Any]]],
) -> tuple[list[DraftOrderItem], str]:
    try:
        data = json.loads(raw_json)
        items: list[DraftOrderItem] = []
        for item_data in data.get("items", []):
            # LLM may return numeric IDs — Pydantic v2 requires str, coerce explicitly
            for key in ("product_id", "sale_item_id"):
                if item_data.get(key) is not None:
                    item_data[key] = str(item_data[key])
            item = DraftOrderItem(**item_data)
            item.matched = item.product_id is not None

            # Resolve unit_price from the already-fetched map (no extra DB round-trip)
            if item.sale_item_id:
                item.unit_price = _get_price_by_sale_item_id(item.sale_item_id, sale_items_map)

            if item.unit_price is not None:
                item.line_total = round(item.quantity * item.unit_price, 2)

            items.append(item)

        has_all_ids = all(item.product_id for item in items) and len(items) > 0
        confidence = "high" if (has_all_ids and matched_products) else ("medium" if items else "low")
        return items, confidence

    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Failed to parse LLM draft order response: %s — raw: %s", exc, raw_json[:300])
        return [], "low"
