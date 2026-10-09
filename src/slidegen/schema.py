"""Pydantic models for the slide JSON consumed by ``index.html``.

Mirrors ``notes.txt``::

    Slide{id, title, subtitle, steps[{number, heading, body_markdown, image?}]}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_SCHEMA_PATH = Path("schema/slide.schema.json")


class Image(BaseModel):
    """An image attached to a step."""

    model_config = ConfigDict(extra="forbid")

    src: str = Field(description="Image URL or site-relative path (http/https only in the viewer).")
    alt: str = Field(default="", description="Alternative text describing the image.")


class Step(BaseModel):
    """One progressively revealed step on a slide."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="1-based step number within the slide.")
    heading: str = Field(description="Short step heading.")
    body_markdown: str = Field(
        description="Step body. Supports **bold**, _italic_, [links](https://...) and paragraphs."
    )
    image: Image | None = Field(default=None, description="Optional figure for this step.")


class Slide(BaseModel):
    """A single slide made of ordered steps."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique kebab-case slide id.")
    title: str = Field(description="Slide title.")
    subtitle: str = Field(default="", description="One-line subtitle.")
    steps: list[Step] = Field(description="Ordered steps; at least one.")

    @field_validator("steps")
    @classmethod
    def _non_empty_steps(cls, v: list[Step]) -> list[Step]:
        if not v:
            raise ValueError("a slide needs at least one step")
        return v


class Deck(BaseModel):
    """A file of slides: ``{"slides": [...]}`` (the shape ``slides/*.json`` may take)."""

    model_config = ConfigDict(extra="forbid")

    slides: list[Slide] = Field(description="Ordered slides of the presentation.")

    @model_validator(mode="after")
    def _unique_ids(self) -> Deck:
        seen: set[str] = set()
        for s in self.slides:
            if s.id in seen:
                raise ValueError(f"duplicate slide id: {s.id!r}")
            seen.add(s.id)
        if not self.slides:
            raise ValueError("a deck needs at least one slide")
        return self


def _forbid_extra(node: Any) -> None:
    """Recursively set ``additionalProperties: false`` on every object schema."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            node["additionalProperties"] = False
        for v in node.values():
            _forbid_extra(v)
    elif isinstance(node, list):
        for v in node:
            _forbid_extra(v)


def deck_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for a :class:`Deck` (strict: no additional properties)."""
    schema = Deck.model_json_schema()
    _forbid_extra(schema)
    return schema


def export_json_schema(path: str | Path = DEFAULT_SCHEMA_PATH) -> Path:
    """Write the deck JSON Schema to ``path`` and return it."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(deck_json_schema(), indent=2) + "\n", encoding="utf-8")
    return out
