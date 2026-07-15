from pathlib import Path

from PIL import Image

from paddlocr_vl.workers.layout import _crop_regions


def test_crop_regions_accepts_layout_boxes_without_reading_order(tmp_path: Path) -> None:
    page = tmp_path / "page.jpg"
    Image.new("RGB", (100, 100)).save(page)

    regions = _crop_regions(
        page,
        [
            {"label": "text", "coordinate": [0, 0, 50, 20], "order": None},
            {"label": "table", "coordinate": [0, 30, 90, 90], "order": 1},
        ],
        tmp_path / "regions",
        1,
        64,
    )

    assert [region["label"] for region in regions] == ["text", "table"]
