#!/usr/bin/env python3
"""Generate golden fixture PDFs for extraction evaluation.

Creates synthetic PDF documents for each layout class needed by the golden
evaluation set. Each fixture is deterministic and reproducible.

Layout classes generated:
- multi_column: two-column body page with heading
- icon_dense: page with many inline icons
- table_callout: page with table and callout blocks
- figure_caption: page with figure and caption
- hard_route: complex mixed-layout page
- furniture_repetition: 3-page PDF with consistent headers/footers
"""

from pathlib import Path

import fitz  # PyMuPDF

FIXTURES_ROOT = (
    Path(__file__).resolve().parent.parent / "packages" / "fixtures" / "sample_documents"
)

# A4 dimensions in points
A4_W, A4_H = 595.2, 841.8
HELV = fitz.Font("helv")


def _ensure_dirs(doc_id: str) -> Path:
    """Create fixture subdirectories and return the source dir."""
    base = FIXTURES_ROOT / doc_id
    for sub in ("source", "expected", "catalogs", "patches/source", "patches/target"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    # Add .gitkeep to empty patch dirs
    for d in ("patches/source", "patches/target"):
        gk = base / d / ".gitkeep"
        if not gk.exists():
            gk.touch()
    return base / "source"


def _icon_pixmap() -> fitz.Pixmap:
    """Create a 16x16 green circle icon pixmap."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16), 1)
    pix.clear_with(0)
    cx, cy, r = 8, 8, 6
    for y in range(16):
        for x in range(16):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                pix.set_pixel(x, y, (34, 139, 34, 255))
    return pix


def create_multi_column(src: Path) -> None:
    """Two-column body page with full-width heading."""
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    page.insert_text(fitz.Point(58, 70), "Combat Rules", fontsize=18, fontname="helv")
    col_w = 230
    left_x, right_x = 58, 320
    y = 110
    for i, (x, text) in enumerate(
        [
            (left_x, "When a Titan attacks, roll the combat dice and compare the result."),
            (left_x, "Critical hits deal double damage and ignore armor values."),
            (right_x, "Defense is calculated from base armor plus any active shield."),
            (right_x, "If damage exceeds threshold the target enters wounded state."),
        ]
    ):
        tw = fitz.TextWriter(page.rect)
        tw.fill_textbox(fitz.Rect(x, y, x + col_w, y + 60), text, fontsize=10, font=HELV)
        tw.write_text(page)
        if i == 1:
            y = 110
        else:
            y += 70
    doc.save(str(src / "multi_column.pdf"))
    doc.close()


def create_icon_dense(src: Path, icon_path: Path) -> None:
    """Page with 6 inline icons across 3 paragraphs."""
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    page.insert_text(fitz.Point(58, 70), "Action Costs", fontsize=18, fontname="helv")
    y = 100
    texts = [
        ("Gain 2 ", " and 1 ", " per round."),
        ("Spend 3 ", " to activate ", " ability."),
        ("Lose 1 ", " but recover 2 ", " at dawn."),
    ]
    for parts in texts:
        x = 58
        for j, part in enumerate(parts):
            page.insert_text(fitz.Point(x, y), part, fontsize=10, fontname="helv")
            x += int(fitz.get_text_length(part, fontname="helv", fontsize=10))
            if j < 2:
                page.insert_image(fitz.Rect(x, y - 12, x + 16, y + 4), filename=str(icon_path))
                x += 18
        y += 30
    doc.save(str(src / "icon_dense.pdf"))
    doc.close()


def create_table_callout(src: Path) -> None:
    """Page with a table and a callout block."""
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    page.insert_text(fitz.Point(58, 70), "Equipment Table", fontsize=18, fontname="helv")
    # Simple table via lines and text
    tx, ty = 58, 90
    cols = [0, 150, 300, 420]
    rows = [0, 25, 50, 75]
    headers = ["Item", "Weight", "Effect"]
    data = [["Iron Sword", "3", "+2 Attack"], ["Shield", "5", "+3 Defense"]]
    for r in rows:
        page.draw_line(fitz.Point(tx, ty + r), fitz.Point(tx + 420, ty + r))
    for c in cols:
        page.draw_line(fitz.Point(tx + c, ty), fitz.Point(tx + c, ty + 75))
    for i, h in enumerate(headers):
        page.insert_text(fitz.Point(tx + cols[i] + 5, ty + 18), h, fontsize=10, fontname="helv")
    for ri, row in enumerate(data):
        for ci, cell in enumerate(row):
            page.insert_text(
                fitz.Point(tx + cols[ci] + 5, ty + 18 + (ri + 1) * 25),
                cell,
                fontsize=10,
                fontname="helv",
            )
    # Callout box
    cy = 200
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(58, cy, 480, cy + 60))
    shape.finish(color=(0.6, 0.2, 0.2), width=2)
    shape.commit()
    page.insert_text(
        fitz.Point(68, cy + 20), "Important!", fontsize=12, fontname="helv", color=(0.6, 0.2, 0.2)
    )
    page.insert_text(
        fitz.Point(68, cy + 42),
        "Cursed items cannot be unequipped once worn.",
        fontsize=10,
        fontname="helv",
    )
    # Trailing paragraph
    page.insert_text(
        fitz.Point(58, 300), "See appendix for full item catalog.", fontsize=10, fontname="helv"
    )
    doc.save(str(src / "table_callout.pdf"))
    doc.close()


def create_figure_caption(src: Path) -> None:
    """Page with a figure and its caption."""
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    page.insert_text(fitz.Point(58, 70), "Titan Anatomy", fontsize=18, fontname="helv")
    page.insert_text(
        fitz.Point(58, 100),
        "The diagram below shows vulnerable regions.",
        fontsize=10,
        fontname="helv",
    )
    # Figure placeholder (gray rectangle)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(100, 130, 480, 380))
    shape.finish(fill=(0.85, 0.85, 0.85), color=(0.5, 0.5, 0.5), width=1)
    shape.commit()
    page.insert_text(
        fitz.Point(220, 265), "[Titan Diagram]", fontsize=14, fontname="helv", color=(0.5, 0.5, 0.5)
    )
    # Caption
    page.insert_text(
        fitz.Point(100, 400),
        "Figure 1: Titan weak points and armor zones.",
        fontsize=9,
        fontname="helv",
        color=(0.3, 0.3, 0.3),
    )
    doc.save(str(src / "figure_caption.pdf"))
    doc.close()


def create_hard_route(src: Path, icon_path: Path) -> None:
    """Complex page mixing columns, figure, callout, and icons."""
    doc = fitz.open()
    page = doc.new_page(width=A4_W, height=A4_H)
    page.insert_text(fitz.Point(58, 70), "Advanced Combat", fontsize=18, fontname="helv")
    # Left column paragraph
    tw = fitz.TextWriter(page.rect)
    tw.fill_textbox(
        fitz.Rect(58, 90, 280, 160),
        "Flanking grants advantage. Roll extra dice when attacking from behind.",
        fontsize=10,
        font=HELV,
    )
    tw.write_text(page)
    # Right column paragraph
    tw2 = fitz.TextWriter(page.rect)
    tw2.fill_textbox(
        fitz.Rect(310, 90, 530, 160),
        "Defensive stance reduces incoming damage by half rounded down.",
        fontsize=10,
        font=HELV,
    )
    tw2.write_text(page)
    # Inline icon in a paragraph
    page.insert_text(fitz.Point(58, 185), "Spend 1 ", fontsize=10, fontname="helv")
    page.insert_image(fitz.Rect(115, 173, 131, 189), filename=str(icon_path))
    page.insert_text(fitz.Point(135, 185), " to activate.", fontsize=10, fontname="helv")
    # Callout
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(58, 210, 530, 260))
    shape.finish(color=(0.6, 0.2, 0.2), width=2)
    shape.commit()
    page.insert_text(
        fitz.Point(68, 238),
        "Warning: Flanking provokes opportunity attacks from adjacent enemies.",
        fontsize=10,
        fontname="helv",
    )
    # Figure
    shape2 = page.new_shape()
    shape2.draw_rect(fitz.Rect(58, 280, 350, 430))
    shape2.finish(fill=(0.9, 0.9, 0.9), color=(0.5, 0.5, 0.5), width=1)
    shape2.commit()
    page.insert_text(
        fitz.Point(140, 365),
        "[Combat Diagram]",
        fontsize=12,
        fontname="helv",
        color=(0.5, 0.5, 0.5),
    )
    doc.save(str(src / "hard_route.pdf"))
    doc.close()


def create_furniture_repetition(src: Path) -> None:
    """3-page PDF with identical header/footer furniture on each page."""
    doc = fitz.open()
    bodies = [
        "The first encounter begins at dawn when the Titan emerges from the mist.",
        "During the second phase the terrain shifts and new hazards appear.",
        "The final confrontation requires all survivors to coordinate their assault.",
    ]
    for i, body in enumerate(bodies):
        page = doc.new_page(width=A4_W, height=A4_H)
        # Header (furniture — same on every page)
        page.insert_text(
            fitz.Point(58, 30),
            "Chapter 4 — Combat Rules",
            fontsize=9,
            fontname="helv",
            color=(0.4, 0.4, 0.4),
        )
        page.draw_line(fitz.Point(58, 35), fitz.Point(537, 35), color=(0.7, 0.7, 0.7))
        # Body
        page.insert_text(fitz.Point(58, 80), f"Section {i + 1}", fontsize=16, fontname="helv")
        tw = fitz.TextWriter(page.rect)
        tw.fill_textbox(fitz.Rect(58, 110, 537, 200), body, fontsize=10, font=HELV)
        tw.write_text(page)
        # Footer (furniture — same structure, page number varies)
        page.draw_line(fitz.Point(58, 805), fitz.Point(537, 805), color=(0.7, 0.7, 0.7))
        page.insert_text(
            fitz.Point(270, 820),
            f"— {i + 31} —",
            fontsize=9,
            fontname="helv",
            color=(0.4, 0.4, 0.4),
        )
    doc.save(str(src / "furniture_repetition.pdf"))
    doc.close()


def main() -> None:
    # Shared icon for icon-dependent fixtures
    icon_dir = FIXTURES_ROOT / "walking_skeleton" / "source"
    icon_path = icon_dir / "symbol_progress.png"
    if not icon_path.exists():
        pix = _icon_pixmap()
        pix.save(str(icon_path))

    fixtures = [
        ("multi_column", lambda s: create_multi_column(s)),
        ("icon_dense", lambda s: create_icon_dense(s, icon_path)),
        ("table_callout", lambda s: create_table_callout(s)),
        ("figure_caption", lambda s: create_figure_caption(s)),
        ("hard_route", lambda s: create_hard_route(s, icon_path)),
        ("furniture_repetition", lambda s: create_furniture_repetition(s)),
    ]
    for name, builder in fixtures:
        src = _ensure_dirs(name)
        builder(src)
        print(f"  generated {name}")

    # Copy icon to icon_dense and hard_route catalogs
    for doc_id in ("icon_dense", "hard_route"):
        dst = FIXTURES_ROOT / doc_id / "source" / "symbol_progress.png"
        if not dst.exists():
            dst.write_bytes(icon_path.read_bytes())

    print("Done — all golden fixtures generated.")


if __name__ == "__main__":
    main()
