"""Schema round-trip and JSON Schema export tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from slidegen.schema import Deck, Slide, deck_json_schema, export_json_schema

ROOT = Path(__file__).resolve().parents[1]


def _slide() -> dict:
    return {
        "id": "intro",
        "title": "Intro",
        "subtitle": "sub",
        "steps": [
            {"number": 1, "heading": "h", "body_markdown": "**b**"},
            {
                "number": 2,
                "heading": "h2",
                "body_markdown": "b2",
                "image": {"src": "a/b.png", "alt": "x"},
            },
        ],
    }


def test_round_trip() -> None:
    deck = Deck.model_validate({"slides": [_slide()]})
    again = Deck.model_validate_json(deck.model_dump_json())
    assert again == deck
    assert again.slides[0].steps[1].image is not None


def test_numeric_string_number_is_coerced() -> None:
    """Existing slides/slide1.json uses "1" for number."""
    s = _slide()
    s["steps"][0]["number"] = "1"
    assert Slide.model_validate(s).steps[0].number == 1


def test_repo_slides_validate() -> None:
    for f in (ROOT / "slides").glob("*.json"):
        data = json.loads(f.read_text())
        Deck.model_validate(data if "slides" in data else {"slides": [data]})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(steps=[]),
        lambda s: s.pop("title"),
        lambda s: s.update(extra="nope"),
    ],
)
def test_invalid_slides_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    s = _slide()
    mutate(s)
    with pytest.raises(ValidationError):
        Deck.model_validate({"slides": [s]})


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Deck.model_validate({"slides": [_slide(), _slide()]})


def test_json_schema_is_strict_and_committed(tmp_path: Path) -> None:
    schema = deck_json_schema()
    assert schema["additionalProperties"] is False
    assert all(d["additionalProperties"] is False for d in schema["$defs"].values())
    out = export_json_schema(tmp_path / "s.json")
    assert json.loads(out.read_text()) == schema
    committed = json.loads((ROOT / "schema" / "slide.schema.json").read_text())
    assert committed == schema, "run: uv run slidegen export-schema"
