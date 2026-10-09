"""generate stage tests using a fake, offline client."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from slidegen.generate import (
    GenerationError,
    extract_captions,
    generate_deck,
    generate_to_file,
    load_extraction,
)

GOOD = {
    "slides": [
        {
            "id": "s1",
            "title": "T",
            "subtitle": "",
            "steps": [
                {
                    "number": 1,
                    "heading": "H",
                    "body_markdown": "B",
                    "image": {
                        "src": "extracted_data/paper/images/page1_figure0000.png",
                        "alt": "f",
                    },
                }
            ],
        }
    ]
}


class FakeMessages:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self.outputs.pop(0)
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)]
        )


class FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.messages = FakeMessages(outputs)


@pytest.fixture
def extraction_dir(tmp_path: Path) -> Path:
    root = tmp_path / "paper"
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (3000, 2000), "white").save(root / "images" / "page1_figure0000.png")
    out = {
        "1": {
            "text": "Intro. Figure 1: Overview of the method pipeline. More text.",
            "tables": [[["a", "b"], ["1", "2"]]],
            "images": [
                {
                    "path": "does/not/exist/page1_figure0000.png",
                    "bbox": {},
                    "is_chart": False,
                    "text_only": False,
                }
            ],
        }
    }
    (root / "output.json").write_text(json.dumps(out))
    return root


def test_extract_captions() -> None:
    caps = extract_captions("x Figure 2: A caption that is long enough. y Table 1. Short")
    assert caps == ["Figure 2: A caption that is long enough."]


def test_load_extraction_resolves_images(extraction_dir: Path) -> None:
    ex = load_extraction(extraction_dir)
    assert [f.src for f in ex.figures] == ["extracted_data/paper/images/page1_figure0000.png"]
    assert ex.figures[0].captions


def test_generate_ok_sends_base64_image_and_schema(extraction_dir: Path) -> None:
    client = FakeClient([json.dumps(GOOD)])
    deck = generate_deck(load_extraction(extraction_dir), client=client, model="m")
    assert deck.slides[0].id == "s1"
    call = client.messages.calls[0]
    assert call["model"] == "m"
    assert call["output_config"]["format"]["type"] == "json_schema"
    blocks = call["messages"][0]["content"]
    img = next(b for b in blocks if b["type"] == "image")
    assert img["source"]["type"] == "base64" and img["source"]["media_type"] == "image/png"


def test_retry_after_invalid_output_feeds_error_back(extraction_dir: Path) -> None:
    client = FakeClient(['{"slides": []}', json.dumps(GOOD)])
    deck = generate_deck(load_extraction(extraction_dir), client=client)
    assert len(deck.slides) == 1
    assert len(client.messages.calls) == 2
    retry_msgs = client.messages.calls[1]["messages"]
    assert retry_msgs[-2]["role"] == "assistant"
    assert "Validation error" in retry_msgs[-1]["content"]


def test_unknown_image_src_triggers_retry(extraction_dir: Path) -> None:
    bad = json.loads(json.dumps(GOOD))
    bad["slides"][0]["steps"][0]["image"]["src"] = "invented.png"
    client = FakeClient([json.dumps(bad), json.dumps(GOOD)])
    generate_deck(load_extraction(extraction_dir), client=client)
    assert "invented.png" in client.messages.calls[1]["messages"][-1]["content"]


def test_gives_up_after_max_retries(extraction_dir: Path) -> None:
    client = FakeClient(["not json"] * 3)
    with pytest.raises(GenerationError):
        generate_deck(load_extraction(extraction_dir), client=client, max_retries=2)
    assert len(client.messages.calls) == 3


def test_dry_run_makes_no_call_and_reports_sizes(extraction_dir: Path, tmp_path: Path) -> None:
    sizes = generate_to_file(extraction_dir, tmp_path / "o.json", dry_run=True)
    assert isinstance(sizes, dict)
    assert sizes["images"] == 1 and sizes["text_chars"] > 0 and sizes["image_base64_bytes"] > 0
    assert not (tmp_path / "o.json").exists()


def test_generate_to_file_writes_valid_deck(extraction_dir: Path, tmp_path: Path) -> None:
    out = generate_to_file(
        extraction_dir, tmp_path / "slides" / "p.json", client=FakeClient([json.dumps(GOOD)])
    )
    assert json.loads(Path(out).read_text())["slides"][0]["id"] == "s1"
