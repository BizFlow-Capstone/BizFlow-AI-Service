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
import subprocess
import tempfile

from app.core.config import settings
from app.core.exceptions import STTError

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
    normalized_mime_type = _normalize_audio_mime_type(mime_type)
    logger.info("STT request: original_mime=%s bytes=%d", normalized_mime_type, len(audio_bytes))

    if not audio_bytes:
        raise STTError("Audio rỗng, không thể xử lý nhận dạng giọng nói.")

    # ── Provider selection log (debug config issues quickly) ──────────────────
    _google_ready = bool(settings.google_application_credentials and settings.google_cloud_project)
    if _google_ready:
        logger.info(
            "STT provider selection: GOOGLE_STT_V2 | project=%s | credentials=%s",
            settings.google_cloud_project,
            settings.google_application_credentials,
        )
    else:
        logger.warning(
            "STT provider selection: WHISPER "
            "(Google STT chưa cấu hình — "
            "GOOGLE_APPLICATION_CREDENTIALS=%r | GOOGLE_CLOUD_PROJECT=%r)",
            settings.google_application_credentials or "(empty)",
            settings.google_cloud_project or "(empty)",
        )

    # Convert all formats (AMR/Android, AAC/iPhone, 3GPP, WebM, ...) to
    # 16 kHz mono WAV so both Google STT v2 and Whisper receive a format
    # they universally support — no more per-format codec mapping needed.
    audio_bytes = _convert_audio_to_wav(audio_bytes, normalized_mime_type)

    # Warn if audio likely exceeds Google STT Sync limit (~60 s inline)
    # 16kHz * 16-bit * mono = 32 000 bytes/s  →  60 s ≈ 1.9 MB WAV
    _GOOGLE_SYNC_LIMIT_BYTES = 1_900_000
    if _google_ready and len(audio_bytes) > _GOOGLE_SYNC_LIMIT_BYTES:
        estimated_seconds = len(audio_bytes) / 32_000
        logger.warning(
            "Audio dài ước tính %.0fs (>60s) — Google STT Sync có thể fail, "
            "sẽ tự động fallback sang Whisper.",
            estimated_seconds,
        )

    if _google_ready:
        try:
            transcript = await _transcribe_google_v2(audio_bytes)
            if transcript.strip():
                logger.info(
                    "✓ STT used: GOOGLE_STT_V2 | chars=%d", len(transcript)
                )
                return transcript
            # Google returned empty (no speech detected) — fall through to Whisper
            logger.warning("Google STT v2 trả transcript rỗng — falling back to Whisper.")
        except Exception as exc:
            logger.warning(
                "Google STT v2 failed (%s) — falling back to Whisper.", exc, exc_info=True
            )

    logger.info("STT falling through to WHISPER")
    transcript = await _transcribe_whisper(
        audio_bytes,
        "audio/wav",
        source_mime_type=normalized_mime_type,
    )
    logger.info("✓ STT used: WHISPER | chars=%d", len(transcript))
    return transcript


# ---------------------------------------------------------------------------
# FFmpeg audio normalizer
# ---------------------------------------------------------------------------

