"""Command line interface: ``slidegen extract|generate|build-index``."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from slidegen import extract as ex
from slidegen.generate import (
    DEFAULT_MAX_IMAGES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    GenerationError,
    MissingCredentialsError,
)
from slidegen.schema import export_json_schema


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slidegen", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="Extract text, tables and figures from PDF(s).")
    e.add_argument("pdf", type=Path, help="A PDF file or a directory of PDFs.")
    e.add_argument("--proximity", type=float, default=ex.DEFAULT_PROXIMITY)
    e.add_argument("--min-area", type=float, default=ex.DEFAULT_MIN_AREA)
    e.add_argument("--caption-scan", type=float, default=ex.DEFAULT_CAPTION_SCAN)
    e.add_argument("--output-dir", type=Path, default=ex.OUTPUT_BASE_DIR)
    e.add_argument("--no-ocr", action="store_true", help="Disable PaddleOCR whitefill/detection.")

    g = sub.add_parser("generate", help="Generate slide JSON from an extraction directory.")
    g.add_argument("extraction_dir", type=Path, help="e.g. extracted_data/<paper>")
    g.add_argument("-o", "--output", type=Path, help="Default: slides/<paper>.json")
    g.add_argument("--model", default=DEFAULT_MODEL)
    g.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    g.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES)
    g.add_argument("--image-base", help="Site-relative prefix for image.src values.")
    g.add_argument("--dry-run", action="store_true", help="Print payload sizes; no API call.")

    b = sub.add_parser("build-index", help="Run build-index.js to write index.json.")
    b.add_argument("--lazy", action="store_true", help="Emit url-only entries (no inline steps).")

    s = sub.add_parser("export-schema", help="Write schema/slide.schema.json.")
    s.add_argument("-o", "--output", type=Path, default=Path("schema/slide.schema.json"))
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.cmd == "extract":
        if args.no_ocr:
            ex.disable_ocr()
        target: Path = args.pdf
        if target.is_dir():
            pdfs = sorted(target.glob("*.pdf")) + sorted(target.glob("*.PDF"))
            if not pdfs:
                print(f"No PDF files found in {target}")
                return 1
        elif target.is_file():
            pdfs = [target]
        else:
            print(f"Path not found: {target}")
            return 1
        for pdf in pdfs:
            ex.process_pdf(pdf, args.proximity, args.min_area, args.caption_scan, args.output_dir)
        return 0

    if args.cmd == "generate":
        from slidegen.generate import generate_to_file

        out = args.output or Path("slides") / f"{args.extraction_dir.name}.json"
        try:
            result = generate_to_file(
                args.extraction_dir,
                out,
                model=args.model,
                max_retries=args.max_retries,
                max_images=args.max_images,
                image_base=args.image_base,
                dry_run=args.dry_run,
            )
        except (MissingCredentialsError, GenerationError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(json.dumps({"model": args.model, **result}, indent=2))  # type: ignore[arg-type]
        else:
            print(f"wrote {result}")
        return 0

    if args.cmd == "build-index":
        node = shutil.which("node")
        if node is None:
            print("node is required for build-index (https://nodejs.org)")
            return 1
        script = Path.cwd() / "build-index.js"
        cmd = [node, str(script)] + (["--lazy"] if args.lazy else [])
        return subprocess.call(cmd)

    if args.cmd == "export-schema":
        print(f"wrote {export_json_schema(args.output)}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
