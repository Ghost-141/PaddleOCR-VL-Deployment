from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import time
from typing import Any

from .core.config import Settings, load_settings
from .jobs import JobStore
from .pdf_utils import render_page
from .service import TritonClient, TritonError
from .utils.markdown_assembler import assemble_page_markdown


def process_one(store: JobStore, client: TritonClient, worker_id: str) -> bool:
    task = store.claim(worker_id)
    if task is None:
        return False
    rendered = store.settings.jobs_dir / task["job_id"] / f".{worker_id}-{task['page_number']}.jpg"
    result_path = (
        store.settings.jobs_dir / task["job_id"] / "pages" / f"{task['page_number']:06d}.json"
    )
    try:
        render_page(Path(task["upload_path"]), task["page_number"], rendered)
        result = client.infer(rendered)
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        job = store.finish_page(task, result_path)
        if job["status"] == "completed":
            claimed = store.claim_assembly(task["job_id"])
            if claimed:
                try:
                    assemble_artifacts(claimed)
                except Exception as exc:
                    store.fail_assembly(task["job_id"], f"Artifact assembly failed: {exc}")
                else:
                    store.complete_assembly(task["job_id"])
    except TritonError as exc:
        store.fail_page(task, str(exc), exc.transient)
    except Exception as exc:
        store.fail_page(task, str(exc), False)
    finally:
        rendered.unlink(missing_ok=True)
    return True


def assemble_artifacts(job: dict[str, Any]) -> None:
    job_dir = Path(job["json_path"]).parent
    pages_dir = job_dir / "pages"
    want_json = job["output_format"] in {"json", "both"}
    want_markdown = job["output_format"] in {"markdown", "both"}
    json_file = Path(job["json_path"])
    markdown_file = Path(job["markdown_path"])
    json_tmp = json_file.with_suffix(".json.tmp")
    markdown_tmp = markdown_file.with_suffix(".md.tmp")
    previous_table_header: tuple[str, ...] | None = None

    json_output = json_tmp.open("w", encoding="utf-8") if want_json else None
    markdown_output = markdown_tmp.open("w", encoding="utf-8") if want_markdown else None
    try:
        if json_output:
            json_output.write(
                json.dumps(
                    {"job_id": job["id"], "filename": job["filename"]},
                    ensure_ascii=False,
                )[:-1]
                + ',"pages":['
            )
        for page_number in range(1, job["total_pages"] + 1):
            page = json.loads(
                (pages_dir / f"{page_number:06d}.json").read_text(encoding="utf-8")
            )
            previous_table_header = _normalize_cross_page(
                page, page_number, previous_table_header
            )
            if json_output:
                if page_number > 1:
                    json_output.write(",")
                json.dump(
                    {"page": page_number, "json": page},
                    json_output,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            if markdown_output:
                markdown = assemble_page_markdown(page)
                markdown_output.write(f"## Page {page_number}\n\n")
                if markdown:
                    markdown_output.write(markdown + "\n\n")
                markdown_output.write("---\n\n")
        if json_output:
            json_output.write("]}")
    finally:
        if json_output:
            json_output.close()
        if markdown_output:
            markdown_output.close()
    if want_json:
        json_tmp.replace(json_file)
    if want_markdown:
        markdown_tmp.replace(markdown_file)


def _normalize_cross_page(
    page: dict[str, Any],
    page_number: int,
    previous_table_header: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    result = page.get("res") if isinstance(page.get("res"), dict) else page
    blocks = result.get("parsing_res_list")
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if (
            page_number > 1
            and isinstance(block, dict)
            and block.get("block_label") in {"doc_title", "document_title", "title"}
        ):
            block["block_label"] = "section_title"
    first_table = next(
        (
            block
            for block in blocks
            if isinstance(block, dict) and block.get("block_label") == "table"
        ),
        None,
    )
    if first_table:
        lines = str(first_table.get("block_content", "")).splitlines()
        header = tuple(lines[:2])
        if previous_table_header and header == previous_table_header:
            first_table["block_content"] = "\n".join(lines[2:])
    last = next((block for block in reversed(blocks) if isinstance(block, dict)), None)
    if last and last.get("block_label") == "table":
        return tuple(str(last.get("block_content", "")).splitlines()[:2])
    return None


def run(settings: Settings) -> None:
    store = JobStore(settings)
    client = TritonClient(settings)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    last_cleanup = 0.0
    while True:
        if time.time() - last_cleanup >= 3600:
            store.cleanup()
            last_cleanup = time.time()
        if not process_one(store, client, worker_id):
            time.sleep(1)


def main() -> None:
    argparse.ArgumentParser(description="PaddleOCR-VL PDF page worker").parse_args()
    run(load_settings())


if __name__ == "__main__":
    main()
