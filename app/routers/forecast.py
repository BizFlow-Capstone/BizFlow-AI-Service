from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import verify_internal_secret
from app.services.forecast_service import ForecastSummary, run_forecast

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


class ForecastRequest(BaseModel):
    location_ids: list[str]


class ForecastResponse(BaseModel):
    processed: int
    skipped: int
    results: list[ForecastSummary]


@router.post(
    "",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Chạy dự báo doanh thu (nightly job)",
    description=(
        "Tính EMA 7 ngày + confidence band cho từng location, "
        "sau đó gọi GPT-4o-mini để sinh giải thích xu hướng bằng tiếng Việt. "
        "Kết quả được ghi vào bảng ai_revenue_forecasts. "
        "Yêu cầu tối thiểu 14 ngày dữ liệu confirmed orders."
    ),
)
async def forecast(body: ForecastRequest) -> ForecastResponse:
    results: list[ForecastSummary] = []
    skipped = 0
    for location_id in body.location_ids:
        result = await run_forecast(location_id)
        if result is None:
            skipped += 1
        else:
            results.append(result)
    return ForecastResponse(processed=len(results), skipped=skipped, results=results)
