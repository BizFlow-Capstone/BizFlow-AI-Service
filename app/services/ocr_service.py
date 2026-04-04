"""
services/ocr_service.py

Extracts structured data from invoice / delivery slip photos using GPT-4o Vision.

Notes:
  - Image must be ≤ 1 MB (client-side resize/compress before upload).
  - Results are always returned as a draft — never auto-saved.
  - confidence field: "high" | "medium" | "low"
      "high"   : all fields parsed cleanly, totals add up
      "medium" : most fields present, minor inconsistencies
      "low"    : GPT could not reliably read the document
"""

import json
import logging

from pydantic import BaseModel

from app.ml import llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schemas (shared with router)
# ---------------------------------------------------------------------------

class InvoiceItem(BaseModel):
    product_name: str
    quantity: float
    unit: str
    unit_price: float


class InvoiceResult(BaseModel):
    supplier_name: str | None = None
    invoice_date: str | None = None
    items: list[InvoiceItem]
    total_amount: float | None = None
    confidence: str  # "high" | "medium" | "low"


class DeliveryItem(BaseModel):
    product_name: str
    quantity: float
    unit: str


class DeliveryNoteResult(BaseModel):
    items: list[DeliveryItem]
    confidence: str


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_INVOICE_SYSTEM = """Bạn là hệ thống OCR chuyên đọc hóa đơn nhập hàng của hộ kinh doanh Việt Nam.
Nhiệm vụ: trích xuất thông tin từ ảnh hóa đơn và trả về JSON hợp lệ, không giải thích thêm.

Output format:
{
  "supplier_name": "<tên nhà cung cấp hoặc null>",
  "invoice_date":  "<YYYY-MM-DD hoặc null>",
  "items": [
    {
      "product_name": "<tên sản phẩm>",
      "quantity":     <số lượng>,
      "unit":         "<đơn vị>",
      "unit_price":   <đơn giá>
    }
  ],
  "total_amount": <tổng tiền hoặc null>,
  "confidence":   "high" | "medium" | "low"
}

Quy tắc:
- confidence = "high"   nếu đọc rõ ràng, tổng tiền khớp với items.
- confidence = "medium" nếu thiếu một số trường nhưng vẫn đọc được items.
- confidence = "low"    nếu ảnh quá mờ hoặc không phải hóa đơn nhập hàng.
- Trả về confidence = "low" với items = [] nếu không đọc được."""

_DELIVERY_SYSTEM = """Bạn là hệ thống OCR đọc phiếu giao hàng của hộ kinh doanh Việt Nam.
Trích xuất danh sách sản phẩm từ ảnh và trả về JSON hợp lệ.

Output format:
{
  "items": [
    {
      "product_name": "<tên sản phẩm>",
      "quantity":     <số lượng>,
      "unit":         "<đơn vị>"
    }
  ],
  "confidence": "high" | "medium" | "low"
}"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def extract_invoice(
    image_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> InvoiceResult:
    raw = await llm.vision(
        system_prompt=_INVOICE_SYSTEM,
        user_text="Hãy đọc hóa đơn nhập hàng trong ảnh và trả về JSON theo format đã quy định.",
        image_bytes=image_bytes,
        image_mime=mime_type,
    )
    return _parse_invoice(raw)


async def extract_delivery_note(
    image_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> DeliveryNoteResult:
    raw = await llm.vision(
        system_prompt=_DELIVERY_SYSTEM,
        user_text="Hãy đọc phiếu giao hàng trong ảnh và trả về JSON theo format đã quy định.",
        image_bytes=image_bytes,
        image_mime=mime_type,
    )
    return _parse_delivery(raw)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_invoice(raw: str) -> InvoiceResult:
    try:
        # Strip markdown code fences if GPT wraps the JSON
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        items = [InvoiceItem(**item) for item in data.get("items", [])]
        return InvoiceResult(
            supplier_name=data.get("supplier_name"),
            invoice_date=data.get("invoice_date"),
            items=items,
            total_amount=data.get("total_amount"),
            confidence=data.get("confidence", "low"),
        )
    except Exception as exc:
        logger.error("Failed to parse OCR invoice response: %s", exc)
        return InvoiceResult(items=[], confidence="low")


def _parse_delivery(raw: str) -> DeliveryNoteResult:
    try:
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        items = [DeliveryItem(**item) for item in data.get("items", [])]
        return DeliveryNoteResult(items=items, confidence=data.get("confidence", "low"))
    except Exception as exc:
        logger.error("Failed to parse OCR delivery response: %s", exc)
        return DeliveryNoteResult(items=[], confidence="low")
