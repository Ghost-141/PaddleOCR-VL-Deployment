import json
from pathlib import Path

from paddlocr_vl.db.jobs import JobStore
from paddlocr_vl.workers.vlm import assemble_artifacts


def test_assemble_artifacts_orders_pages_and_merges_table_headers(settings_factory) -> None:
    settings = settings_factory()
    store = JobStore(settings)
    upload = settings.upload_dir / "document.pdf"
    upload.write_bytes(b"pdf")
    job = store.create_job("owner", "document.pdf", "both", 2, upload)
    pages = Path(job["json_path"]).parent / "pages"
    pages.mkdir(exist_ok=True)
    table = "| A | B |\n|---|---|\n| 1 | 2 |"
    (pages / "000001.json").write_text(json.dumps({"parsing_res_list": [{"block_label": "doc_title", "block_content": "Document"}, {"block_label": "table", "block_content": table}]}))
    (pages / "000002.json").write_text(json.dumps({"parsing_res_list": [{"block_label": "doc_title", "block_content": "Continuation"}, {"block_label": "table", "block_content": table.replace("1 | 2", "3 | 4")}]}))

    assemble_artifacts(job)

    result = json.loads(Path(job["json_path"]).read_text())
    assert [page["page"] for page in result["pages"]] == [1, 2]
    assert result["pages"][1]["json"]["parsing_res_list"][0]["block_label"] == "section_title"
    markdown = Path(job["markdown_path"]).read_text()
    assert markdown.count("|---|---|") == 1
