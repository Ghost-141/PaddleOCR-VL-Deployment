from pathlib import Path

from paddlocr_vl.db.jobs import JobStore


def test_region_queue_finishes_a_page_only_after_its_regions(settings_factory, tmp_path: Path) -> None:
    settings = settings_factory()
    store = JobStore(settings)
    upload = tmp_path / "document.pdf"
    upload.write_bytes(b"pdf")
    job = store.create_job(
        owner_id="owner", filename="document.pdf", output_format="json", total_pages=1, upload_path=upload
    )
    page = store.claim("layout")
    assert page
    crop = tmp_path / "crop.jpg"
    crop.write_bytes(b"jpeg")
    store.enqueue_regions(page, [{"label": "text", "bbox": [0, 0, 10, 10], "crop_path": str(crop)}])

    region = store.claim_region("vlm")
    assert region and region["page_number"] == 1
    result = tmp_path / "region.json"
    result.write_text('{"parsing_res_list": []}')
    assert store.finish_region(region, result) is True
    merge = store.claim_page_merge("vlm", job["id"], 1)
    assert merge

    page_result = tmp_path / "page.json"
    page_result.write_text('{"parsing_res_list": []}')
    completed = store.complete_region_page(merge, page_result)
    assert completed["status"] == "completed"
