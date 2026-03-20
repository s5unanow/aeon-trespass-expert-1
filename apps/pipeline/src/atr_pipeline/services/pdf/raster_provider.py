"""PageRasterProvider — shared raster service with multi-DPI pyramid and provenance."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from atr_pipeline.services.pdf.rasterizer import render_page_png
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import sha256_bytes
from atr_schemas.raster_meta_v1 import RasterLevel, RasterMetaV1


class PageRasterProvider:
    """Render and retrieve per-page raster pyramids with provenance metadata.

    Replaces ad-hoc ``_find_raster()`` helpers scattered across stages.
    All rasters are content-addressed and stored via :class:`ArtifactStore`.
    """

    def __init__(
        self,
        store: ArtifactStore,
        document_id: str,
        pyramid_dpi: list[int] | None = None,
    ) -> None:
        self._store = store
        self._document_id = document_id
        self._pyramid_dpi = sorted(pyramid_dpi or [300])

    @property
    def default_dpi(self) -> int:
        """Highest DPI in the configured pyramid."""
        return self._pyramid_dpi[-1]

    @property
    def pyramid_dpi(self) -> list[int]:
        """Configured DPI levels (ascending)."""
        return list(self._pyramid_dpi)

    def render_page(
        self,
        pdf_path: Path,
        page_number: int,
        page_id: str,
        *,
        source_pdf_sha256: str = "",
    ) -> RasterMetaV1:
        """Render a page at all pyramid DPI levels, store results, return metadata."""
        levels: list[RasterLevel] = []

        for dpi in self._pyramid_dpi:
            png_bytes = render_page_png(pdf_path, page_number, dpi=dpi)
            entity_id = f"{page_id}__{dpi}dpi"
            stored_path = self._store.put_bytes(
                document_id=self._document_id,
                schema_family="raster",
                scope="page",
                entity_id=entity_id,
                data=png_bytes,
                extension=".png",
            )
            w, h = _png_dimensions(png_bytes)
            c_hash = sha256_bytes(png_bytes)[:12]
            rel_path = str(stored_path.relative_to(self._store.root))
            levels.append(
                RasterLevel(
                    dpi=dpi,
                    width_px=w,
                    height_px=h,
                    content_hash=c_hash,
                    relative_path=rel_path,
                )
            )

        meta = RasterMetaV1(
            document_id=self._document_id,
            page_id=page_id,
            page_number=page_number,
            source_pdf_sha256=source_pdf_sha256,
            levels=levels,
        )
        self._store.put_json(
            document_id=self._document_id,
            schema_family="raster_meta.v1",
            scope="page",
            entity_id=page_id,
            data=meta,
        )
        return meta

    def get_raster(self, page_id: str, dpi: int | None = None) -> Path | None:
        """Return the filesystem path for a page raster at the requested DPI.

        Falls back to the closest available DPI, then legacy (non-pyramid) path.
        """
        target_dpi = dpi or self.default_dpi
        path = self._lookup_raster(page_id, target_dpi)
        if path is not None:
            return path

        # Try other pyramid levels (closest first)
        for level_dpi in sorted(self._pyramid_dpi, key=lambda d: abs(d - target_dpi)):
            if level_dpi == target_dpi:
                continue
            path = self._lookup_raster(page_id, level_dpi)
            if path is not None:
                return path

        # Legacy fallback: raster stored without DPI suffix
        return self._find_legacy_raster(page_id)

    def get_meta(self, page_id: str) -> RasterMetaV1 | None:
        """Load raster provenance metadata for a page."""
        meta_dir = self._store.root / self._document_id / "raster_meta.v1" / "page" / page_id
        if not meta_dir.exists():
            return None
        jsons = sorted(meta_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return RasterMetaV1.model_validate(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_raster(self, page_id: str, dpi: int) -> Path | None:
        entity_id = f"{page_id}__{dpi}dpi"
        raster_dir = self._store.root / self._document_id / "raster" / "page" / entity_id
        if not raster_dir.exists():
            return None
        pngs = sorted(raster_dir.glob("*.png"))
        return pngs[-1] if pngs else None

    def _find_legacy_raster(self, page_id: str) -> Path | None:
        raster_dir = self._store.root / self._document_id / "raster" / "page" / page_id
        if not raster_dir.exists():
            return None
        pngs = sorted(raster_dir.glob("*.png"))
        return pngs[-1] if pngs else None


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Extract width and height from a PNG's IHDR chunk."""
    if len(data) < 24 or data[:8] != _PNG_SIGNATURE:
        msg = f"Invalid PNG data ({len(data)} bytes)"
        raise ValueError(msg)
    # PNG: 8-byte signature, then IHDR chunk (4B length + 4B type + 4B width + 4B height)
    width: int = struct.unpack(">I", data[16:20])[0]
    height: int = struct.unpack(">I", data[20:24])[0]
    return width, height
