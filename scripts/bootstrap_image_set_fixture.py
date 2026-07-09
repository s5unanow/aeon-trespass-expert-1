#!/usr/bin/env python3
"""Generate the tiny deterministic PNGs for the ``tiny_image_set`` fixture.

The image-set ingest tests (S5U-1536) need a small, committed image set with
no binary bloat. This script regenerates the PNGs deterministically so the
fixture can be refreshed without hand-editing binary files. PIL's PNG encoder
is deterministic given identical inputs (no timestamps by default), so re-running
this produces byte-identical files.

Usage:
    uv run python scripts/bootstrap_image_set_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = REPO_ROOT / "packages" / "fixtures" / "image_sets" / "tiny_image_set" / "images"

# (filename, size, solid RGB colour). Distinct colours → distinct sha256 per file.
_IMAGES: list[tuple[str, tuple[int, int], tuple[int, int, int]]] = [
    ("page_01_a.png", (16, 16), (200, 60, 60)),
    ("page_01_b.png", (16, 16), (60, 200, 60)),
    ("page_02_a.png", (16, 24), (60, 60, 200)),
]


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for name, size, colour in _IMAGES:
        img = Image.new("RGB", size, color=colour)
        out = IMAGES_DIR / name
        img.save(out, format="PNG", optimize=False)
        print(f"  wrote {out.relative_to(REPO_ROOT)} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
