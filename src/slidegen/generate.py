"""VLM stage: turn an extraction directory into validated slide JSON.

Uses the Anthropic Messages API with structured outputs
(``output_config.format`` = JSON Schema). Forced ``tool_choice`` is rejected by
current Sonnet/Opus models, so structured outputs is the schema-forcing mechanism.
The client is injectable so tests run offline with a fake.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from PIL import Image as PILImage
from pydantic import ValidationError

from slidegen.schema import Deck, deck_json_schema

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("SLIDEGEN_MODEL", "claude-sonnet-5-5")
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_IMAGES = 20
MAX_IMAGE_EDGE = 1568  # px; larger images are downscaled before upload
MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
You turn the extracted contents of a research paper into a slide deck.
Return a JSON object matching the provided schema: {"slides": [...]}.

Rules:
- 5 to 10 slides covering motivation, method, key results and conclusion.
- Each slide has a unique kebab-case `id`, a `title`, a `subtitle`, and 1-5 `steps`
  numbered from 1. Keep step bodies concise (1-3 sentences, markdown allowed).
- Only state facts supported by the supplied text, tables and figures.
- To show a figure, set the step's `image.src` to EXACTLY one of the figure `src`
  values listed in the input, and write a helpful `image.alt`. Never invent image paths.
  Omit `image` (null) when no figure fits.
"""

_CAPTION_SENTENCE_RE = re.compile(
    r"((?:Figure|Fig\.|Table)\s*\d+\s*[:.]\s*[^\n]{10,400}?\.)(?=\s|$)", re.IGNORECASE
)


class MessagesAPI(Protocol):
    """The slice of ``anthropic.Anthropic().messages`` that this module uses."""

    def create(self, **kwargs: Any) -> Any: ...


class ClientLike(Protocol):
    """Anything with a ``messages.create`` method (real client or test fake)."""

    messages: MessagesAPI


class GenerationError(RuntimeError):
    """Raised when the model never produced a valid deck."""


@dataclass
class Figure:
    """One extracted figure to show the model."""

    src: str
    path: Path
    page: int
    captions: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    """Loaded contents of an ``extracted_data/<paper>/`` directory."""

    name: str
    pages: dict[int, str]
    tables: dict[int, list[Any]]
    figures: list[Figure]


def extract_captions(page_text: str) -> list[str]:
    """Find ``Figure N: ...`` / ``Table N: ...`` caption sentences in page text."""
    return [m.group(1).strip() for m in _CAPTION_SENTENCE_RE.finditer(page_text)]


def load_extraction(extraction_dir: str | Path, image_base: str | None = None) -> Extraction:
    """Load ``output.json`` and resolve figure image files.

    Args:
        extraction_dir: Directory containing ``output.json`` and ``images/``.
        image_base: Site-relative prefix used for ``image.src`` values. Defaults to
            ``extracted_data/<name>/images``.

    Returns:
        The parsed :class:`Extraction`.
    """
    root = Path(extraction_dir)
    data = json.loads((root / "output.json").read_text(encoding="utf-8"))
    base = (image_base or f"extracted_data/{root.name}/images").rstrip("/")
    pages: dict[int, str] = {}
    tables: dict[int, list[Any]] = {}
    figures: list[Figure] = []
    for key in sorted(data, key=int):
        page = int(key)
        entry = data[key]
        pages[page] = entry.get("text", "")
        if entry.get("tables"):
            tables[page] = entry["tables"]
        captions = extract_captions(pages[page])
        for img in entry.get("images", []):
            fname = Path(img["path"]).name
            candidates = [Path(img["path"]), root / "images" / fname]
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                log.warning("figure file missing, skipping: %s", img["path"])
                continue
            figures.append(Figure(f"{base}/{fname}", found, page, captions))
    return Extraction(root.name, pages, tables, figures)


def encode_image(path: Path, max_edge: int = MAX_IMAGE_EDGE) -> tuple[str, str]:
    """Return ``(media_type, base64)`` for an image, downscaled to ``max_edge``."""
    with PILImage.open(path) as im:
        im = im.convert("RGB")
        if max(im.size) > max_edge:
            im.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
    return "image/png", base64.standard_b64encode(buf.getvalue()).decode("ascii")


