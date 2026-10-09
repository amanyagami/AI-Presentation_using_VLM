# slidegen: research PDF to slide deck with a VLM

Turn a research paper PDF into a browsable, step-by-step slide deck.

```
 raw_pdfs/paper.pdf
        |  slidegen extract        PyMuPDF + pdfplumber (+ optional PaddleOCR)
        v
 extracted_data/paper/{output.json, images/}
        |  slidegen generate       Claude vision model, schema-constrained JSON
        v
 slides/paper.json                 single source of truth for the deck
        |  slidegen build-index    node build-index.js
        v
 index.json  ->  index.html        static, dependency-free viewer
```

## Install

Requires Python >= 3.10 and [uv](https://docs.astral.sh/uv/). Node >= 18 is needed for the index build and its tests.

```bash
uv sync                    # core: pymupdf, pdfplumber, pillow, pydantic (+ dev tools)
uv sync --extra vlm        # + anthropic, for `generate`
uv sync --extra ocr        # + paddleocr/paddlepaddle, for OCR whitefill (large download)
```

Without the `ocr` extra, extraction still works: figures are cropped but text is not whited out of them. `--no-ocr` forces this.

## Use

```bash
uv run slidegen extract raw_pdfs/2505.14984v1.pdf [--no-ocr] [--output-dir extracted_data]
export ANTHROPIC_API_KEY=...
uv run slidegen generate extracted_data/2505.14984v1 [--model claude-sonnet-5-5] [--dry-run]
uv run slidegen build-index          # writes index.json from slides/*.json
python -m http.server                # open http://localhost:8000/
```

- `generate` defaults to `claude-sonnet-5-5` (override with `--model` or `SLIDEGEN_MODEL`). It sends the page text, tables and downscaled base64 figures, asks for JSON constrained to `schema/slide.schema.json` (structured outputs), validates it with pydantic and, on failure, sends the error back to the model (max 2 retries). `--dry-run` prints payload sizes and makes no API call.
- Slide files in `slides/` are either one Slide or a deck `{"slides": [...]}`. See `schema/slide.schema.json` (regenerate with `uv run slidegen export-schema`).
- `node build-index.js` inlines all slides into `index.json`; `--lazy` emits `url`-only entries for single-slide files and the viewer fetches them on demand. The viewer supports both.
- The legacy `python extract_images.py <pdf|dir> [proximity] [min_area] [caption_scan]` still works as a thin wrapper.

## Deploy the viewer (Netlify / Vercel)

The viewer is static. Both `netlify.toml` and `vercel.json` set the build command to `node build-index.js` and publish the repository root. The files the site actually needs are:

- `index.html`, `index.json` (generated), `slides/*.json`
- `extracted_data/<paper>/images/*.png` (referenced by `image.src`)

To publish only those, build with `node build-index.js --dist dist` and set the publish directory to `dist`.

## Develop

```bash
uv run --frozen ruff format src/ tests/
uv run --frozen ruff check src/ tests/
uv run --frozen pytest
node --test
```

`requirements.legacy.freeze.txt` is the old, non-installable `pip freeze` kept for reference only.

---

# Original notes

(Pre-`slidegen` documentation; install steps there are superseded by the section above.)

## PDF Figure Extractor

Extracts figures, tables, and text from PDF files using PyMuPDF, pdfplumber, and PaddleOCR.

---

## Setup

```bash
conda activate <your_env_name>
pip install -r requirements.txt
```

---

## Hardcoded Paths to Update

Open `extract_images.py` and update the following:

| Variable | Line | Description |
|---|---|---|
| `OUTPUT_BASE_DIR` | `OUTPUT_BASE_DIR = Path("extracted_data")` | Root folder where all extracted output (JSON + images) is saved |

---

## Input: Where to Put Your PDFs

Place your PDF files in any local folder, then pass the path as an argument when running the script.

**Recommended structure:**
```
project/
├── extract_images.py
├── requirements.txt
├── input_pdfs/          ← put your PDFs here
│   ├── paper1.pdf
│   └── paper2.pdf
└── extracted_data/      ← output is auto-created here
```

---

## Run

**Single PDF:**
```bash
python extract_images.py input_pdfs/paper1.pdf
```

**Entire folder of PDFs:**
```bash
python extract_images.py input_pdfs/
```

**With optional parameters:**
```bash
python extract_images.py input_pdfs/paper1.pdf [proximity] [min_area] [caption_scan]
# Example:
python extract_images.py input_pdfs/paper1.pdf 20 2000 30
```

| Parameter | Default | Description |
|---|---|---|
| `proximity` | `20` | Max distance (pts) between elements to be grouped into one figure |
| `min_area` | `2000` | Minimum bounding box area (pts²) to be kept as a figure |
| `caption_scan` | `30` | How far below a figure (pts) to scan for a caption |

---

## Output

For each PDF, a folder is created under `extracted_data/`:

```
extracted_data/
└── paper1/
    ├── output.json          ← structured text, tables, and image paths per page
    └── images/
        └── page1_figure0000.png
```

`output.json` structure:
```json
{
  "1": {
    "text": "...",
    "tables": [[ ["col1", "col2"], ["val1", "val2"] ]],
    "images": [{ "path": "...", "bbox": {...}, "is_chart": false, "text_only": false }]
  }
}
```
