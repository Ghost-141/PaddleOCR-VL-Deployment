from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from paddleocr import PaddleOCRVL

from ..core.config import Settings
from ..utils.file_utils import read_json, read_markdown


class PaddleOCRVLService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._pipeline: PaddleOCRVL | None = None

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    def start(self) -> None:
        self._pipeline = PaddleOCRVL(
            pipeline_version=self.settings.pipeline_version,
            vl_rec_backend="vllm-server",
            vl_rec_server_url=self.settings.vllm_server_url,
            vl_rec_api_model_name=self.settings.vllm_model_name,
            vl_rec_api_key=self.settings.vllm_api_key,
            vl_rec_max_concurrency=self.settings.vl_rec_max_concurrency,
            layout_detection_model_name=self.settings.layout_model_name,
        )

    def stop(self) -> None:
        self._pipeline = None

    def predict(self, input_path: Path, output_dir: Path) -> dict[str, Any]:
        if self._pipeline is None:
            raise RuntimeError("PaddleOCR-VL pipeline is not initialized")
        output_dir.mkdir(parents=True, exist_ok=True)
        pages: list[dict[str, Any]] = []
        markdown: list[str] = []
        with self._lock:
            for index, result in enumerate(self._pipeline.predict(str(input_path)), start=1):
                json_path = output_dir / f"page_{index}.json"
                markdown_path = output_dir / f"page_{index}.md"
                result.save_to_json(save_path=str(json_path))
                result.save_to_markdown(save_path=str(markdown_path))
                page_markdown = read_markdown(markdown_path)
                pages.append({"page": index, "json": read_json(json_path), "markdown": page_markdown})
                markdown.append(f"## Page {index}\n\n{page_markdown}")
                if index >= self.settings.max_pages:
                    break
        return {
            "processed_pages": len(pages),
            "pages": pages,
            "combined_markdown": "\n\n---\n\n".join(markdown),
        }
