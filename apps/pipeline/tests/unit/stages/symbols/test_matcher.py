"""Tests for deterministic symbol template matching."""

from pathlib import Path

from atr_pipeline.services.pdf.rasterizer import render_page_png
from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_pipeline.stages.symbols.catalog_loader import load_symbol_catalog
from atr_pipeline.stages.symbols.matcher import match_symbols


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


FIXTURE_DIR = (
    _repo_root()
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
)


def test_match_finds_progress_icon(tmp_path: Path) -> None:
    """Template matching finds sym.progress on the walking skeleton page."""
    pdf_path = FIXTURE_DIR / "source" / "sample_page_01.pdf"
    catalog_path = FIXTURE_DIR / "catalogs" / "walking_skeleton.symbols.toml"

    # Extract native evidence
    native = extract_native_page(pdf_path, page_number=1, document_id="ws")

    # Rasterize
    png_bytes = render_page_png(pdf_path, 1, dpi=300)
    raster_path = tmp_path / "page.png"
    raster_path.write_bytes(png_bytes)

    # Load catalog and match
    catalog = load_symbol_catalog(catalog_path)
    result = match_symbols(
        native, raster_path, catalog, repo_root=_repo_root()
    )

    assert result.page_id == "p0001"
    assert len(result.matches) >= 1

    progress_matches = [m for m in result.matches if m.symbol_id == "sym.progress"]
    assert len(progress_matches) == 1
    match = progress_matches[0]
    assert match.score >= 0.70
    assert match.inline is True
    assert match.bbox.x0 > 0
    assert match.bbox.y0 > 0


def test_catalog_loader() -> None:
    """Symbol catalog loads from TOML correctly."""
    catalog_path = FIXTURE_DIR / "catalogs" / "walking_skeleton.symbols.toml"
    catalog = load_symbol_catalog(catalog_path)

    assert catalog.catalog_id == "walking_skeleton"
    assert len(catalog.symbols) == 1
    assert catalog.symbols[0].symbol_id == "sym.progress"
    assert catalog.symbols[0].label == "Progress"
