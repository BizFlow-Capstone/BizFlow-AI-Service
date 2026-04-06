from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import verify_internal_secret
from app.services.draft_revenue_service import DraftRevenueResult, process_draft_revenue

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


@router.post(
    "",
    response_model=DraftRevenueResult,
    status_code=status.HTTP_200_OK,
    summary="Tạo draft doanh thu từ giọng nói",
    description=(
        "Nhận file audio tiếng Việt, chạy STT → LLM extraction. "
        "Trả về draft doanh thu (số tiền, mô tả, ngày, kênh thanh toán) để user xem lại trước khi lưu. "
        "Ví dụ: 'Hôm nay bán áo thun được 3 triệu rưỡi, tiền mặt'. "
        "Thời gian xử lý: ~3–6 giây."
    ),
)
async def draft_revenue(
    audio: Annotated[UploadFile, File(description="File audio (webm / mp3 / wav / ogg / m4a)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> DraftRevenueResult:
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"
    return await process_draft_revenue(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        location_id=location_id,
    )
