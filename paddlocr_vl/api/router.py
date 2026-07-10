from fastapi import APIRouter

from .routes.documents import router as documents_router
from .routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(documents_router)