def build_messages(ex: Extraction, max_images: int = DEFAULT_MAX_IMAGES) -> list[dict[str, Any]]:
    """Build the initial user message: paper text/tables, then labelled figures."""
    text_parts = [f"Paper: {ex.name}\n"]
    for page, text in ex.pages.items():
        text_parts.append(f"## Page {page}\n{text}\n")
        for t in ex.tables.get(page, []):
            text_parts.append("Table (rows as JSON):\n" + json.dumps(t, ensure_ascii=False) + "\n")
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(text_parts)}]

    figures = ex.figures
    if len(figures) > max_images:
        log.warning("%d figures found; sending only the first %d", len(figures), max_images)
        figures = figures[:max_images]
    for fig in figures:
        cap = " | ".join(fig.captions) if fig.captions else "(none detected)"
        content.append(
            {
                "type": "text",
                "text": f"Figure src={fig.src} (page {fig.page}). Captions on this page: {cap}",
            }
        )
        media_type, data = encode_image(fig.path)
        content.append(
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
        )
    content.append(
        {"type": "text", "text": "Create the slide deck now as JSON matching the schema."}
    )
    return [{"role": "user", "content": content}]


def payload_sizes(system: str, messages: list[dict[str, Any]]) -> dict[str, int]:
    """Summarise request size (chars, image count/bytes, rough token estimate)."""
    text_chars = len(system)
    n_images = 0
    image_b64 = 0
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            text_chars += len(c)
            continue
        for block in c:
            if block["type"] == "text":
                text_chars += len(block["text"])
            elif block["type"] == "image":
                n_images += 1
                image_b64 += len(block["source"]["data"])
    return {
        "system_chars": len(system),
        "text_chars": text_chars,
        "images": n_images,
        "image_base64_bytes": image_b64,
        "approx_text_tokens": text_chars // 4,
    }


def _response_text(response: Any) -> str:
    """Concatenate text blocks; raise on refusal/truncation."""
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise GenerationError("model refused the request")
    if stop == "max_tokens":
        raise GenerationError("output truncated at max_tokens")
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def validate_deck(raw: str, allowed_srcs: set[str]) -> Deck:
    """Parse and validate model output; also check image paths are real figures.

    Raises:
        ValueError: With a message suitable for feeding back to the model.
    """
    try:
        deck = Deck.model_validate_json(raw)
    except ValidationError as e:
        raise ValueError(str(e)) from e
    bad = [
        s.image.src
        for slide in deck.slides
        for s in slide.steps
        if s.image is not None and s.image.src not in allowed_srcs
    ]
    if bad:
        raise ValueError(
            f"image.src must be one of {sorted(allowed_srcs)}; got unknown values: {bad}"
        )
    return deck


def make_client() -> ClientLike:
    """Create a real Anthropic client (needs the ``vlm`` extra and credentials)."""
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Install the 'vlm' extra: uv sync --extra vlm") from e
    return anthropic.Anthropic()  # type: ignore[return-value]


def generate_deck(
    ex: Extraction,
    *,
    client: ClientLike | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_images: int = DEFAULT_MAX_IMAGES,
) -> Deck:
    """Call the model and return a validated :class:`Deck`.

    On validation failure the invalid output and the error are sent back to the
    model, up to ``max_retries`` extra attempts.

    Raises:
        GenerationError: If no valid deck is produced.
    """
    client = client or make_client()
    messages = build_messages(ex, max_images)
    allowed = {f.src for f in ex.figures[:max_images]}
    schema = deck_json_schema()
    last_error = ""
    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        raw = _response_text(response)
        try:
            return validate_deck(raw, allowed)
        except ValueError as e:
            last_error = str(e)
            log.warning("attempt %d produced invalid output: %s", attempt + 1, last_error[:300])
            messages = [
                *messages,
                {"role": "assistant", "content": raw or "{}"},
                {
                    "role": "user",
                    "content": "Your JSON failed validation. Fix every problem and return the "
                    f"complete corrected JSON.\n\nValidation error:\n{last_error}",
                },
            ]
    raise GenerationError(f"no valid deck after {max_retries + 1} attempts: {last_error[:500]}")


def generate_to_file(
    extraction_dir: str | Path,
    out_path: str | Path,
    *,
    client: ClientLike | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_images: int = DEFAULT_MAX_IMAGES,
    image_base: str | None = None,
    dry_run: bool = False,
) -> dict[str, int] | Path:
    """Run the full stage. With ``dry_run`` return payload sizes and call nothing."""
    ex = load_extraction(extraction_dir, image_base)
    if dry_run:
        return payload_sizes(SYSTEM_PROMPT, build_messages(ex, max_images))
    deck = generate_deck(
        ex, client=client, model=model, max_retries=max_retries, max_images=max_images
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(deck.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return out
