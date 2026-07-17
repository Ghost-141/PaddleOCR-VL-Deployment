from pathlib import Path
import time

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


def test_claim_regions_leases_a_batch(settings_factory, tmp_path: Path) -> None:
    store = JobStore(settings_factory())
    upload = tmp_path / "batch.pdf"
    upload.write_bytes(b"pdf")
    store.create_job(
        owner_id="owner", filename="batch.pdf", output_format="both", total_pages=1, upload_path=upload
    )
    page = store.claim("layout")
    assert page
    store.enqueue_regions(
        page,
        [
            {"label": "text", "bbox": [0, 0, 1, 1], "crop_path": str(tmp_path / f"{number}.jpg")}
            for number in range(3)
        ],
    )

    claimed = store.claim_regions("dispatcher", 2)

    assert len(claimed) == 2
    assert len({task["region_number"] for task in claimed}) == 2
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM regions WHERE status='running'").fetchone()[0] == 2


def test_region_batch_claims_jobs_round_robin(settings_factory, tmp_path: Path) -> None:
    store = JobStore(settings_factory())
    jobs = []
    for name in ("first", "second"):
        upload = tmp_path / f"{name}.pdf"
        upload.write_bytes(b"pdf")
        job = store.create_job(
            owner_id="owner", filename=upload.name, output_format="json", total_pages=1, upload_path=upload
        )
        page = store.claim(name)
        assert page
        store.enqueue_regions(
            page,
            [
                {"label": "text", "bbox": [0, 0, 1, 1], "crop_path": str(tmp_path / f"{name}-{i}.jpg")}
                for i in range(3)
            ],
        )
        jobs.append(job["id"])

    claimed = store.claim_regions("dispatcher", 2)

    assert {task["job_id"] for task in claimed} == set(jobs)


def test_stale_region_lease_cannot_finish_or_fail_a_reclaimed_region(settings_factory, tmp_path: Path) -> None:
    store = JobStore(settings_factory())
    upload = tmp_path / "lease.pdf"
    upload.write_bytes(b"pdf")
    store.create_job(
        owner_id="owner", filename="lease.pdf", output_format="json", total_pages=1, upload_path=upload
    )
    page = store.claim("layout")
    assert page
    store.enqueue_regions(
        page, [{"label": "text", "bbox": [0, 0, 1, 1], "crop_path": str(tmp_path / "crop.jpg")}]
    )
    stale = store.claim_region("first")
    assert stale
    with store.connect() as db:
        db.execute("UPDATE regions SET lease_expires=?", (time.time() - 1,))
    current = store.claim_region("replacement")
    assert current and current["attempts"] == 2

    assert store.finish_region(stale, tmp_path / "stale.json") is False
    store.fail_region(stale, "late failure", transient=False)
    with store.connect() as db:
        status, attempts = db.execute("SELECT status, attempts FROM regions").fetchone()
    assert (status, attempts) == ("running", 2)
    assert store.finish_region(current, tmp_path / "current.json") is True


def test_expired_region_stops_after_the_retry_limit(settings_factory, tmp_path: Path) -> None:
    store = JobStore(settings_factory(max_retries=1))
    upload = tmp_path / "retry.pdf"
    upload.write_bytes(b"pdf")
    job = store.create_job(
        owner_id="owner", filename="retry.pdf", output_format="json", total_pages=1, upload_path=upload
    )
    page = store.claim("layout")
    assert page
    store.enqueue_regions(
        page, [{"label": "text", "bbox": [0, 0, 1, 1], "crop_path": str(tmp_path / "crop.jpg")}]
    )
    assert store.claim_region("first")
    with store.connect() as db:
        db.execute("UPDATE regions SET lease_expires=?", (time.time() - 1,))
    assert store.claim_region("second")
    with store.connect() as db:
        db.execute("UPDATE regions SET lease_expires=?", (time.time() - 1,))

    assert store.claim_region("third") is None
    assert store.get(job["id"])["status"] == "failed"  # type: ignore[index]


def test_completed_page_region_artifacts_can_be_deleted(settings_factory, tmp_path: Path) -> None:
    store = JobStore(settings_factory())
    upload = tmp_path / "artifacts.pdf"
    upload.write_bytes(b"pdf")
    job = store.create_job(
        owner_id="owner", filename="artifacts.pdf", output_format="json", total_pages=1, upload_path=upload
    )
    page = store.claim("layout")
    assert page
    crop = tmp_path / "crop.jpg"
    crop.write_bytes(b"jpeg")
    store.enqueue_regions(page, [{"label": "text", "bbox": [0, 0, 1, 1], "crop_path": str(crop)}])
    region = store.claim_region("vlm")
    assert region
    result = tmp_path / "region.json"
    result.write_text('{"parsing_res_list": []}')
    assert store.finish_region(region, result)
    merge = store.claim_page_merge("vlm", job["id"], 1)
    assert merge
    page_result = tmp_path / "page.json"
    page_result.write_text('{"parsing_res_list": []}')
    assert store.complete_region_page(merge, page_result)

    store.delete_region_artifacts(job["id"], 1)

    assert not crop.exists()
    assert not result.exists()
