"""
main.py — FastAPI application entry point for BizFlow AI Service.

Startup sequence (lifespan):
  1. init_vector_store() — pre-loads ChromaDB PersistentClient and
     downloads / warms up the multilingual-e5-large sentence-transformer.

Routers wired below each own their `/path` prefix and carry the
`verify_internal_secret` dependency, so no additional auth is applied here.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AIServiceError, LLMError, STTError, VectorStoreError
from app.ml.vector_store import init_vector_store
from app.routers import (
    anomaly,
    draft_cost,
    draft_order,
    draft_revenue,
    forecast,
    ocr,
    product_insights,
    reorder,
    vector_store,
)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Pre-load the sentence-transformer so the first request isn't slow.
    await init_vector_store()
    yield
    # Nothing to tear down — ChromaDB PersistentClient flushes on GC.


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BizFlow AI Service",
    version="1.0.0",
    description=(
        "Internal AI microservice for BizFlow: voice-driven draft orders, "
        "revenue forecasting, anomaly detection, reorder suggestions, "
        "invoice OCR, and product performance insights."
    ),
    lifespan=lifespan,
    # Disable automatic redirect on trailing slash — prevents silent 307
    redirect_slashes=False,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exception handlers — convert to 503 instead of 500
# ---------------------------------------------------------------------------

@app.exception_handler(STTError)
async def stt_error_handler(request: Request, exc: STTError) -> JSONResponse:
    logger.error("STTError on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Không thể nhận diện giọng nói. Vui lòng thử lại."},
    )


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    logger.error("LLMError on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Dịch vụ AI xử lý ngôn ngữ tạm thời không khả dụng. Vui lòng thử lại."},
    )


@app.exception_handler(VectorStoreError)
async def vector_store_error_handler(request: Request, exc: VectorStoreError) -> JSONResponse:
    logger.error("VectorStoreError on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Dịch vụ tìm kiếm sản phẩm tạm thời không khả dụng. Vui lòng thử lại."},
    )


@app.exception_handler(AIServiceError)
async def ai_service_error_handler(request: Request, exc: AIServiceError) -> JSONResponse:
    logger.error("AIServiceError on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Dịch vụ AI gặp lỗi. Vui lòng thử lại sau."},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(draft_order.router,      prefix="/draft-order",     tags=["Draft Order"])
app.include_router(draft_revenue.router,    prefix="/draft-revenue",   tags=["Draft Revenue"])
app.include_router(draft_cost.router,       prefix="/draft-cost",      tags=["Draft Cost"])
app.include_router(forecast.router,         prefix="/forecast",        tags=["Forecast"])
app.include_router(anomaly.router,          prefix="/anomaly",         tags=["Anomaly"])
app.include_router(reorder.router,          prefix="/reorder",         tags=["Reorder"])
app.include_router(ocr.router,              prefix="/ocr",             tags=["OCR"])
app.include_router(product_insights.router, prefix="/product-insights",tags=["Product Insights"])
app.include_router(vector_store.router,     prefix="/vector-store",    tags=["Vector Store"])


# ---------------------------------------------------------------------------
# Health check (no auth — probed by docker-compose healthcheck)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"], include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "bizflow-ai"}
