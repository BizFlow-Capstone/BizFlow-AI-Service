from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import verify_internal_secret
from app.services.reorder_service import ReorderSummary, run_reorder

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


class ReorderRequest(BaseModel):
    location_ids: list[str]


class ReorderResponse(BaseModel):
    processed: int
    skipped: int
    results: list[ReorderSummary]


@router.post(
    "",
    response_model=ReorderResponse,
    status_code=status.HTTP_200_OK,
    summary="Tính gợi ý nhập hàng (nightly job)",
    description=(
        "Tính reorder point + suggested quantity cho tất cả sản phẩm của từng location "
        "dựa trên rolling 14-day sales velocity + safety stock formula. "
        "Ghi kết quả vào bảng ai_reorder_suggestions. "
        "Yêu cầu tối thiểu 14 ngày lịch sử bán hàng."
    ),
)
async def reorder(body: ReorderRequest) -> ReorderResponse:
    results: list[ReorderSummary] = []
    skipped = 0
    for location_id in body.location_ids:
        result = await run_reorder(location_id)
        if result is None:
            skipped += 1
        else:
            results.append(result)
    return ReorderResponse(processed=len(results), skipped=skipped, results=results)
