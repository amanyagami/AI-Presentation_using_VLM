# PDF Figure Extractor

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
