"""
ml/stt.py — Speech-to-Text wrapper

Primary:  Google Cloud STT (vi-VN, Synchronous Recognition)
           Free tier: 60 min/month. Dedicated Vietnamese acoustic model.

Fallback: OpenAI Whisper (whisper-1)
           Activated automatically if:
             - GOOGLE_APPLICATION_CREDENTIALS is not set, OR
             - Google STT raises a quota / service error.

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
        audio_bytes: Raw audio file content (webm, mp3, wav, m4a, ogg).
        mime_type:   MIME type of the audio. Used by Google STT encoding detection.

    Returns:
        Transcript string (may be empty if no speech detected).

    Raises:
        STTError: when both providers fail.
    """
    if settings.google_application_credentials:
        try:
            return await _transcribe_google(audio_bytes, mime_type)
        except Exception as exc:
            logger.warning(
                "Google STT failed (%s). Falling back to Whisper.", exc, exc_info=True
            )

    return await _transcribe_whisper(audio_bytes, mime_type)


# ---------------------------------------------------------------------------
# Google Cloud STT
# ---------------------------------------------------------------------------

async def _transcribe_google(audio_bytes: bytes, mime_type: str) -> str:
    """
    Call Google Cloud Speech-to-Text v1 Synchronous Recognition.
    Uses the vi-VN locale and WEBM_OPUS encoding by default.
    """
    from google.cloud import speech  # imported lazily to avoid hard dep at startup

    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)

    client = speech.SpeechClient()

    encoding_map = {
        "audio/webm": speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        "audio/ogg":  speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
        "audio/mp3":  speech.RecognitionConfig.AudioEncoding.MP3,
        "audio/wav":  speech.RecognitionConfig.AudioEncoding.LINEAR16,
        "audio/m4a":  speech.RecognitionConfig.AudioEncoding.MP3,
    }

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=encoding_map.get(mime_type, speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED),
        language_code="vi-VN",
        enable_automatic_punctuation=True,
        model="latest_long",
    )

    response = client.recognize(config=config, audio=audio)

    transcript = " ".join(
        result.alternatives[0].transcript
        for result in response.results
        if result.alternatives
    )
    logger.info("Google STT transcript: %s", transcript)
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
