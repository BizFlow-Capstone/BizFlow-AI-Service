from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import verify_internal_secret
from app.ml.vector_store import delete_product, sync_product

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


class SyncProductRequest(BaseModel):
    location_id: str
    product_id: str
    name: str
    unit: str
    category: str | None = None


class DeleteProductRequest(BaseModel):
    location_id: str
    product_id: str


class SyncResponse(BaseModel):
    status: str
    product_id: str


@router.post(
    "/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Đồng bộ sản phẩm vào ChromaDB",
    description=(
        "Upsert một sản phẩm vào ChromaDB collection của location. "
        "Gọi bởi BizFlow API mỗi khi sản phẩm được tạo / cập nhật."
    ),
)
async def sync(body: SyncProductRequest) -> SyncResponse:
    await sync_product(
        location_id=body.location_id,
        product={
            "product_id": body.product_id,
            "name":       body.name,
            "unit":       body.unit,
            "category":   body.category or "",
        },
    )
    return SyncResponse(status="synced", product_id=body.product_id)


@router.post(
    "/delete",
    response_model=SyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Xóa sản phẩm khỏi ChromaDB",
    description="Gọi bởi BizFlow API khi sản phẩm bị xóa.",
)
async def delete(body: DeleteProductRequest) -> SyncResponse:
    await delete_product(location_id=body.location_id, product_id=body.product_id)
    return SyncResponse(status="deleted", product_id=body.product_id)
