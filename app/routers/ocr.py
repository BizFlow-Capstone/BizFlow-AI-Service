from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import verify_internal_secret
from app.services.ocr_service import (
    PurchaseInvoiceResult,
    SaleInvoiceResult,
    extract_purchase_invoice,
    extract_sale_invoice,
)

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


@router.post(
    "/purchase-invoice",
    response_model=PurchaseInvoiceResult,
    status_code=status.HTTP_200_OK,
    summary="OCR hóa đơn nhập hàng",
    description=(
        "Nhận ảnh hóa đơn nhập hàng từ nhà cung cấp — có thể là hóa đơn đỏ (VAT) "
        "hoặc phiếu mua hàng không hóa đơn (mẫu 01/TNDN). "
        "GPT-4o Vision trích xuất: tên NCC, ngày, tên SP, SL, đơn giá, tổng tiền. "
        "Kết quả trả về dạng draft để user review trước khi lưu nhập hàng / chi phí. "
        "Ảnh ≤ 1 MB (client resize trước khi upload). Thời gian xử lý: ~3–8 giây."
    ),
)
async def ocr_purchase_invoice(
    image: Annotated[UploadFile, File(description="Ảnh hóa đơn nhập hàng (JPEG / PNG / WEBP, ≤ 1 MB)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> PurchaseInvoiceResult:
    image_bytes = await image.read()
    mime_type = image.content_type or "image/jpeg"
    return await extract_purchase_invoice(image_bytes=image_bytes, mime_type=mime_type, location_id=location_id)


@router.post(
    "/sale-invoice",
    response_model=SaleInvoiceResult,
    status_code=status.HTTP_200_OK,
    summary="OCR hóa đơn bán hàng",
    description=(
        "Nhận ảnh hóa đơn bán hàng do shop phát hành (hóa đơn đỏ khi bán). "
        "GPT-4o Vision trích xuất: tên người mua, số hóa đơn, ngày, tên SP, SL, đơn giá, VAT, tổng tiền. "
        "Kết quả trả về dạng draft để user review trước khi lưu doanh thu. "
        "Ảnh ≤ 1 MB (client resize trước khi upload). Thời gian xử lý: ~3–8 giây."
    ),
)
async def ocr_sale_invoice(
    image: Annotated[UploadFile, File(description="Ảnh hóa đơn bán hàng (JPEG / PNG / WEBP, ≤ 1 MB)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> SaleInvoiceResult:
    image_bytes = await image.read()
    mime_type = image.content_type or "image/jpeg"
    return await extract_sale_invoice(image_bytes=image_bytes, mime_type=mime_type, location_id=location_id)
