"""
ml/stt.py — Speech-to-Text wrapper

Primary:  Google Cloud STT **v2** (vi-VN, Synchronous Recognition)
           Uses AutoDetectDecodingConfig — supports all common audio formats
           (webm, m4a, mp3, wav, ogg, flac, aac, ...) without manual encoding map.
           Free tier: 60 min/month. Dedicated Vietnamese acoustic model.
           Requires: GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT in env.

Fallback: OpenAI Whisper (whisper-1)
           Activated automatically if:
             - GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CLOUD_PROJECT is not set, OR
             - Google STT raises a quota / service error, OR
             - Google STT returns an empty transcript.

Both providers accept a raw audio bytes payload and return a plain
transcript string. All STT logic is isolated here so the draft_order
service never needs to know which engine was used.
"""

import io
import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def transcribe(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """
    Transcribe Vietnamese speech audio to text.

    Args:
        audio_bytes: Raw audio file content (webm, m4a, mp3, wav, ogg, ...).
        mime_type:   MIME type hint (codec params stripped automatically).

    Returns:
        Transcript string (may be empty if no speech detected).

    Raises:
        STTError: when both providers fail.
    """
    # Strip codec params: "audio/webm; codecs=opus" → "audio/webm"
    normalized_mime_type = _normalize_audio_mime_type(mime_type)
    logger.info("STT request: mime=%s bytes=%d", normalized_mime_type, len(audio_bytes))

    if settings.google_application_credentials and settings.google_cloud_project:
        try:
            transcript = await _transcribe_google_v2(audio_bytes)
            if transcript.strip():
                return transcript
            # Google returned empty (no speech detected) — fall through to Whisper
            logger.warning("Google STT v2 returned empty transcript — falling back to Whisper.")
        except Exception as exc:
            logger.warning(
                "Google STT v2 failed (%s) — falling back to Whisper.", exc, exc_info=True
            )

    return await _transcribe_whisper(audio_bytes, normalized_mime_type)


# ---------------------------------------------------------------------------
# Google Cloud STT v2
# ---------------------------------------------------------------------------

async def _transcribe_google_v2(audio_bytes: bytes) -> str:
    """
    Call Google Cloud Speech-to-Text v2 Synchronous Recognition.

    Key advantage over v1: AutoDetectDecodingConfig handles all audio formats
    automatically — no manual encoding map needed. M4A, AAC, MP3, WebM, WAV,
    OGG are all supported transparently.
    """
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech

    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)

    client = SpeechClient()

    config = cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=["vi-VN"],
        model=settings.google_stt_model,
    )

    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{settings.google_cloud_project}/locations/global/recognizers/_",
        config=config,
        content=audio_bytes,
    )

    response = client.recognize(request=request)

    transcript = " ".join(
        result.alternatives[0].transcript
        for result in response.results
        if result.alternatives
    )
    logger.info("Google STT v2 transcript: %s", transcript)
    return transcript


# ---------------------------------------------------------------------------
# OpenAI Whisper fallback
# ---------------------------------------------------------------------------

async def _transcribe_whisper(audio_bytes: bytes, mime_type: str) -> str:
    """
    Call OpenAI Whisper (whisper-1) for Speech-to-Text.
    Whisper auto-detects Vietnamese — no locale needs to be specified.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Whisper requires a file-like object with a .name attribute
    ext_map = {
        "audio/webm": "audio.webm",
        "audio/ogg":  "audio.ogg",
        "audio/mp3":  "audio.mp3",
        "audio/wav":  "audio.wav",
        "audio/m4a":  "audio.m4a",
    }
    filename = ext_map.get(mime_type, "audio.webm")

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename  # type: ignore[attr-defined]

    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="vi",
        response_format="text",
    )

    transcript = str(response).strip()
    logger.info("Whisper STT transcript: %s", transcript)
    return transcript


def _normalize_audio_mime_type(mime_type: str) -> str:
    # Strip codec parameters: "audio/webm; codecs=opus" → "audio/webm"
    base = (mime_type or "").split(";")[0].strip().lower()
    if base in {"audio/x-m4a", "audio/mp4", "audio/aac"}:
        return "audio/m4a"
    return base or "audio/webm"
