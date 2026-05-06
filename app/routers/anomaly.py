from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import verify_internal_secret
from app.services.anomaly_service import (
    CheckRecordResult,
    PatternCheckSummary,
    check_record_rules,
    run_pattern_check,
)

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


# ---------------------------------------------------------------------------
# Tier 1 — Realtime rule-based check (called on every order/import save)
# ---------------------------------------------------------------------------

class CheckRecordRequest(BaseModel):
    location_id: str
    record_type: Literal["order", "import", "revenue", "cost"]
    record_id: str


@router.post(
    "/check-record",
    response_model=CheckRecordResult,
    status_code=status.HTTP_200_OK,
    summary="Kiểm tra rule-based tức thời khi lưu đơn hàng / phiếu nhập",
    description=(
        "Tier 1: chạy các business rule cứng (giá = 0, SL âm, cost bất thường…) "
        "ngay lập tức khi BizFlow API lưu 1 record. "
        "Nếu phát hiện CRITICAL → BizFlow API sẽ gửi FCM push notification."
    ),
)
async def check_record(body: CheckRecordRequest) -> CheckRecordResult:
    return await check_record_rules(
        location_id=body.location_id,
        record_type=body.record_type,
        record_id=body.record_id,
    )


# ---------------------------------------------------------------------------
# Tier 2 — Nightly LLM pattern summary (called by Hangfire @ 02:00 AM)
# ---------------------------------------------------------------------------

class AnomalyPatternRequest(BaseModel):
    location_ids: list[str]


class AnomalyPatternResponse(BaseModel):
    processed: int
    skipped: int
    results: list[PatternCheckSummary]


@router.post(
    "",
    response_model=AnomalyPatternResponse,
    status_code=status.HTTP_200_OK,
    summary="Phân tích pattern bất thường 7 ngày qua (nightly job — Tier 2)",
    description=(
        "Tier 2: GPT-4o-mini xem lại dữ liệu tổng hợp 7 ngày của từng location, "
        "phát hiện pattern bất thường và sinh giải thích tiếng Việt. "
        "Yêu cầu tối thiểu 7 ngày dữ liệu."
    ),
)
async def anomaly_pattern_check(body: AnomalyPatternRequest) -> AnomalyPatternResponse:
    results: list[PatternCheckSummary] = []
    skipped = 0
    for location_id in body.location_ids:
        result = await run_pattern_check(location_id)
        if result is None:
            skipped += 1
        else:
            results.append(result)
    return AnomalyPatternResponse(processed=len(results), skipped=skipped, results=results)
