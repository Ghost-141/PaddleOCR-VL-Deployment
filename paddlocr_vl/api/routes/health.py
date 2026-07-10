from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.config import Settings
from ...core.dependencies import get_ocr_service, get_settings
from ...service import PaddleOCRVLService
from ...schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    ocr_service: Annotated[PaddleOCRVLService, Depends(get_ocr_service)],
) -> dict[str, object]:
    return {
        "status": "healthy" if ocr_service.loaded else "starting",
        "pipeline_loaded": ocr_service.loaded,
        "vllm_server_url": settings.vllm_server_url,
        "vllm_model": settings.vllm_model_name,
        "layout_model": settings.layout_model_name,
    }
