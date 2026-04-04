"""
main.py — FastAPI application entry point for BizFlow AI Service.

Startup sequence (lifespan):
  1. init_vector_store() — pre-loads ChromaDB PersistentClient and
     downloads / warms up the multilingual-e5-large sentence-transformer.

Routers wired below each own their `/path` prefix and carry the
`verify_internal_secret` dependency, so no additional auth is applied here.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.ml.vector_store import init_vector_store
from app.routers import (
    anomaly,
    draft_order,
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


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(draft_order.router,      prefix="/draft-order",     tags=["Draft Order"])
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
