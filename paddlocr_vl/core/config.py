from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    public_api_key: str
    vllm_api_key: str
    vllm_server_url: str
    vllm_model_name: str
    pipeline_version: str
    layout_model_name: str
    vl_rec_max_concurrency: int
    upload_dir: Path
    output_dir: Path
    max_file_size_mb: int
    max_pages: int
    delete_temp_files: bool

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def load_settings() -> Settings:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    public_api_key = os.getenv("PUBLIC_API_KEY", "").strip()
    if not public_api_key:
        raise RuntimeError("PUBLIC_API_KEY must be configured")

    settings = Settings(
        public_api_key=public_api_key,
        vllm_api_key=os.getenv("VLLM_API_KEY", "EMPTY"),
        vllm_server_url=os.getenv(
            "VLLM_SERVER_URL", "http://paddleocr-vlm-server:8118/v1"
        ),
        vllm_model_name=os.getenv(
            "VLLM_MODEL_NAME", "PaddleOCR-VL-1.6-0.9B"
        ),
        pipeline_version=os.getenv("PIPELINE_VERSION", "v1.6"),
        layout_model_name=os.getenv("LAYOUT_MODEL_NAME", "PP-DocLayoutV2"),
        vl_rec_max_concurrency=int(os.getenv("VL_REC_MAX_CONCURRENCY", "1")),
        upload_dir=Path(os.getenv("UPLOAD_DIR", "/data/uploads")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "/data/outputs")),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "100")),
        max_pages=int(os.getenv("MAX_PAGES", "100")),
        delete_temp_files=_as_bool(os.getenv("DELETE_TEMP_FILES", "true")),
    )
    if settings.vl_rec_max_concurrency < 1:
        raise RuntimeError("VL_REC_MAX_CONCURRENCY must be at least 1")
    if settings.max_file_size_mb < 1:
        raise RuntimeError("MAX_FILE_SIZE_MB must be at least 1")
    if settings.max_pages < 1:
        raise RuntimeError("MAX_PAGES must be at least 1")
    return settings
