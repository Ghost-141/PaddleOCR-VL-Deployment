from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings
from ..service import PaddleOCRVLService

bearer_scheme = HTTPBearer(scheme_name="Bearer Authentication")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_ocr_service(request: Request) -> PaddleOCRVLService:
    return request.app.state.ocr_service


def authorize(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(bearer_scheme)],
) -> None:
    settings = get_settings(request)
    if not secrets.compare_digest(
        credentials.credentials.strip(), settings.public_api_key
    ):
        raise HTTPException(
            401,
            "Invalid public API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
