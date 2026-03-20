"""Visual overlay generator — draws bboxes on page rasters using Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from atr_schemas.common import Rect
from atr_schemas.evidence_primitives_v1 import EvidenceEntity
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.resolved_page_v1 import ResolvedPageV1

# Color palette for overlay layers
EVIDENCE_COLORS: dict[str, str] = {
    "char": "#3366FF80",
    "line": "#3366FF80",
    "text_span": "#3366FF80",
    "image_occurrence": "#33CC6680",
    "vector_path": "#9933CC80",
    "vector_cluster": "#9933CC80",
    "table_candidate": "#FF993380",
    "region_candidate": "#FF993380",
}
RESOLVED_REGION_COLOR = "#33CC6680"
RESOLVED_SYMBOL_COLOR = "#FF333380"
IR_BLOCK_COLOR = "#FF8C0080"
IR_BLOCK_OUTLINE = "#FF8C00"


def _pdf_to_pixel(
    bbox: Rect,
    page_height_pt: float,
    raster_width: int,
    raster_height: int,
    page_width_pt: float,
) -> tuple[float, float, float, float]:
    """Convert PDF-point bbox to pixel coordinates.

    PDF origin is bottom-left; image origin is top-left.
    """
    scale_x = raster_width / page_width_pt
    scale_y = raster_height / page_height_pt
    x0 = bbox.x0 * scale_x
    x1 = bbox.x1 * scale_x
    y0 = (page_height_pt - bbox.y1) * scale_y
    y1 = (page_height_pt - bbox.y0) * scale_y
    return x0, y0, x1, y1


def draw_evidence_overlay(
    raster_path: Path,
    evidence: PageEvidenceV1,
) -> bytes:
    """Draw evidence-layer bboxes on a raster and return PNG bytes."""
    img = Image.open(raster_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    dims = evidence.transform.page_dimensions_pt
    page_w, page_h = dims.width, dims.height

    for entity in evidence.entities:
        _draw_evidence_entity(draw, entity, page_h, img.width, img.height, page_w)

    composite = Image.alpha_composite(img, overlay)
    return _image_to_png_bytes(composite)


def _draw_evidence_entity(
    draw: ImageDraw.ImageDraw,
    entity: EvidenceEntity,
    page_h: float,
    raster_w: int,
    raster_h: int,
    page_w: float,
) -> None:
    """Draw a single evidence entity bbox."""
    kind = entity.kind
    color = EVIDENCE_COLORS.get(kind, "#88888880")
    bbox = entity.bbox
    coords = _pdf_to_pixel(bbox, page_h, raster_w, raster_h, page_w)
    draw.rectangle(coords, fill=color, outline=color[:7])


def draw_resolved_overlay(
    raster_path: Path,
    resolved: ResolvedPageV1,
    page_width_pt: float,
    page_height_pt: float,
) -> bytes:
    """Draw resolved-layer regions and symbol refs on a raster."""
    img = Image.open(raster_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for region in resolved.regions:
        coords = _pdf_to_pixel(region.bbox, page_height_pt, img.width, img.height, page_width_pt)
        draw.rectangle(coords, fill=RESOLVED_REGION_COLOR, outline="#33CC66")

    for sym_ref in resolved.symbol_refs:
        if sym_ref.bbox is None:
            continue
        coords = _pdf_to_pixel(sym_ref.bbox, page_height_pt, img.width, img.height, page_width_pt)
        draw.rectangle(coords, fill=RESOLVED_SYMBOL_COLOR, outline="#FF3333")

    composite = Image.alpha_composite(img, overlay)
    return _image_to_png_bytes(composite)


def draw_ir_overlay(
    raster_path: Path,
    page_ir: PageIRV1,
) -> bytes:
    """Draw IR-layer block bboxes with type labels on a raster."""
    if page_ir.dimensions_pt is None:
        img = Image.open(raster_path).convert("RGBA")
        return _image_to_png_bytes(img)

    img = Image.open(raster_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    page_w = page_ir.dimensions_pt.width
    page_h = page_ir.dimensions_pt.height

    try:
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12
        )
    except OSError:
        font = ImageFont.load_default()

    for block in page_ir.blocks:
        bbox = block.bbox
        if bbox is None:
            continue
        coords = _pdf_to_pixel(bbox, page_h, img.width, img.height, page_w)
        draw.rectangle(coords, fill=IR_BLOCK_COLOR, outline=IR_BLOCK_OUTLINE, width=2)
        block_type = block.type
        block_id = block.block_id
        label = f"{block_type}:{block_id}"
        draw.text((coords[0], coords[1] - 14), label, fill=IR_BLOCK_OUTLINE, font=font)

    composite = Image.alpha_composite(img, overlay)
    return _image_to_png_bytes(composite)


def _image_to_png_bytes(img: Image.Image) -> bytes:
    """Convert a Pillow image to PNG bytes."""
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
