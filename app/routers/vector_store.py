from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.dependencies import verify_internal_secret
from app.ml.vector_store import backfill_location, delete_product, list_products, sync_product

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


class BackfillRequest(BaseModel):
    location_id: str


class BackfillResponse(BaseModel):
    location_id: str
    synced: int
    skipped: int


@router.post(
    "/backfill",
    response_model=BackfillResponse,
    status_code=status.HTTP_200_OK,
    summary="Đồng bộ toàn bộ sản phẩm của một location vào ChromaDB",
    description=(
        "Lấy toàn bộ sản phẩm Active chưa bị xóa của location từ MySQL "
        "rồi upsert vào ChromaDB. Idempotent — an toàn để chạy lại nhiều lần. "
        "Dùng để backfill dữ liệu cho các sản phẩm tạo trước khi tích hợp vector store."
    ),
)
async def backfill(body: BackfillRequest) -> BackfillResponse:
    result = await backfill_location(location_id=body.location_id)
    return BackfillResponse(**result)


class ProductItem(BaseModel):
    product_id: str
    name: str
    unit: str
    category: str
    document: str


class ListResponse(BaseModel):
    location_id: str
    total: int
    items: list[ProductItem]


@router.get(
    "/list",
    response_model=ListResponse,
    status_code=status.HTTP_200_OK,
    summary="Xem toàn bộ sản phẩm trong ChromaDB của một location",
    description="Trả về danh sách sản phẩm đang được lưu trong vector store. Dùng để debug / kiểm tra dữ liệu đồng bộ.",
)
async def list_collection(
    location_id: str,
    limit: int = 200,
) -> ListResponse:
    result = list_products(location_id=location_id, limit=limit)
    return ListResponse(**result)
