"""Unit tests for PageRasterProvider."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atr_pipeline.services.pdf.raster_provider import (
    PageRasterProvider,
    _png_dimensions,
)
from atr_pipeline.store.artifact_store import ArtifactStore


def _make_fake_png(width: int = 100, height: int = 200) -> bytes:
    """Create minimal valid PNG bytes with given dimensions in the IHDR chunk."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    ihdr_crc = b"\x00\x00\x00\x00"  # dummy CRC
    ihdr_length = struct.pack(">I", len(ihdr_data))
    ihdr_chunk = ihdr_length + b"IHDR" + ihdr_data + ihdr_crc
    iend_chunk = struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    return signature + ihdr_chunk + iend_chunk


class TestPngDimensions:
    def test_extracts_width_height(self) -> None:
        data = _make_fake_png(640, 480)
        assert _png_dimensions(data) == (640, 480)

    def test_large_dimensions(self) -> None:
        data = _make_fake_png(4096, 3072)
        assert _png_dimensions(data) == (4096, 3072)

    def test_rejects_invalid_data(self) -> None:
        with pytest.raises(ValueError, match="Invalid PNG"):
            _png_dimensions(b"not a png")


class TestPageRasterProvider:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> ArtifactStore:
        return ArtifactStore(tmp_path / "artifacts")

    @pytest.fixture()
    def provider(self, store: ArtifactStore) -> PageRasterProvider:
        return PageRasterProvider(
            store=store,
            document_id="test_doc",
            pyramid_dpi=[150, 300],
        )

    def test_default_dpi_is_highest(self, provider: PageRasterProvider) -> None:
        assert provider.default_dpi == 300

    def test_pyramid_dpi_sorted(self) -> None:
        store = ArtifactStore(Path("/tmp/test"))
        p = PageRasterProvider(store=store, document_id="d", pyramid_dpi=[300, 72, 150])
        assert p.pyramid_dpi == [72, 150, 300]

    def test_default_pyramid_when_none(self) -> None:
        store = ArtifactStore(Path("/tmp/test"))
        p = PageRasterProvider(store=store, document_id="d")
        assert p.pyramid_dpi == [300]

    @patch("atr_pipeline.services.pdf.raster_provider.render_page_png")
    def test_render_page_stores_all_levels(
        self,
        mock_render: Any,
        provider: PageRasterProvider,
        store: ArtifactStore,
    ) -> None:
        fake_png = _make_fake_png(640, 480)
        mock_render.return_value = fake_png
        meta = provider.render_page(
            pdf_path=Path("/fake.pdf"),
            page_number=1,
            page_id="p0001",
            source_pdf_sha256="abc123",
        )

        assert meta.document_id == "test_doc"
        assert meta.page_id == "p0001"
        assert meta.page_number == 1
        assert meta.source_pdf_sha256 == "abc123"
        assert len(meta.levels) == 2
        assert meta.levels[0].dpi == 150
        assert meta.levels[1].dpi == 300
        assert meta.levels[0].width_px == 640
        assert meta.levels[0].height_px == 480

        # Verify rasters stored on disk
        for level in meta.levels:
            full_path = store.root / level.relative_path
            assert full_path.exists()

        # Verify metadata JSON stored
        meta_dir = store.root / "test_doc" / "raster_meta.v1" / "page" / "p0001"
        assert meta_dir.exists()
        jsons = list(meta_dir.glob("*.json"))
        assert len(jsons) == 1

    @patch("atr_pipeline.services.pdf.raster_provider.render_page_png")
    def test_get_raster_returns_path(
        self,
        mock_render: Any,
        provider: PageRasterProvider,
    ) -> None:
        fake_png = _make_fake_png()
        mock_render.return_value = fake_png
        provider.render_page(Path("/fake.pdf"), 1, "p0001")

        result = provider.get_raster("p0001")
        assert result is not None
        assert result.suffix == ".png"
        assert result.exists()

    @patch("atr_pipeline.services.pdf.raster_provider.render_page_png")
    def test_get_raster_specific_dpi(
        self,
        mock_render: Any,
        provider: PageRasterProvider,
    ) -> None:
        fake_png = _make_fake_png()
        mock_render.return_value = fake_png
        provider.render_page(Path("/fake.pdf"), 1, "p0001")

        result = provider.get_raster("p0001", dpi=150)
        assert result is not None
        assert "__150dpi" in str(result)

    def test_get_raster_missing_returns_none(self, provider: PageRasterProvider) -> None:
        assert provider.get_raster("p9999") is None

    @patch("atr_pipeline.services.pdf.raster_provider.render_page_png")
    def test_get_meta_returns_stored_meta(
        self,
        mock_render: Any,
        provider: PageRasterProvider,
    ) -> None:
        fake_png = _make_fake_png()
        mock_render.return_value = fake_png
        provider.render_page(Path("/fake.pdf"), 1, "p0001")

        meta = provider.get_meta("p0001")
        assert meta is not None
        assert meta.page_id == "p0001"
        assert len(meta.levels) == 2

    def test_get_meta_missing_returns_none(self, provider: PageRasterProvider) -> None:
        assert provider.get_meta("p9999") is None

    @patch("atr_pipeline.services.pdf.raster_provider.render_page_png")
    def test_legacy_fallback(
        self,
        mock_render: Any,
        store: ArtifactStore,
    ) -> None:
        """Provider falls back to legacy raster path when pyramid not found."""
        fake_png = _make_fake_png()

        # Simulate legacy raster (no DPI suffix)
        store.put_bytes(
            document_id="test_doc",
            schema_family="raster",
            scope="page",
            entity_id="p0001",
            data=fake_png,
            extension=".png",
        )

        provider = PageRasterProvider(store=store, document_id="test_doc", pyramid_dpi=[300])

        result = provider.get_raster("p0001")
        assert result is not None
        assert result.exists()
