from __future__ import annotations

from fastapi import FastAPI

from .api.router import api_router
from .core.config import Settings, load_settings
from .core.logger import configure_logging
from .jobs import JobStore
from .service import TritonClient

configure_logging()


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings()
    app = FastAPI(title="PaddleOCR-VL Document Parser API", version="2.0.0")
    app.state.settings = config
    app.state.job_store = JobStore(config)
    app.state.triton_client = TritonClient(config)
    app.include_router(api_router)
    return app


app = create_app()