def _convert_audio_to_wav(audio_bytes: bytes, source_mime_type: str) -> bytes:
    """
    Convert any audio format to 16 kHz mono WAV using ffmpeg.

    Uses temp files instead of stdin pipe because container formats
    (3GP, MP4, M4A) may have the moov atom at the end of the file —
    ffmpeg needs to seek backward to read it, which pipes don't support.
    """
    input_format = _resolve_ffmpeg_input_format(source_mime_type, audio_bytes)
    logger.info(
        "ffmpeg input: source_mime=%s, detected_format=%s, bytes=%d",
        source_mime_type, input_format or "auto", len(audio_bytes),
    )

    # Determine proper file extension so ffmpeg can also use it as a hint
    ext_map = {
        "3gp": ".3gp", "mp4": ".mp4", "webm": ".webm", "ogg": ".ogg",
        "wav": ".wav", "mp3": ".mp3", "flac": ".flac", "amr": ".amr",
        "matroska": ".mkv",
    }
    in_ext = ext_map.get(input_format or "", ".bin")

    try:
        # Write input to a temp file (ffmpeg can seek on it)
        with tempfile.NamedTemporaryFile(suffix=in_ext, delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path + ".wav"

        ffmpeg_cmd = ["ffmpeg", "-y"]
        if input_format:
            ffmpeg_cmd.extend(["-f", input_format])
        ffmpeg_cmd.extend([
            "-i", tmp_in_path,
            "-vn",                   # ignore video stream if present
            "-ar", "16000",          # 16 kHz — optimal for speech recognition
            "-ac", "1",              # mono
            "-acodec", "pcm_s16le",  # stable WAV codec
            "-f", "wav",
            tmp_out_path,
        ])

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error("ffmpeg conversion failed: %s", result.stderr.decode(errors="replace"))
            raise STTError(
                "Không thể đọc file audio. "
                "Vui lòng dùng định dạng webm, mp4, m4a, mp3, wav hoặc ogg."
            )

        wav_bytes = open(tmp_out_path, "rb").read()

    except FileNotFoundError:
        raise STTError("ffmpeg chưa được cài đặt trên server.")
    except subprocess.TimeoutExpired:
        raise STTError("Chuyển đổi audio mất quá nhiều thời gian, vui lòng thử lại với file nhỏ hơn.")
    except STTError:
        raise
    finally:
        # Clean up temp files
        for p in (tmp_in_path, tmp_out_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    # WAV must start with RIFF header and contain more than a bare header.
    if len(wav_bytes) <= 64 or not wav_bytes.startswith(b"RIFF"):
        raise STTError(
            "File audio không hợp lệ sau khi chuyển đổi. "
            "Nếu ghi âm từ Android, vui lòng chọn định dạng AAC/M4A thay vì AMR."
        )

    logger.debug("ffmpeg conversion: %d → %d bytes (16kHz mono WAV)", len(audio_bytes), len(wav_bytes))
    return wav_bytes


def _resolve_ffmpeg_input_format(source_mime_type: str, audio_bytes: bytes) -> str | None:
    """
    Best-effort format hint for ffmpeg when input comes from stdin.

    IMPORTANT: header sniffing runs FIRST because MIME types from clients
    are often wrong — e.g. Android voice recorders produce 3GP/AMR files
    but the client may report audio/x-m4a or audio/m4a.
    """
    # ── 1. Header sniff (bytes never lie) ─────────────────────────
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        brand = audio_bytes[8:12]
        if brand.startswith(b"3gp"):
            return "3gp"
        # isom, M4A, mp41, mp42 etc. — all ISO base media → mp4 demuxer
        return "mp4"
    if len(audio_bytes) >= 4:
        head4 = audio_bytes[:4]
        if head4 == b"RIFF":
            return "wav"
        if head4 == b"OggS":
            return "ogg"
        if head4 == b"fLaC":
            return "flac"
        if head4 == b"\x1aE\xdf\xa3":  # EBML header → WebM / Matroska
            return "matroska"
        # MP3: ID3 tag or MPEG sync word
        if head4[:3] == b"ID3" or head4[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
            return "mp3"
        # AMR bare stream (no container)
        if audio_bytes[:6] == b"#!AMR\n" or audio_bytes[:9] == b"#!AMR-WB\n":
            return "amr"

    # ── 2. MIME fallback (only when header is inconclusive) ───────
    mime = (source_mime_type or "").lower()
    if mime in {"audio/3gpp", "audio/3gpp2", "video/3gpp", "video/3gpp2"}:
        return "3gp"
    if mime in {"audio/mp4", "audio/m4a", "audio/x-m4a"}:
        return "mp4"
    if mime in {"audio/webm"}:
        return "webm"
    if mime in {"audio/ogg", "audio/oga"}:
        return "ogg"
    if mime in {"audio/wav", "audio/x-wav"}:
        return "wav"
    if mime in {"audio/mpeg", "audio/mp3"}:
        return "mp3"
    if mime in {"audio/amr"}:
        return "amr"

    # ── 3. No hint — let ffmpeg auto-detect ───────────────────────
    return None


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

async def _transcribe_whisper(
    audio_bytes: bytes,
    mime_type: str,
    source_mime_type: str | None = None,
) -> str:
    """
    Call OpenAI Whisper (whisper-1) for Speech-to-Text.
    Whisper auto-detects Vietnamese — no locale needs to be specified.
    """
    from openai import AsyncOpenAI, APIError, BadRequestError

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Whisper requires a file-like object with a .name attribute.
    # Use mp4 as fallback (better than webm for phone recordings).
    ext_map = {
        "audio/webm": "audio.webm",
        "audio/ogg":  "audio.ogg",
        "audio/mp3":  "audio.mp3",
        "audio/mpeg": "audio.mp3",
        "audio/wav":  "audio.wav",
        "audio/m4a":  "audio.m4a",
        "audio/mp4":  "audio.mp4",
    }
    filename = ext_map.get(mime_type, "audio.mp4")

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename  # type: ignore[attr-defined]

    try:
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="vi",
            response_format="text",
        )
    except BadRequestError as exc:
        original_mime = source_mime_type or mime_type
        raise STTError(
            f"Định dạng audio không được hỗ trợ (mime_goc={original_mime}). "
            "Vui lòng dùng định dạng webm, mp4, m4a, mp3, wav hoặc ogg."
        ) from exc
    except APIError as exc:
        raise STTError(f"Whisper API lỗi: {exc}") from exc

    transcript = str(response).strip()
    logger.info("Whisper STT transcript: %s", transcript)
    return transcript


def _normalize_audio_mime_type(mime_type: str) -> str:
    # Used only for logging the original client-reported MIME type.
    base = (mime_type or "").split(";")[0].strip().lower()
    return base or "audio/webm"
