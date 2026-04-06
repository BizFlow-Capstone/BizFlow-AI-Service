from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import verify_internal_secret
from app.services.draft_cost_service import DraftCostResult, process_draft_cost

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


@router.post(
    "",
    response_model=DraftCostResult,
    status_code=status.HTTP_200_OK,
    summary="Tạo draft chi phí từ giọng nói",
    description=(
        "Nhận file audio tiếng Việt, chạy STT → LLM extraction. "
        "Trả về draft chi phí (số tiền, mô tả, ngày, loại chi phí, phương thức thanh toán) để user xem lại trước khi lưu. "
        "Ví dụ: 'Chi tiền điện tháng này 1 triệu 2, tiền mặt'. "
        "Thời gian xử lý: ~3–6 giây."
    ),
)
async def draft_cost(
    audio: Annotated[UploadFile, File(description="File audio (webm / mp3 / wav / ogg / m4a)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> DraftCostResult:
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"
    return await process_draft_cost(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        location_id=location_id,
    )
