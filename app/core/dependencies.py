from fastapi import Header, HTTPException, status
from app.core.config import settings


async def verify_internal_secret(
    x_internal_secret: str = Header(..., alias="X-Internal-Secret"),
) -> None:
    """
    FastAPI dependency that ensures every request to the AI Service
    originates from the BizFlow .NET API (container-to-container only).

    The BizFlow API must include the header:
        X-Internal-Secret: <value of INTERNAL_API_SECRET env var>
    """
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal secret.",
        )
