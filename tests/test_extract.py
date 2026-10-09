"""Extraction tests: pure geometry helpers plus an OCR-free smoke test."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from slidegen import extract as ex

ROOT = Path(__file__).resolve().parents[1]


def test_import_has_no_side_effects() -> None:
    code = (
        "import os, logging, slidegen.extract as e;"
        "assert 'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK' not in os.environ;"
        "assert logging.getLogger('ppocr').level == logging.NOTSET;"
        "assert e._OCR is None"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_bbox_dict_to_rect_area() -> None:
    b = ex.bbox_dict(1, 2, 11, 7)
    assert b == {"left": 1, "top": 2, "width": 10, "height": 5}
    assert ex.to_rect(b) == (1, 2, 11, 7)
    assert ex.area(b) == 50


def test_union_bbox() -> None:
    u = ex.union_bbox([ex.bbox_dict(0, 0, 10, 10), ex.bbox_dict(5, 20, 30, 25)])
    assert ex.to_rect(u) == (0, 0, 30, 25)


def test_boxes_are_close() -> None:
    a, b = ex.bbox_dict(0, 0, 10, 10), ex.bbox_dict(15, 0, 25, 10)
    assert ex.boxes_are_close(a, b, 5)
    assert not ex.boxes_are_close(a, b, 4.9)
    assert ex.boxes_are_close(a, ex.bbox_dict(5, 5, 8, 8), 0)  # overlap


def test_cluster_groups_transitively() -> None:
    boxes = [
        ex.bbox_dict(0, 0, 10, 10),
        ex.bbox_dict(12, 0, 22, 10),  # near box 0
        ex.bbox_dict(24, 0, 34, 10),  # near box 1 only
        ex.bbox_dict(500, 500, 510, 510),  # isolated
    ]
    groups = sorted(sorted(g) for g in ex.cluster(boxes, 5))
    assert groups == [[0, 1, 2], [3]]
    assert ex.cluster([], 5) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Figure 3: x", True),
        ("fig. 2 y", True),
        ("(a) left", True),
        ("Table 1", True),
        ("Plain body text", False),
    ],
)
def test_is_caption_line(text: str, expected: bool) -> None:
    assert ex.is_caption_line(text) is expected


def test_smoke_extract_small_pdf_without_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ex, "_OCR", "DISABLED")  # never touch PaddleOCR / network
    pdf = ROOT / "raw_pdfs" / "2505.14984v1.pdf"
    out = ex.process_pdf(
        pdf, ex.DEFAULT_PROXIMITY, ex.DEFAULT_MIN_AREA, ex.DEFAULT_CAPTION_SCAN, tmp_path
    )
    data = json.loads((out / "output.json").read_text())
    assert len(data) == 9
    images = [i for p in data.values() for i in p["images"]]
    assert images and all(Path(i["path"]).is_file() for i in images)
