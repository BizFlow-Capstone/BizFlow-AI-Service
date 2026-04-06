"""
services/ocr_service.py

Extracts structured data from invoice photos using GPT-4o Vision.

Two document types:
  - purchase-invoice : hóa đơn nhập hàng (hóa đơn đỏ từ NCC hoặc phiếu mua 01/TNDN)
  - sale-invoice     : hóa đơn bán hàng (hóa đơn đỏ khi chủ shop bán)

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

# ── Purchase Invoice (hóa đơn nhập hàng) ─────────────────────────────────

class PurchaseInvoiceItem(BaseModel):
    product_name: str
    quantity: float
    unit: str
    unit_price: float


class PurchaseInvoiceResult(BaseModel):
    supplier_name: str | None = None
    invoice_date: str | None = None
    items: list[PurchaseInvoiceItem]
    total_amount: float | None = None
    confidence: str  # "high" | "medium" | "low"


# ── Sale Invoice (hóa đơn bán hàng) ──────────────────────────────────────

class SaleInvoiceItem(BaseModel):
    product_name: str
    quantity: float
    unit: str
    unit_price: float


class SaleInvoiceResult(BaseModel):
    buyer_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    items: list[SaleInvoiceItem]
    vat_amount: float | None = None
    total_amount: float | None = None
    confidence: str  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PURCHASE_INVOICE_SYSTEM = """Bạn là hệ thống OCR chuyên đọc hóa đơn nhập hàng của hộ kinh doanh Việt Nam.
Nhiệm vụ: trích xuất thông tin từ ảnh hóa đơn (hóa đơn đỏ từ nhà cung cấp hoặc phiếu mua hàng không hóa đơn) và trả về JSON hợp lệ, không giải thích thêm.

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
- confidence = "low"    nếu ảnh quá mờ hoặc không phải hóa đơn/phiếu mua hàng.
- Trả về confidence = "low" với items = [] nếu không đọc được."""

_SALE_INVOICE_SYSTEM = """Bạn là hệ thống OCR chuyên đọc hóa đơn bán hàng của hộ kinh doanh Việt Nam.
Nhiệm vụ: trích xuất thông tin từ ảnh hóa đơn bán hàng (hóa đơn đỏ do shop phát hành khi bán) và trả về JSON hợp lệ, không giải thích thêm.

Output format:
{
  "buyer_name":      "<tên người mua hoặc null>",
  "invoice_number":  "<số hóa đơn hoặc null>",
  "invoice_date":    "<YYYY-MM-DD hoặc null>",
  "items": [
    {
      "product_name": "<tên sản phẩm>",
      "quantity":     <số lượng>,
      "unit":         "<đơn vị>",
      "unit_price":   <đơn giá>
    }
  ],
  "vat_amount":    <tiền VAT hoặc null>,
  "total_amount":  <tổng tiền đã bao gồm VAT hoặc null>,
  "confidence":    "high" | "medium" | "low"
}

Quy tắc:
- confidence = "high"   nếu đọc rõ ràng, tổng tiền khớp với items.
- confidence = "medium" nếu thiếu một số trường nhưng vẫn đọc được items.
- confidence = "low"    nếu ảnh quá mờ hoặc không phải hóa đơn bán hàng.
- Trả về confidence = "low" với items = [] nếu không đọc được."""




# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

async def extract_purchase_invoice(
    image_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> PurchaseInvoiceResult:
    raw = await llm.vision(
        system_prompt=_PURCHASE_INVOICE_SYSTEM,
        user_text="Hãy đọc hóa đơn/phiếu mua hàng nhập hàng trong ảnh và trả về JSON theo format đã quy định.",
        image_bytes=image_bytes,
        image_mime=mime_type,
    )
    return _parse_purchase_invoice(raw)


async def extract_sale_invoice(
    image_bytes: bytes,
    mime_type: str,
    location_id: str,
) -> SaleInvoiceResult:
    raw = await llm.vision(
        system_prompt=_SALE_INVOICE_SYSTEM,
        user_text="Hãy đọc hóa đơn bán hàng trong ảnh và trả về JSON theo format đã quy định.",
        image_bytes=image_bytes,
        image_mime=mime_type,
    )
    return _parse_sale_invoice(raw)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_purchase_invoice(raw: str) -> PurchaseInvoiceResult:
    try:
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        items = [PurchaseInvoiceItem(**item) for item in data.get("items", [])]
        return PurchaseInvoiceResult(
            supplier_name=data.get("supplier_name"),
            invoice_date=data.get("invoice_date"),
            items=items,
            total_amount=data.get("total_amount"),
            confidence=data.get("confidence", "low"),
        )
    except Exception as exc:
        logger.error("Failed to parse OCR purchase invoice response: %s", exc)
        return PurchaseInvoiceResult(items=[], confidence="low")


def _parse_sale_invoice(raw: str) -> SaleInvoiceResult:
    try:
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        items = [SaleInvoiceItem(**item) for item in data.get("items", [])]
        return SaleInvoiceResult(
            buyer_name=data.get("buyer_name"),
            invoice_number=data.get("invoice_number"),
            invoice_date=data.get("invoice_date"),
            items=items,
            vat_amount=data.get("vat_amount"),
            total_amount=data.get("total_amount"),
            confidence=data.get("confidence", "low"),
        )
    except Exception as exc:
        logger.error("Failed to parse OCR sale invoice response: %s", exc)
        return SaleInvoiceResult(items=[], confidence="low")
