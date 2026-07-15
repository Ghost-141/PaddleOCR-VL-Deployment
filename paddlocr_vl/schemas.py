from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    vllm_url: str


class PageResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    page: int
    json_result: Any | None = Field(default=None, alias="json")
    markdown: str | None = None


class OutputFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    BOTH = "both"


class ParseResponse(BaseModel):
    request_id: str
    filename: str | None
    content_type: str | None
    file_size_bytes: int
    processed_pages: int
    pages: list[PageResult]
    combined_markdown: str
