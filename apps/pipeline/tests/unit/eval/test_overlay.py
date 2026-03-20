"""Tests for visual overlay generation."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from atr_pipeline.eval.overlay import draw_ir_overlay
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1, ParagraphBlock


def _create_test_raster(path: Path, width: int = 200, height: int = 300) -> Path:
    """Create a minimal test PNG raster."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    return path


def test_draw_ir_overlay_produces_valid_png(tmp_path: Path) -> None:
    """draw_ir_overlay returns valid PNG bytes."""
    raster = _create_test_raster(tmp_path / "test.png")
    ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language="en",
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        blocks=[
            HeadingBlock(
                block_id="p0001.b001",
                bbox=Rect(x0=50.0, y0=700.0, x1=300.0, y1=750.0),
            ),
            ParagraphBlock(
                block_id="p0001.b002",
                bbox=Rect(x0=50.0, y0=600.0, x1=300.0, y1=690.0),
            ),
        ],
    )

    png_bytes = draw_ir_overlay(raster, ir)

    assert len(png_bytes) > 100
    # Verify it's a valid PNG by reading it back
    import io

    img = Image.open(io.BytesIO(png_bytes))
    assert img.format == "PNG"
    assert img.size == (200, 300)


def test_draw_ir_overlay_skips_null_bbox(tmp_path: Path) -> None:
    """Blocks with bbox=None are gracefully skipped."""
    raster = _create_test_raster(tmp_path / "test.png")
    ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language="en",
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        blocks=[
            HeadingBlock(block_id="p0001.b001", bbox=None),
        ],
    )

    png_bytes = draw_ir_overlay(raster, ir)
    assert len(png_bytes) > 100


def test_draw_ir_overlay_no_dimensions(tmp_path: Path) -> None:
    """Page IR without dimensions returns the raster as-is."""
    raster = _create_test_raster(tmp_path / "test.png")
    ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language="en",
        dimensions_pt=None,
        blocks=[HeadingBlock(block_id="p0001.b001")],
    )

    png_bytes = draw_ir_overlay(raster, ir)
    assert len(png_bytes) > 100
