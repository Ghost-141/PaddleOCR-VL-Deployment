from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.config import Settings
from ...core.dependencies import get_settings
from ...schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {"status": "healthy", "vllm_url": settings.vllm_url}
