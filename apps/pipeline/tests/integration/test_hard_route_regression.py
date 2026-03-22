"""S5U-285: Hard-route and fallback regression tests.

Proves that the difficulty scorer → extract_layout → structure routing
pipeline correctly classifies pages into R1 (primary) or R2 (hard) paths
and records provenance in PageIRV1 artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_layout.stage import ExtractLayoutStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence, WordEvidence
from atr_schemas.page_ir_v1 import PageIRV1


def _make_config(doc_id: str) -> DocumentBuildConfig:
    """Minimal config for route regression tests."""
    return DocumentBuildConfig(
        document=DocumentConfig(
            id=doc_id,
            source_pdf="dummy.pdf",
            structure_builder="simple",
        ),
    )


def _make_ctx(tmp_path: Path, doc_id: str) -> StageContext:
    """Create a real StageContext for integration testing."""
    config = _make_config(doc_id)
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="test_route_run",
        document_id=doc_id,
        pipeline_version="0.1.0",
        config_hash="route_test",
    )
    return StageContext(
        run_id="test_route_run",
        document_id=doc_id,
        config=config,
        artifact_store=store,
        registry_conn=conn,
    )


def _word(x0: float, y0: float, x1: float, y1: float) -> WordEvidence:
    return WordEvidence(word_id="w1", text="word", bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1))


def _span(x0: float, y0: float, x1: float, y1: float) -> SpanEvidence:
    return SpanEvidence(span_id="s1", text="word", bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1))


def _store_native(
    store: ArtifactStore,
    doc_id: str,
    page_id: str,
    words: list[WordEvidence],
    spans: list[SpanEvidence] | None = None,
) -> None:
    """Write a NativePageV1 to the artifact store."""
    native = NativePageV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=int(page_id[1:]),
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        words=words,
        spans=spans or [_span(50, 50, 200, 70)],
    )
    store.put_json(
        document_id=doc_id,
        schema_family="native_page.v1",
        scope="page",
        entity_id=page_id,
        data=native,
    )


def _read_page_ir(store: ArtifactStore, doc_id: str, page_id: str) -> dict[str, object]:
    """Read back the stored PageIRV1 artifact."""
    ir_dir = store.root / doc_id / "page_ir.v1.en" / "page" / page_id
    jsons = sorted(ir_dir.glob("*.json"))
    assert len(jsons) == 1, f"Expected 1 IR artifact for {page_id}, got {len(jsons)}"
    return json.loads(jsons[0].read_text())


def _read_layout(store: ArtifactStore, doc_id: str, page_id: str) -> dict[str, object]:
    """Read back the stored LayoutPageV1 artifact."""
    layout_dir = store.root / doc_id / "layout_page.v1" / "page" / page_id
    jsons = sorted(layout_dir.glob("*.json"))
    assert len(jsons) == 1, f"Expected 1 layout artifact for {page_id}, got {len(jsons)}"
    return json.loads(jsons[0].read_text())


# ---------------------------------------------------------------------------
# Test: normal single-column page stays on primary path (R1)
# ---------------------------------------------------------------------------


def test_normal_page_routes_to_r1(tmp_path: Path) -> None:
    """A normal single-column page with adequate text coverage routes to R1."""
    doc_id = "route_r1_test"
    ctx = _make_ctx(tmp_path, doc_id)

    # Generate words covering >30% of page area (612*792 = 484704 sq pt)
    # Each word: 510 wide x 12 tall = 6120 sq pt; 45 rows ~ 275400 sq pt ~ 57%
    words = [_word(50, y * 15 + 50, 560, y * 15 + 62) for y in range(45)]
    _store_native(ctx.artifact_store, doc_id, "p0001", words)

    # Run extract_layout → produces LayoutPageV1 with difficulty
    ExtractLayoutStage().run(ctx, None)

    # Verify layout difficulty: not hard, R1
    layout = _read_layout(ctx.artifact_store, doc_id, "p0001")
    diff = layout["difficulty"]
    assert diff is not None
    assert diff["hard_page"] is False
    assert diff["recommended_route"] == "R1"
    assert diff["column_count"] == 1
    assert diff["native_text_coverage"] >= 0.30

    # Run structure → produces PageIRV1 with provenance
    StructureStage().run(ctx, None)

    ir = _read_page_ir(ctx.artifact_store, doc_id, "p0001")

    # Assert route provenance
    prov = ir["provenance"]
    assert prov is not None
    assert prov["evidence_ids"] == ["route:R1"]
    assert prov["extractor"] == "structure"

    # Assert confidence metrics from difficulty scoring
    conf = ir["confidence"]
    assert conf is not None
    assert conf["native_text_coverage"] >= 0.30
    assert 0.0 < conf["page_confidence"] <= 1.0  # multi-signal scorer


# ---------------------------------------------------------------------------
# Test: low text coverage page routes to hard path (R2)
# ---------------------------------------------------------------------------


def test_low_coverage_page_routes_to_r2(tmp_path: Path) -> None:
    """A page with <30% text coverage is flagged hard and routes to R2."""
    doc_id = "route_r2_coverage"
    ctx = _make_ctx(tmp_path, doc_id)

    # Very few words — coverage << 30%
    words = [_word(50, 50, 100, 62)]
    _store_native(ctx.artifact_store, doc_id, "p0001", words)

    ExtractLayoutStage().run(ctx, None)

    layout = _read_layout(ctx.artifact_store, doc_id, "p0001")
    diff = layout["difficulty"]
    assert diff is not None
    assert diff["hard_page"] is True
    assert diff["recommended_route"] == "R2"
    assert diff["native_text_coverage"] < 0.30

    StructureStage().run(ctx, None)

    ir = _read_page_ir(ctx.artifact_store, doc_id, "p0001")

    prov = ir["provenance"]
    assert prov is not None
    assert prov["evidence_ids"] == ["route:R2"]

    conf = ir["confidence"]
    assert conf is not None
    assert conf["native_text_coverage"] < 0.30


# ---------------------------------------------------------------------------
# Test: multi-column page routes to hard path (R2)
# ---------------------------------------------------------------------------


def test_multicolumn_page_routes_to_r2(tmp_path: Path) -> None:
    """A two-column page is flagged hard and routes to R2."""
    doc_id = "route_r2_columns"
    ctx = _make_ctx(tmp_path, doc_id)

    # Two word clusters with a clear gap in the middle
    left = [_word(50, y * 15 + 50, 250, y * 15 + 62) for y in range(25)]
    right = [_word(350, y * 15 + 50, 560, y * 15 + 62) for y in range(25)]
    words = left + right
    _store_native(ctx.artifact_store, doc_id, "p0001", words)

    ExtractLayoutStage().run(ctx, None)

    layout = _read_layout(ctx.artifact_store, doc_id, "p0001")
    diff = layout["difficulty"]
    assert diff is not None
    assert diff["hard_page"] is True
    assert diff["recommended_route"] == "R2"
    assert diff["column_count"] == 2

    StructureStage().run(ctx, None)

    ir = _read_page_ir(ctx.artifact_store, doc_id, "p0001")

    prov = ir["provenance"]
    assert prov is not None
    assert prov["evidence_ids"] == ["route:R2"]


# ---------------------------------------------------------------------------
# Test: fallback extraction records default route when no difficulty data
# ---------------------------------------------------------------------------


def test_fallback_records_default_route(tmp_path: Path) -> None:
    """When primary extractor fails, fallback produces no difficulty;
    structure stage defaults to R1 with default confidence scores."""
    doc_id = "route_fallback"
    ctx = _make_ctx(tmp_path, doc_id)

    words = [_word(50, y * 15 + 50, 560, y * 15 + 62) for y in range(30)]
    _store_native(ctx.artifact_store, doc_id, "p0001", words)

    # Force primary extractor to fail so fallback is used
    with patch(
        "atr_pipeline.stages.extract_layout.stage.extract_layout_stub",
        side_effect=RuntimeError("docling unavailable"),
    ):
        ExtractLayoutStage().run(ctx, None)

    # Fallback produces empty layout with no difficulty
    layout = _read_layout(ctx.artifact_store, doc_id, "p0001")
    assert layout["difficulty"] is None
    assert layout["zones"] == []

    StructureStage().run(ctx, None)

    ir = _read_page_ir(ctx.artifact_store, doc_id, "p0001")

    # No difficulty → default R1 route
    prov = ir["provenance"]
    assert prov is not None
    assert prov["evidence_ids"] == ["route:R1"]

    # No difficulty → scorer uses defaults (text_coverage=1.0)
    conf = ir["confidence"]
    assert conf is not None
    assert conf["page_confidence"] == 1.0


# ---------------------------------------------------------------------------
# Test: hard page count is tracked in StructureResult
# ---------------------------------------------------------------------------


def test_structure_result_counts_hard_pages(tmp_path: Path) -> None:
    """StructureResult.hard_pages correctly counts hard-routed pages."""
    doc_id = "route_counting"
    ctx = _make_ctx(tmp_path, doc_id)

    # p0001: normal page (R1)
    normal_words = [_word(50, y * 15 + 50, 560, y * 15 + 62) for y in range(45)]
    _store_native(ctx.artifact_store, doc_id, "p0001", normal_words)

    # p0002: hard page — low coverage (R2)
    sparse_words = [_word(50, 50, 100, 62)]
    _store_native(ctx.artifact_store, doc_id, "p0002", sparse_words)

    # p0003: hard page — multi-column (R2)
    left = [_word(50, y * 15 + 50, 250, y * 15 + 62) for y in range(25)]
    right = [_word(350, y * 15 + 50, 560, y * 15 + 62) for y in range(25)]
    _store_native(ctx.artifact_store, doc_id, "p0003", left + right)

    ExtractLayoutStage().run(ctx, None)
    result = StructureStage().run(ctx, None)

    assert result.pages_built == 3
    assert result.hard_pages == 2

    # Verify each page got the correct route
    ir1 = _read_page_ir(ctx.artifact_store, doc_id, "p0001")
    ir2 = _read_page_ir(ctx.artifact_store, doc_id, "p0002")
    ir3 = _read_page_ir(ctx.artifact_store, doc_id, "p0003")

    assert ir1["provenance"]["evidence_ids"] == ["route:R1"]
    assert ir2["provenance"]["evidence_ids"] == ["route:R2"]
    assert ir3["provenance"]["evidence_ids"] == ["route:R2"]


# ---------------------------------------------------------------------------
# Test: route metadata survives artifact roundtrip
# ---------------------------------------------------------------------------


def test_route_provenance_roundtrip(tmp_path: Path) -> None:
    """Route provenance can be deserialized back into typed models."""
    doc_id = "route_roundtrip"
    ctx = _make_ctx(tmp_path, doc_id)

    words = [_word(50, 50, 100, 62)]  # sparse → R2
    _store_native(ctx.artifact_store, doc_id, "p0001", words)

    ExtractLayoutStage().run(ctx, None)
    StructureStage().run(ctx, None)

    ir_data = _read_page_ir(ctx.artifact_store, doc_id, "p0001")
    ir = PageIRV1.model_validate(ir_data)

    assert ir.provenance is not None
    assert ir.provenance.extractor == "structure"
    assert ir.provenance.version == "1.1"
    assert "route:R2" in ir.provenance.evidence_ids

    assert ir.confidence is not None
    assert ir.confidence.native_text_coverage < 0.30
