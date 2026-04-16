# =============================================================================
# BizFlow AI Service — Docker image
# =============================================================================
# Multi-stage build: keeps final image lean by avoiding build-time deps.

# ---------- build stage ------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools required by some Python packages (e.g. sentence-transformers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- runtime stage ----------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# ffmpeg: converts any incoming audio format (AMR, 3GPP, AAC, WebM, ...)
# to a universally-supported WAV before passing to Google STT / Whisper.
# curl: required by docker-compose healthcheck probe.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Sentence-transformers model will be downloaded on first run and cached here
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV HF_HOME=/app/.cache/huggingface

# ChromaDB persistence directory
ENV CHROMA_PERSIST_DIR=/app/chroma_data

EXPOSE 5000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
