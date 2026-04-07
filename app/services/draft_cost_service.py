"""
services/draft_cost_service.py

Orchestrates: STT → LLM extraction → DraftCostResult

Flow:
  1. audio_bytes → ml.stt.transcribe() → transcript (vi-VN text)
  2. transcript → ml.llm.chat() → structured JSON with cost fields
  3. Parse JSON → DraftCostResult
"""

import json
import logging

from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import LLMError, STTError
from app.ml import llm, stt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class CostItem(BaseModel):
    amount: float | None = None
    description: str | None = None
    cost_date: str | None = None       # YYYY-MM-DD; null = today (let client fill)
    cost_type: str | None = None       # "utilities" | "salary" | "rent" | "transport" | "marketing" | "maintenance" | "other"
    payment_method: str | None = None  # "cash" | "bank"


class DraftCostResult(BaseModel):
    items: list[CostItem]
    raw_transcript: str
    confidence: str  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Bạn là trợ lý ghi sổ chi phí cho hộ kinh doanh nhỏ ở Việt Nam.
Nhiệm vụ: từ câu nói của chủ shop, trích xuất TỪNG khoản chi phí thành mảng JSON.
Nếu câu nói đề cập nhiều khoản chi phí khác nhau, tạo nhiều phần tử trong mảng "items".

Quy tắc:
- Chỉ trả về JSON hợp lệ, không giải thích thêm.
- Nếu không xác định được thông tin, để null.
- "payment_method": "cash" nếu có từ "tiền mặt", "tiền tươi"; "bank" nếu có từ "chuyển khoản", "thẻ", "ví"; null nếu không rõ.
- "cost_date": định dạng YYYY-MM-DD nếu người dùng nói ngày cụ thể; null nếu không nói (ngầm hiểu là hôm nay).
- "amount": số tiền (đơn vị đồng). Hiểu "triệu" = 1.000.000, "nghìn" / "ngàn" = 1.000, "trăm" = 100.
- "cost_type": phân loại chi phí dựa trên nội dung, chỉ dùng đúng các giá trị sau:
    "utilities"   → điện, nước, internet, điện thoại
    "salary"      → lương, thưởng, công thợ, nhân công
    "rent"        → thuê nhà, thuê mặt bằng
    "transport"   → ship, giao hàng, vận chuyển
    "marketing"   → quảng cáo, marketing, khuyến mãi
    "maintenance" → sửa chữa, bảo trì, bảo dưỡng
    "materials"   → nguyên liệu, vật tư, hàng hóa mua vào
    "other"       → hoặc bất kỳ khoản nào không thuộc các loại trên
- "confidence": "high" nếu hầu hết items đều có đủ amount + description; "medium" nếu một số items thiếu thông tin; "low" nếu quá mơ hồ.

Output format:
{
  "items": [
    {
      "amount":         <số tiền hoặc null>,
      "description":    "<mô tả nội dung chi phí hoặc null>",
      "cost_date":      "<YYYY-MM-DD hoặc null>",
      "cost_type":      "<loại chi phí hoặc null>",
      "payment_method": "cash" | "bank" | null
    }
  ],
  "confidence": "high" | "medium" | "low"
}"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def process_draft_cost(
    audio_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> DraftCostResult:
    # Step 1: Speech-to-Text
    transcript = await stt.transcribe(audio_bytes, mime_type)
    if not transcript.strip():
        return DraftCostResult(items=[], raw_transcript="", confidence="low")

    # Step 2: LLM extraction
    user_prompt = (
        f"Câu nói của chủ shop: \"{transcript}\"\n\n"
        "Trích xuất tất cả các khoản chi phí theo format JSON đã quy định."
    )

    raw_json = await llm.chat(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=settings.llm_draft_order_temperature,
        max_tokens=512,
        response_format={"type": "json_object"},
    )

    # Step 3: Parse
    return _parse_llm_response(raw_json, transcript)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str, transcript: str) -> DraftCostResult:
    try:
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        raw_items: list[dict] = data.get("items", [])
        items = [
            CostItem(
                amount=item.get("amount"),
                description=item.get("description"),
                cost_date=item.get("cost_date"),
                cost_type=item.get("cost_type"),
                payment_method=item.get("payment_method"),
            )
            for item in raw_items
            if isinstance(item, dict)
        ]
        return DraftCostResult(
            items=items,
            raw_transcript=transcript,
            confidence=data.get("confidence", "low"),
        )
    except Exception as exc:
        logger.error("Failed to parse draft cost LLM response: %s", exc)
        return DraftCostResult(items=[], raw_transcript=transcript, confidence="low")
