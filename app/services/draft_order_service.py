"""
services/draft_order_service.py

Orchestrates: STT → RAG product matching → LLM extraction → DraftOrderResult

Flow:
  1. audio_bytes → ml.stt.transcribe() → transcript (vi-VN text)
  2. transcript → ml.vector_store.query_products() → top-3 matching products from catalog
  3. (transcript + product context) → ml.llm.chat() → structured JSON order
  4. Parse JSON → DraftOrderResult
"""

import json
import logging
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import LLMError, STTError
from app.ml import llm, stt, vector_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class DraftOrderItem(BaseModel):
    product_id: str | None = None
    product_name: str
    quantity: float
    unit: str
    customer_name: str | None = None
    is_debt: bool = False


class DraftOrderResult(BaseModel):
    items: list[DraftOrderItem]
    raw_transcript: str
    confidence: str  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Bạn là trợ lý nhận đơn hàng cho hộ kinh doanh nhỏ ở Việt Nam.
Nhiệm vụ: từ câu nói của chủ shop, trích xuất thông tin đơn hàng thành JSON.

Quy tắc:
- Chỉ trả về JSON hợp lệ, không giải thích thêm.
- Nếu không xác định được thông tin, để null.
- "is_debt" là true nếu có từ "nợ", "ghi sổ", "chịu", "thiếu tiền".
- "product_id" chỉ điền nếu tìm được sản phẩm khớp trong danh sách catalog.

Output format:
{
  "items": [
    {
      "product_id": "<id hoặc null>",
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
    # Search for all noun phrases in transcript; query once with full transcript
    matched_products = await vector_store.query_products(
        location_id=location_id,
        query_text=transcript,
        top_k=5,
    )

    # Step 3: LLM extraction
    catalog_context = _format_catalog(matched_products)
    user_prompt = (
        f"Danh sách sản phẩm trong kho:\n{catalog_context}\n\n"
        f"Câu đặt hàng: \"{transcript}\"\n\n"
        "Trích xuất đơn hàng theo format JSON đã quy định."
    )

    raw_json = await llm.chat(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    # Step 4: Parse result
    items, confidence = _parse_llm_response(raw_json, matched_products)

    return DraftOrderResult(
        items=items,
        raw_transcript=transcript,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_catalog(products: list[dict[str, Any]]) -> str:
    if not products:
        return "(Không tìm thấy sản phẩm nào phù hợp trong kho)"
    lines = [
        f"- ID: {p['product_id']}, Tên: {p['name']}, Đơn vị: {p.get('unit', '')}"
        for p in products
    ]
    return "\n".join(lines)


def _parse_llm_response(
    raw_json: str,
    matched_products: list[dict[str, Any]],
) -> tuple[list[DraftOrderItem], str]:
    try:
        data = json.loads(raw_json)
        items: list[DraftOrderItem] = []
        for item_data in data.get("items", []):
            items.append(DraftOrderItem(**item_data))

        # Confidence heuristic: all items have a matched product_id → high
        has_all_ids = all(item.product_id for item in items) and len(items) > 0
        confidence = "high" if (has_all_ids and matched_products) else ("medium" if items else "low")
        return items, confidence

    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Failed to parse LLM draft order response: %s — raw: %s", exc, raw_json[:300])
        return [], "low"
