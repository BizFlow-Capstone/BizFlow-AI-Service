"""
ml/llm.py — OpenAI client wrapper

Provides two entry points:
  - chat()   : text-in / text-out (GPT-4o-mini). Used by:
                 draft_order_service (order extraction)
                 forecast_service    (Vietnamese trend explanation)
                 anomaly_service     (Tier-2 pattern summary)
  - vision() : image+text-in / text-out (GPT-4o). Used by:
                 ocr_service         (invoice / delivery slip extraction)

All prompt templates live in the service layer — llm.py is a pure transport
layer and contains no business logic.
"""

import logging
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ---------------------------------------------------------------------------
# Text chat (GPT-4o-mini)
# ---------------------------------------------------------------------------

async def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    response_format: dict[str, Any] | None = None,
) -> str:
    """
    Send a chat completion request to GPT-4o-mini.

    Args:
        system_prompt:   Role / persona instructions for the model.
        user_prompt:     The actual task or data.
        temperature:     Low (0.0–0.3) for structured extraction; higher for free-text explanations.
        max_tokens:      Cap on response length.
        response_format: Pass {"type": "json_object"} to enforce JSON output mode.

    Returns:
        The model's reply as a plain string (caller parses JSON if needed).
    """
    client = _get_client()

    kwargs: dict[str, Any] = {
        "model": settings.llm_chat_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""
    logger.debug("LLM chat response (first 200 chars): %s", content[:200])
    return content


# ---------------------------------------------------------------------------
# Vision (GPT-4o) — used for OCR document scanning
# ---------------------------------------------------------------------------

async def vision(
    system_prompt: str,
    user_text: str,
    image_bytes: bytes,
    image_mime: str = "image/jpeg",
    *,
    max_tokens: int = 2048,
) -> str:
    """
    Send an image + text prompt to GPT-4o Vision.

    Args:
        system_prompt: Instructions for the model (e.g., "Extract invoice data as JSON").
        user_text:     Context or additional instructions alongside the image.
        image_bytes:   Raw image bytes (JPEG / PNG / WEBP, ≤ 1 MB recommended).
        image_mime:    MIME type of the image.
        max_tokens:    Cap on response length.

    Returns:
        Model reply as a string (typically JSON — caller parses).
    """
    import base64

    client = _get_client()

    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{image_mime};base64,{b64_image}"

    response = await client.chat.completions.create(
        model=settings.llm_vision_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text",      "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            },
        ],
        max_tokens=max_tokens,
        temperature=0.1,   # low temperature for deterministic extraction
    )
    content = response.choices[0].message.content or ""
    logger.debug("LLM vision response (first 200 chars): %s", content[:200])
    return content
