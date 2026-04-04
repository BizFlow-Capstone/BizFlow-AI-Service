from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import verify_internal_secret
from app.services.product_insights_service import InsightsSummary, run_product_insights

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


class ProductInsightsRequest(BaseModel):
    location_ids: list[str]


class ProductInsightsResponse(BaseModel):
    processed: int
    skipped: int
    results: list[InsightsSummary]


@router.post(
    "",
    response_model=ProductInsightsResponse,
    status_code=status.HTTP_200_OK,
    summary="Tính product performance insights (nightly job)",
    description=(
        "Tính 3 loại insight cho từng location: "
        "TOP_SELLER (bán chạy 7/30 ngày), "
        "GROWTH_TREND (sản phẩm tăng trưởng), "
        "PROMOTE_CANDIDATE (margin cao + tồn kho nhiều). "
        "Tất cả dựa trên data thực của chính business — không dùng LLM, không hallucination. "
        "Ghi kết quả vào bảng ai_product_insights."
    ),
)
async def product_insights(body: ProductInsightsRequest) -> ProductInsightsResponse:
    results: list[InsightsSummary] = []
    skipped = 0
    for location_id in body.location_ids:
        result = await run_product_insights(location_id)
        if result is None:
            skipped += 1
        else:
            results.append(result)
    return ProductInsightsResponse(processed=len(results), skipped=skipped, results=results)
