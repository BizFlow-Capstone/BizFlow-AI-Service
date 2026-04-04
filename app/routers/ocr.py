from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import verify_internal_secret
from app.services.ocr_service import InvoiceResult, DeliveryNoteResult, extract_invoice, extract_delivery_note

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


@router.post(
    "/invoice",
    response_model=InvoiceResult,
    status_code=status.HTTP_200_OK,
    summary="OCR hóa đơn nhập hàng",
    description=(
        "Nhận ảnh hóa đơn từ nhà cung cấp (JPEG/PNG, ≤ 1 MB sau khi client resize). "
        "GPT-4o Vision trích xuất: tên SP, SL, đơn giá, tổng tiền. "
        "Kết quả trả về dạng draft để user review — không tự động lưu. "
        "Thời gian xử lý: ~3–8 giây."
    ),
)
async def ocr_invoice(
    image: Annotated[UploadFile, File(description="Ảnh hóa đơn (JPEG / PNG / WEBP, ≤ 1 MB)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> InvoiceResult:
    image_bytes = await image.read()
    mime_type = image.content_type or "image/jpeg"
    return await extract_invoice(image_bytes=image_bytes, mime_type=mime_type, location_id=location_id)


@router.post(
    "/delivery-note",
    response_model=DeliveryNoteResult,
    status_code=status.HTTP_200_OK,
    summary="OCR phiếu giao hàng",
    description=(
        "Nhận ảnh phiếu giao hàng. "
        "GPT-4o Vision trích xuất: tên SP, SL. "
        "Kết quả trả về dạng draft để user review — không tự động lưu."
    ),
)
async def ocr_delivery_note(
    image: Annotated[UploadFile, File(description="Ảnh phiếu giao hàng (JPEG / PNG / WEBP, ≤ 1 MB)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> DeliveryNoteResult:
    image_bytes = await image.read()
    mime_type = image.content_type or "image/jpeg"
    return await extract_delivery_note(image_bytes=image_bytes, mime_type=mime_type, location_id=location_id)
