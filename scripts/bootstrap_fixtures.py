#!/usr/bin/env python3
"""Generate the walking skeleton synthetic sample page and icon template.

Creates:
- sample_page_01.pdf — a single-page PDF with heading, paragraph text, and an inline icon image
- symbol_progress.png — the icon template image for sym.progress

The PDF contains:
  Heading: "Attack Test"
  Paragraph: "Gain 1 [icon] Progress."
  where [icon] is an embedded small PNG image inline in the text.
"""

from pathlib import Path

import fitz  # PyMuPDF

OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "source"
)


def create_icon_image(path: Path) -> None:
    """Create a simple 16x16 progress icon PNG (green circle on transparent bg)."""
    # Use PyMuPDF to create a simple pixmap
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16), 1)  # with alpha
    pix.clear_with(0)  # transparent

    # Draw a filled green circle manually via pixel setting
    cx, cy, r = 8, 8, 6
    for y in range(16):
        for x in range(16):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= r * r:
                pix.set_pixel(x, y, (34, 139, 34, 255))  # forest green
            else:
                pix.set_pixel(x, y, (0, 0, 0, 0))  # transparent

    pix.save(str(path))
    print(f"  wrote {path.name}")


def create_sample_pdf(pdf_path: Path, icon_path: Path) -> None:
    """Create a single-page PDF with heading, inline icon, and paragraph text."""
    doc = fitz.open()
    page = doc.new_page(width=595.2, height=841.8)  # A4

    # Heading — use insert_text for reliable extraction
    page.insert_text(
        fitz.Point(58, 90),
        "Attack Test",
        fontsize=18,
        fontname="helv",
        color=(0.1, 0.1, 0.1),
    )

    # Paragraph text before icon
    page.insert_text(
        fitz.Point(58, 122),
        "Gain 1 ",
        fontsize=11,
        fontname="helv",
        color=(0.15, 0.15, 0.15),
    )

    # Inline icon image
    icon_rect = fitz.Rect(108, 110, 124, 126)
    page.insert_image(icon_rect, filename=str(icon_path))

    # Paragraph text after icon
    page.insert_text(
        fitz.Point(128, 122),
        " Progress.",
        fontsize=11,
        fontname="helv",
        color=(0.15, 0.15, 0.15),
    )

    doc.save(str(pdf_path))
    doc.close()
    print(f"  wrote {pdf_path.name}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    icon_path = OUTPUT_DIR / "symbol_progress.png"
    create_icon_image(icon_path)

    pdf_path = OUTPUT_DIR / "sample_page_01.pdf"
    create_sample_pdf(pdf_path, icon_path)

    # Source notes
    notes_path = OUTPUT_DIR / "source_notes.md"
    notes_path.write_text(
        "# Walking Skeleton Source Notes\n\n"
        "This is a **synthetic** single-page PDF created by `scripts/bootstrap_fixtures.py`.\n\n"
        "Content:\n"
        '- Heading: "Attack Test"\n'
        '- Paragraph: "Gain 1 [sym.progress icon] Progress."\n\n'
        "The inline icon is a 16x16 green circle PNG embedded as a PDF image object.\n"
        "This page is intentionally simple: single column, one heading, one paragraph,\n"
        "one inline icon. It exists to prove the architecture end-to-end.\n",
        encoding="utf-8",
    )
    print(f"  wrote {notes_path.name}")


if __name__ == "__main__":
    main()
