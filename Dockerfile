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
# Use a virtualenv so pip properly tracks installed packages between steps.
# This prevents sentence-transformers from re-pulling the CUDA torch build
# (default on PyPI, ~1.7 GB) after we explicitly install the CPU-only wheel.
RUN python -m venv /venv
RUN /venv/bin/pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------- runtime stage ----------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# ffmpeg: converts any incoming audio format (AMR, 3GPP, AAC, WebM, ...)
# to a universally-supported WAV before passing to Google STT / Whisper.
# curl: required by docker-compose healthcheck probe.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy application source
COPY . .

# Sentence-transformers model will be downloaded on first run and cached here
ENV HF_HOME=/app/.cache/huggingface

# Reduce noisy runtime logs from Chroma telemetry in production.
ENV ANONYMIZED_TELEMETRY=False

# ChromaDB persistence directory
ENV CHROMA_PERSIST_DIR=/app/chroma_data

EXPOSE 5000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
