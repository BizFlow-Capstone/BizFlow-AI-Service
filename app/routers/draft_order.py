from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import verify_internal_secret
from app.services.draft_order_service import DraftOrderResult, process_draft_order

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


@router.post(
    "",
    response_model=DraftOrderResult,
    status_code=status.HTTP_200_OK,
    summary="Tạo draft order từ giọng nói",
    description=(
        "Nhận file audio tiếng Việt, chạy STT → RAG product matching → LLM extraction. "
        "Trả về draft order để user xem lại trước khi lưu. "
        "Thời gian xử lý: ~5–8 giây."
    ),
)
async def draft_order(
    audio: Annotated[UploadFile, File(description="File audio (webm / mp3 / wav / ogg / m4a)")],
    location_id: Annotated[str, Form(description="UUID của business location")],
) -> DraftOrderResult:
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"
    return await process_draft_order(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        location_id=location_id,
    )
