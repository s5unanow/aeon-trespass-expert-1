"""Tests for ExtractLayoutStage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_layout.stage import ExtractLayoutResult, ExtractLayoutStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import StageScope
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence


def _write_native_page(store: ArtifactStore, doc_id: str, page_id: str) -> None:
    """Write a minimal NativePageV1 artifact."""
    native = NativePageV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=int(page_id[1:]),
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        spans=[
            SpanEvidence(
                span_id="s1",
                text="Test",
                bbox=Rect(x0=50, y0=50, x1=200, y1=70),
            ),
        ],
    )
    store.put_json(
        document_id=doc_id,
        schema_family="native_page.v1",
        scope="page",
        entity_id=page_id,
        data=native,
    )


def _make_ctx(tmp_path: Path, doc_id: str = "test_doc") -> MagicMock:
    """Create a mock StageContext."""
    store = ArtifactStore(tmp_path / "artifacts")
    ctx = MagicMock()
    ctx.artifact_store = store
    ctx.document_id = doc_id
    ctx.logger = MagicMock()
    return ctx


def test_stage_implements_protocol() -> None:
    """ExtractLayoutStage satisfies the Stage protocol."""
    stage = ExtractLayoutStage()
    assert isinstance(stage, Stage)
    assert stage.name == "extract_layout"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_stage_produces_layout_artifacts(tmp_path: Path) -> None:
    """Stage produces LayoutPageV1 artifacts for each native page."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")
    _write_native_page(ctx.artifact_store, "test_doc", "p0002")

    stage = ExtractLayoutStage()
    result = stage.run(ctx, None)

    assert isinstance(result, ExtractLayoutResult)
    assert result.document_id == "test_doc"
    assert result.pages_processed == 2
    assert result.total_zones > 0

    # Verify artifacts were stored
    layout_dir = ctx.artifact_store.root / "test_doc" / "layout_page.v1" / "page"
    assert (layout_dir / "p0001").exists()
    assert (layout_dir / "p0002").exists()


def test_stage_extracts_zones_from_native(tmp_path: Path) -> None:
    """Layout extraction produces zones from native page data."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    stage = ExtractLayoutStage()
    stage.run(ctx, None)

    # Read back the stored artifact
    layout_dir = ctx.artifact_store.root / "test_doc" / "layout_page.v1" / "page" / "p0001"
    jsons = sorted(layout_dir.glob("*.json"))
    assert len(jsons) == 1
    data = json.loads(jsons[0].read_text())
    assert data["page_id"] == "p0001"
    assert len(data["zones"]) >= 1
    assert data["zones"][0]["kind"] == "body"


def test_stage_populates_difficulty(tmp_path: Path) -> None:
    """Layout extraction populates difficulty metadata."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    stage = ExtractLayoutStage()
    stage.run(ctx, None)

    layout_dir = ctx.artifact_store.root / "test_doc" / "layout_page.v1" / "page" / "p0001"
    data = json.loads(sorted(layout_dir.glob("*.json"))[-1].read_text())
    assert data["difficulty"] is not None
    assert data["difficulty"]["page_id"] == "p0001"
    assert data["difficulty"]["recommended_route"] == "R1"


def test_stage_skips_missing_pages(tmp_path: Path) -> None:
    """Stage warns and skips pages with missing native artifacts."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    # Create a page dir without any JSON
    empty_dir = ctx.artifact_store.root / "test_doc" / "native_page.v1" / "page" / "p0002"
    empty_dir.mkdir(parents=True)

    stage = ExtractLayoutStage()
    result = stage.run(ctx, None)

    assert result.pages_processed == 1
    ctx.logger.warning.assert_called()


def test_stage_raises_without_native_pages(tmp_path: Path) -> None:
    """Stage raises RuntimeError when no native pages exist."""
    ctx = _make_ctx(tmp_path)
    stage = ExtractLayoutStage()

    with pytest.raises(RuntimeError, match="No native pages found"):
        stage.run(ctx, None)


def test_stage_falls_back_on_primary_failure(tmp_path: Path) -> None:
    """When primary extractor raises, the OCR fallback is used."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    with patch(
        "atr_pipeline.stages.extract_layout.stage.extract_layout_stub",
        side_effect=RuntimeError("docling failed"),
    ):
        stage = ExtractLayoutStage()
        result = stage.run(ctx, None)

    assert result.pages_processed == 1
    # Fallback produces no zones
    assert result.total_zones == 0
    ctx.logger.warning.assert_called()
