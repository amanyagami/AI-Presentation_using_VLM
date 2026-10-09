"""Backward-compatible entry point; the implementation lives in ``slidegen.extract``.

Usage: ``python extract_images.py <pdf_or_dir> [proximity] [min_area] [caption_scan]``
"""

import sys
from pathlib import Path

try:
    from slidegen.extract import *  # noqa: F403
    from slidegen.extract import main
except ImportError:  # not installed: fall back to the in-repo source tree
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from slidegen.extract import *  # noqa: F403
    from slidegen.extract import main

if __name__ == "__main__":
    sys.exit(main())
