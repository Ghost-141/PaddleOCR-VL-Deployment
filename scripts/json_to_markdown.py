from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from paddlocr_vl.utils.markdown_assembler import assemble_document_markdown


def load_pages(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
        pages = payload["pages"]
        if pages and isinstance(pages[0], dict) and "json" in pages[0]:
            return [page["json"] for page in pages if isinstance(page, dict) and isinstance(page.get("json"), dict)]
        return [page for page in pages if isinstance(page, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("parsing_res_list"), list):
        return [payload]
    raise ValueError("Input JSON must contain either a 'pages' array or a page-level 'parsing_res_list'.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert PaddleOCR-VL JSON response into clean Markdown."
    )
    parser.add_argument("input_json", type=Path, help="Path to the saved JSON response")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output markdown file path. Defaults to the input stem with .md",
    )
    args = parser.parse_args()

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    pages = load_pages(payload)
    markdown = assemble_document_markdown(pages)

    output_path = args.output or args.input_json.with_suffix(".md")
    output_path.write_text(markdown + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
