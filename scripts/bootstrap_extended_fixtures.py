#!/usr/bin/env python3
"""Generate extended golden fixture PDFs added in S5U-590.

Layout classes generated here (complement scripts/bootstrap_golden_fixtures.py):
- vector_heavy:     page dense with vector drawing primitives (non-raster figure)
- chapter_opener:   full-width-interrupt / chapter-opener page
- confidence_bands: 3-page PDF exercising primary / qa_required / publish_blocking
                    confidence bands (hard_route band covered by hard_route fixture)

The PDFs here are simple stand-ins — the confidence values themselves live in
the expected/ page IR JSON sidecars, so page_confidence classification is
driven by the fixture goldens rather than by re-running extraction.
"""

import math
from pathlib import Path

import fitz  # PyMuPDF

FIXTURES_ROOT = (
    Path(__file__).resolve().parent.parent / "packages" / "fixtures" / "sample_documents"
)

A4_W, A4_H = 595.2, 841.8
HELV = fitz.Font("helv")


def _ensure_dirs(doc_id: str) -> Path:
    """Create fixture subdirectories and return the source dir."""
    base = FIXTURES_ROOT / doc_id
    for sub in ("source", "expected", "catalogs", "patches/source", "patches/target"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    for d in ("patches/source", "patches/target"):
        gk = base / d / ".gitkeep"
        if not gk.exists():
            gk.touch()
    return base / "source"


def create_vector_heavy(src: Path) -> None:
    """Page dense with vector drawing primitives (no raster figure).

    Represents a diagram-heavy layout where the figure is built out of many
    lines / polygons / curves instead of an embedded raster image. This
    stresses region detection on non-raster figure content.
    """
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    page.insert_text(fitz.Point(58, 70), "Vector Anatomy", fontsize=18, fontname="helv")
    page.insert_text(
        fitz.Point(58, 100),
        "The diagram is drawn entirely from vector primitives.",
        fontsize=10,
        fontname="helv",
    )
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(80, 130, 520, 520))
    cx, cy = 300, 325
    for angle_step in range(0, 360, 15):
        rad = math.radians(angle_step)
        ex = cx + int(180 * math.cos(rad))
        ey = cy + int(150 * math.sin(rad))
        shape.draw_line(fitz.Point(cx, cy), fitz.Point(ex, ey))
    for radius in (40, 80, 120, 160):
        pts: list[fitz.Point] = []
        for k in range(8):
            rad = math.radians(k * 45)
            pts.append(
                fitz.Point(cx + int(radius * math.cos(rad)), cy + int(radius * math.sin(rad)))
            )
        pts.append(pts[0])
        for i in range(len(pts) - 1):
            shape.draw_line(pts[i], pts[i + 1])
    shape.finish(color=(0.2, 0.2, 0.2), width=0.5)
    shape.commit()
    page.insert_text(
        fitz.Point(80, 545),
        "Figure 1: Exploded vector schematic of the Titan core.",
        fontsize=9,
        fontname="helv",
        color=(0.3, 0.3, 0.3),
    )
    doc.save(str(src / "vector_heavy.pdf"))
    doc.close()


def create_chapter_opener(src: Path) -> None:
    """Full-width chapter-opener page.

    A full-width banner heading interrupts the usual column grid, followed
    by a full-width lead paragraph and a second body paragraph.
    """
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(40, 90, A4_W - 40, 180))
    shape.finish(fill=(0.12, 0.12, 0.28), color=(0.12, 0.12, 0.28), width=0)
    shape.commit()
    page.insert_text(
        fitz.Point(60, 145),
        "Chapter 3 — The Mist Wars",
        fontsize=28,
        fontname="helv",
        color=(0.95, 0.95, 0.95),
    )
    page.draw_line(
        fitz.Point(40, 200),
        fitz.Point(A4_W - 40, 200),
        color=(0.6, 0.15, 0.15),
        width=1.5,
    )
    tw = fitz.TextWriter(page.rect)
    tw.fill_textbox(
        fitz.Rect(60, 220, A4_W - 60, 300),
        "Long before the Titans fell, the mists curled across the high passes "
        "and concealed both prey and predator alike. This chapter recounts "
        "the earliest skirmishes of that era.",
        fontsize=12,
        font=HELV,
    )
    tw.write_text(page)
    tw2 = fitz.TextWriter(page.rect)
    tw2.fill_textbox(
        fitz.Rect(60, 320, A4_W - 60, 400),
        "The first recorded clash took place at the edge of the Shattered "
        "Reach, where vanguard scouts engaged a lone Titan in a narrow gorge.",
        fontsize=10,
        font=HELV,
    )
    tw2.write_text(page)
    doc.save(str(src / "chapter_opener.pdf"))
    doc.close()


def create_confidence_bands(src: Path) -> None:
    """3-page PDF — structurally trivial content per page.

    Each page is a heading + paragraph. The per-page confidence values that
    make this fixture exercise each band live in the expected/ goldens
    (page_ir.en.p0001.json has page_confidence=0.95, p0002=0.45, p0003=0.15).
    """
    doc = fitz.open()
    page_labels = [
        ("Clear Rule", "A clean, easily extracted rule with no ambiguity."),
        ("Messy Scan Region", "Portions of this page have degraded text quality."),
        ("Unreadable Page", "This page is severely degraded and should block publish."),
    ]
    for heading, body in page_labels:
        page = doc.new_page(width=A4_W, height=A4_H)
        page.insert_text(fitz.Point(58, 90), heading, fontsize=18, fontname="helv")
        tw = fitz.TextWriter(page.rect)
        tw.fill_textbox(
            fitz.Rect(58, 120, A4_W - 58, 200),
            body,
            fontsize=11,
            font=HELV,
        )
        tw.write_text(page)
    doc.save(str(src / "confidence_bands.pdf"))
    doc.close()


def main() -> None:
    fixtures = [
        ("vector_heavy", create_vector_heavy),
        ("chapter_opener", create_chapter_opener),
        ("confidence_bands", create_confidence_bands),
    ]
    for name, builder in fixtures:
        src = _ensure_dirs(name)
        builder(src)
        print(f"  generated {name}")
    print("Done — extended golden fixtures generated.")


if __name__ == "__main__":
    main()
