from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

ALLOWED_CONTENT_TYPES = {
    "application/pdf", "application/octet-stream", "image/png", "image/jpeg",
    "image/jpg", "image/webp", "image/tiff",
}
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
IMAGE_EXTENSIONS = ALLOWED_EXTENSIONS - {".pdf"}


def validate_upload(file: UploadFile) -> str:
    extension = Path(file.filename or "uploaded_document").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Supported formats: PDF, PNG, JPEG, WebP and TIFF")
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"Unsupported content type: {file.content_type}")
    return extension


def validate_image_upload(file: UploadFile) -> str:
    extension = validate_upload(file)
    if extension not in IMAGE_EXTENSIONS:
        raise HTTPException(415, "This endpoint accepts image files only")
    return extension


async def save_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    total_size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise HTTPException(413, "Uploaded file exceeds the configured limit")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return total_size


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    return str(value)
