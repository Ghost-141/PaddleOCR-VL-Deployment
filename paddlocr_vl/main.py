from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .api.router import api_router
from .core.config import Settings, load_settings
from .core.logger import configure_logging
from .service import PaddleOCRVLService

configure_logging()


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings()
    ocr_service = PaddleOCRVLService(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        config.upload_dir.mkdir(parents=True, exist_ok=True)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        ocr_service.start()
        yield
        ocr_service.stop()

    app = FastAPI(
        title="PaddleOCR-VL Document Parser API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.ocr_service = ocr_service
    app.include_router(api_router)
    return app


app = create_app()
