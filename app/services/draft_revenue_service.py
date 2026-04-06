"""
services/draft_revenue_service.py

Orchestrates: STT → LLM extraction → DraftRevenueResult

Flow:
  1. audio_bytes → ml.stt.transcribe() → transcript (vi-VN text)
  2. transcript → ml.llm.chat() → structured JSON with revenue items
  3. Parse JSON → DraftRevenueResult

Mỗi kênh thanh toán (cash / bank) là một item riêng biệt trong danh sách,
để user có thể lưu thành nhiều dòng doanh thu tương ứng.
"""

import json
import logging

from pydantic import BaseModel

from app.core.config import settings
from app.ml import llm, stt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schema (shared with router)
# ---------------------------------------------------------------------------

class DraftRevenueItem(BaseModel):
    amount: float | None = None
    description: str | None = None
    revenue_date: str | None = None   # YYYY-MM-DD; null = today (let client fill)
    money_channel: str | None = None  # "cash" | "bank" | null


class DraftRevenueResult(BaseModel):
    items: list[DraftRevenueItem]
    raw_transcript: str
    confidence: str  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Bạn là trợ lý ghi sổ doanh thu cho hộ kinh doanh nhỏ ở Việt Nam.
Nhiệm vụ: từ câu nói của chủ shop, trích xuất thông tin doanh thu thành JSON.

Quy tắc quan trọng về items:
- Mỗi kênh thanh toán khác nhau = một item riêng biệt.
  Ví dụ: "3 triệu tiền mặt và 1 triệu 250 bank" → 2 items: [{cash, 3000000}, {bank, 1250000}]
- Nếu chỉ có một kênh hoặc không rõ kênh → 1 item duy nhất.
- "money_channel": "cash" nếu có từ "tiền mặt", "tiền tươi"; "bank" nếu có từ "chuyển khoản", "thẻ", "ví", "bank"; null nếu không rõ.
- "revenue_date": YYYY-MM-DD nếu nói ngày cụ thể; null nếu không nói (ngầm là hôm nay).
- "amount": số tiền (đơn vị đồng). "triệu" = 1.000.000, "nghìn"/"ngàn" = 1.000, "trăm" = 100.
- "description": mô tả chung cho tất cả items (lấy từ tên hàng/dịch vụ được nhắc đến).
- "confidence": "high" nếu trích xuất rõ amount + description; "medium" nếu thiếu một; "low" nếu quá mơ hồ.

Output format:
{
  "items": [
    {
      "amount":        <số tiền hoặc null>,
      "description":   "<mô tả hoặc null>",
      "revenue_date":  "<YYYY-MM-DD hoặc null>",
      "money_channel": "cash" | "bank" | null
    }
  ],
  "confidence": "high" | "medium" | "low"
}"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def process_draft_revenue(
    audio_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> DraftRevenueResult:
    # Step 1: Speech-to-Text
    transcript = await stt.transcribe(audio_bytes, mime_type)
    if not transcript.strip():
        return DraftRevenueResult(items=[], raw_transcript="", confidence="low")

    # Step 2: LLM extraction
    user_prompt = (
        f"Câu nói của chủ shop: \"{transcript}\"\n\n"
        "Trích xuất thông tin doanh thu theo format JSON đã quy định. "
        "Nhớ tách riêng từng kênh thanh toán thành item riêng."
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

def _parse_llm_response(raw: str, transcript: str) -> DraftRevenueResult:
    try:
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        items = [DraftRevenueItem(**item) for item in data.get("items", [])]
        return DraftRevenueResult(
            items=items,
            raw_transcript=transcript,
            confidence=data.get("confidence", "low"),
        )
    except Exception as exc:
        logger.error("Failed to parse draft revenue LLM response: %s", exc)
        return DraftRevenueResult(items=[], raw_transcript=transcript, confidence="low")
