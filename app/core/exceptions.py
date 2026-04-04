from fastapi import HTTPException, status


class AIServiceError(Exception):
    """Base class for all AI Service domain exceptions."""


class InsufficientDataError(AIServiceError):
    """Raised when a location does not have enough historical data to run a model."""

    def __init__(self, location_id: str, required_days: int, available_days: int) -> None:
        self.location_id = location_id
        self.required_days = required_days
        self.available_days = available_days
        super().__init__(
            f"Location {location_id}: cần tối thiểu {required_days} ngày dữ liệu, "
            f"hiện có {available_days} ngày."
        )


class STTError(AIServiceError):
    """Raised when both Google STT and Whisper fallback fail."""


class LLMError(AIServiceError):
    """Raised when the OpenAI API call fails or returns unparseable output."""


class OCRParseError(AIServiceError):
    """Raised when GPT-4o Vision returns a response that cannot be parsed as invoice/delivery JSON."""


class VectorStoreError(AIServiceError):
    """Raised when ChromaDB operations fail."""


# ---------------------------------------------------------------------------
# HTTP exception helpers — convert domain exceptions to FastAPI HTTPException
# ---------------------------------------------------------------------------

def raise_503(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


def raise_422(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
    )
