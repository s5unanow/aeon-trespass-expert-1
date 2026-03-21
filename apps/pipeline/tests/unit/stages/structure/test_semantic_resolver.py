"""Tests for semantic resolver — region-aware block enrichment."""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.semantic_resolver import (
    SemanticResolution,
    _assign_blocks_to_regions,
    _bbox_overlap,
    _build_region_edges,
    _build_resolved_blocks,
    _detect_captions,
    _promote_callouts,
    _resolve_tables,
    resolve_semantics,
)
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import AnchorEdgeKind, BlockType, RegionKind
from atr_schemas.evidence_primitives_v1 import EvidenceTableCandidate
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    ParagraphBlock,
    TableBlock,
    TextInline,
)
from atr_schemas.resolved_page_v1 import ResolvedRegion

_DIMS = PageDimensions(width=612.0, height=792.0)


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _norm(rect: Rect) -> NormRect:
    return NormRect(
        x0=max(0.0, min(1.0, rect.x0 / _DIMS.width)),
        y0=max(0.0, min(1.0, rect.y0 / _DIMS.height)),
        x1=max(0.0, min(1.0, rect.x1 / _DIMS.width)),
        y1=max(0.0, min(1.0, rect.y1 / _DIMS.height)),
    )


def _region(
    rid: str,
    kind: RegionKind,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> ResolvedRegion:
    bbox = _rect(x0, y0, x1, y1)
    return ResolvedRegion(
        region_id=rid,
        kind=kind,
        bbox=bbox,
        norm_bbox=_norm(bbox),
    )


def _para(
    bid: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    text: str = "Sample text",
) -> ParagraphBlock:
    return ParagraphBlock(
        block_id=bid,
        bbox=_rect(x0, y0, x1, y1),
        children=[TextInline(text=text)],
    )


def _figure(bid: str, x0: float, y0: float, x1: float, y1: float) -> FigureBlock:
    return FigureBlock(
        block_id=bid,
        bbox=_rect(x0, y0, x1, y1),
        asset_id="asset_001",
    )


def _heading(bid: str, x0: float, y0: float, x1: float, y1: float) -> HeadingBlock:
    return HeadingBlock(
        block_id=bid,
        bbox=_rect(x0, y0, x1, y1),
        level=1,
        children=[TextInline(text="Heading")],
    )


def _evidence(entities: list[object] | None = None) -> PageEvidenceV1:
    return PageEvidenceV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
        entities=entities or [],  # type: ignore[arg-type]
    )


def _table_candidate(
    eid: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    confidence: float = 0.9,
) -> EvidenceTableCandidate:
    bbox = _rect(x0, y0, x1, y1)
    return EvidenceTableCandidate(
        evidence_id=eid,
        bbox=bbox,
        norm_bbox=_norm(bbox),
        confidence=confidence,
    )


class TestAssignBlocksToRegions:
    def test_block_inside_region(self) -> None:
        blocks = [_para("b1", 50, 100, 300, 120)]
        regions = [_region("r001", RegionKind.BODY, 40, 90, 310, 130)]
        result = _assign_blocks_to_regions(blocks, regions)
        assert result == {"b1": "r001"}

    def test_block_outside_all_regions(self) -> None:
        blocks = [_para("b1", 50, 100, 300, 120)]
        regions = [_region("r001", RegionKind.BODY, 400, 400, 500, 500)]
        result = _assign_blocks_to_regions(blocks, regions)
        assert result == {}

    def test_block_at_boundary(self) -> None:
        blocks = [_para("b1", 100, 100, 200, 200)]
        # Center is (150, 150) — exactly at region boundary
        regions = [_region("r001", RegionKind.BODY, 100, 100, 200, 200)]
        result = _assign_blocks_to_regions(blocks, regions)
        assert result == {"b1": "r001"}

    def test_block_without_bbox(self) -> None:
        block = ParagraphBlock(block_id="b1", children=[TextInline(text="hi")])
        regions = [_region("r001", RegionKind.BODY, 0, 0, 600, 800)]
        result = _assign_blocks_to_regions([block], regions)
        assert result == {}

    def test_multiple_blocks_different_regions(self) -> None:
        blocks = [
            _para("b1", 50, 100, 200, 120),
            _para("b2", 350, 100, 500, 120),
        ]
        regions = [
            _region("r001", RegionKind.BODY, 40, 90, 210, 130),
            _region("r002", RegionKind.SIDEBAR, 340, 90, 510, 130),
        ]
        result = _assign_blocks_to_regions(blocks, regions)
        assert result == {"b1": "r001", "b2": "r002"}


class TestDetectCaptions:
    def test_caption_below_figure_within_threshold(self) -> None:
        fig = _figure("b1", 50, 100, 400, 300)
        para = _para("b2", 50, 310, 400, 325, text="Figure 1: Layout")
        cfg = StructureConfig(caption_proximity_pt=25.0)
        blocks, edges = _detect_captions([fig, para], {}, cfg)

        captions = [b for b in blocks if isinstance(b, CaptionBlock)]
        assert len(captions) == 1
        assert captions[0].figure_block_id == "b1"
        assert len(edges) == 1
        assert edges[0].edge_kind == AnchorEdgeKind.CAPTION_TO_FIGURE

    def test_caption_beyond_threshold(self) -> None:
        fig = _figure("b1", 50, 100, 400, 300)
        para = _para("b2", 50, 350, 400, 365, text="Too far away")
        cfg = StructureConfig(caption_proximity_pt=25.0)
        blocks, edges = _detect_captions([fig, para], {}, cfg)

        captions = [b for b in blocks if isinstance(b, CaptionBlock)]
        assert len(captions) == 0
        assert len(edges) == 0

    def test_exclusivity_nearest_figure_wins(self) -> None:
        fig1 = _figure("b1", 50, 100, 400, 200)
        fig2 = _figure("b2", 50, 250, 400, 300)
        para = _para("b3", 50, 310, 400, 325, text="Caption text")
        cfg = StructureConfig(caption_proximity_pt=25.0)
        blocks, _edges = _detect_captions([fig1, fig2, para], {}, cfg)

        captions = [b for b in blocks if isinstance(b, CaptionBlock)]
        assert len(captions) == 1
        assert captions[0].figure_block_id == "b2"

    def test_text_length_limit(self) -> None:
        fig = _figure("b1", 50, 100, 400, 300)
        long_text = "A" * 250
        para = _para("b2", 50, 310, 400, 325, text=long_text)
        cfg = StructureConfig(caption_proximity_pt=25.0, caption_max_text_length=200)
        blocks, _edges = _detect_captions([fig, para], {}, cfg)
        captions = [b for b in blocks if isinstance(b, CaptionBlock)]
        assert len(captions) == 0

    def test_no_figures(self) -> None:
        para = _para("b1", 50, 100, 400, 120)
        cfg = StructureConfig()
        blocks, edges = _detect_captions([para], {}, cfg)
        assert blocks == [para]
        assert edges == []

    def test_caption_above_figure_ignored(self) -> None:
        para = _para("b1", 50, 80, 400, 95, text="Above figure")
        fig = _figure("b2", 50, 100, 400, 300)
        cfg = StructureConfig(caption_proximity_pt=25.0)
        blocks, _edges = _detect_captions([para, fig], {}, cfg)

        captions = [b for b in blocks if isinstance(b, CaptionBlock)]
        assert len(captions) == 0


class TestPromoteCallouts:
    def test_blocks_in_callout_area_wrapped(self) -> None:
        para = _para("b1", 50, 100, 200, 120)
        regions = [_region("r001", RegionKind.CALLOUT_AREA, 40, 90, 210, 130)]
        region_map = {"b1": "r001"}

        blocks, edges = _promote_callouts([para], region_map, regions)
        callouts = [b for b in blocks if isinstance(b, CalloutBlock)]
        assert len(callouts) == 1
        assert callouts[0].region_id == "r001"
        assert len(edges) == 1
        assert edges[0].edge_kind == AnchorEdgeKind.BLOCK_TO_CALLOUT

    def test_body_blocks_untouched(self) -> None:
        para = _para("b1", 50, 100, 200, 120)
        regions = [_region("r001", RegionKind.BODY, 40, 90, 210, 130)]
        region_map = {"b1": "r001"}

        blocks, edges = _promote_callouts([para], region_map, regions)
        assert len(blocks) == 1
        assert isinstance(blocks[0], ParagraphBlock)
        assert edges == []

    def test_multi_block_callout_merge(self) -> None:
        p1 = _para("b1", 50, 100, 200, 120)
        p2 = _para("b2", 50, 125, 200, 145)
        regions = [_region("r001", RegionKind.CALLOUT_AREA, 40, 90, 210, 150)]
        region_map = {"b1": "r001", "b2": "r001"}

        blocks, _edges = _promote_callouts([p1, p2], region_map, regions)
        callouts = [b for b in blocks if isinstance(b, CalloutBlock)]
        assert len(callouts) == 1
        # Should have children from both paragraphs
        assert len(callouts[0].children) == 2

    def test_no_callout_regions(self) -> None:
        para = _para("b1", 50, 100, 200, 120)
        regions = [_region("r001", RegionKind.BODY, 40, 90, 210, 130)]
        blocks, edges = _promote_callouts([para], {"b1": "r001"}, regions)
        assert blocks == [para]
        assert edges == []


class TestResolveTables:
    def test_table_area_with_evidence_promotes(self) -> None:
        para = _para("b1", 50, 100, 400, 200)
        tc = _table_candidate("e.tbl.001", 45, 95, 405, 205, confidence=0.9)
        ev = _evidence([tc])
        cfg = StructureConfig(table_min_confidence=0.6)

        blocks, edges = _resolve_tables([para], {}, ev, cfg)
        tables = [b for b in blocks if isinstance(b, TableBlock)]
        assert len(tables) == 1
        assert tables[0].block_id == "b1"
        assert len(edges) == 1

    def test_without_evidence_unchanged(self) -> None:
        para = _para("b1", 50, 100, 400, 200)
        cfg = StructureConfig()
        blocks, edges = _resolve_tables([para], {}, None, cfg)
        assert blocks == [para]
        assert edges == []

    def test_low_confidence_skipped(self) -> None:
        para = _para("b1", 50, 100, 400, 200)
        tc = _table_candidate("e.tbl.001", 45, 95, 405, 205, confidence=0.3)
        ev = _evidence([tc])
        cfg = StructureConfig(table_min_confidence=0.6)

        blocks, _edges = _resolve_tables([para], {}, ev, cfg)
        tables = [b for b in blocks if isinstance(b, TableBlock)]
        assert len(tables) == 0

    def test_no_overlap_unchanged(self) -> None:
        para = _para("b1", 50, 100, 200, 150)
        tc = _table_candidate("e.tbl.001", 400, 400, 600, 600, confidence=0.9)
        ev = _evidence([tc])
        cfg = StructureConfig(table_min_confidence=0.6)

        blocks, _edges = _resolve_tables([para], {}, ev, cfg)
        assert all(isinstance(b, ParagraphBlock) for b in blocks)


class TestBboxOverlap:
    def test_full_overlap(self) -> None:
        a = _rect(0, 0, 100, 100)
        b = _rect(0, 0, 100, 100)
        assert _bbox_overlap(a, b) == 1.0

    def test_no_overlap(self) -> None:
        a = _rect(0, 0, 50, 50)
        b = _rect(100, 100, 200, 200)
        assert _bbox_overlap(a, b) == 0.0

    def test_partial_overlap(self) -> None:
        a = _rect(0, 0, 100, 100)
        b = _rect(50, 50, 150, 150)
        overlap = _bbox_overlap(a, b)
        assert 0.0 < overlap < 1.0


class TestBuildAnchorEdges:
    def test_correct_edge_kinds(self) -> None:
        blocks = [_para("b1", 50, 100, 200, 120)]
        region_map = {"b1": "r001"}
        edges = _build_region_edges(blocks, region_map)
        assert len(edges) == 1
        assert edges[0].edge_kind == AnchorEdgeKind.BLOCK_TO_REGION
        assert edges[0].source_id == "b1"
        assert edges[0].target_id == "r001"

    def test_unmapped_blocks_no_edges(self) -> None:
        blocks = [_para("b1", 50, 100, 200, 120)]
        edges = _build_region_edges(blocks, {})
        assert edges == []


class TestBuildResolvedBlocks:
    def test_resolved_block_types(self) -> None:
        blocks = [
            _para("b1", 50, 100, 200, 120),
            _figure("b2", 50, 200, 400, 400),
            _heading("b3", 50, 50, 400, 70),
        ]
        region_map = {"b1": "r001", "b2": "r002"}
        resolved = _build_resolved_blocks(blocks, region_map)
        assert len(resolved) == 3
        assert resolved[0].block_type == BlockType.PARAGRAPH
        assert resolved[0].region_id == "r001"
        assert resolved[1].block_type == BlockType.FIGURE
        assert resolved[1].region_id == "r002"
        assert resolved[2].block_type == BlockType.HEADING
        assert resolved[2].region_id == ""


class TestResolveSemanticsIntegration:
    def test_end_to_end(self) -> None:
        fig = _figure("b1", 50, 100, 400, 300)
        caption_para = _para("b2", 50, 310, 400, 325, text="Figure 1")
        body_para = _para("b3", 50, 400, 400, 420, text="Body text")
        callout_para = _para("b4", 450, 100, 580, 120, text="Note text")

        regions = [
            _region("r001", RegionKind.BODY, 40, 90, 410, 430),
            _region("r002", RegionKind.CALLOUT_AREA, 440, 90, 590, 130),
        ]

        cfg = StructureConfig(caption_proximity_pt=25.0)
        result = resolve_semantics(
            [fig, caption_para, body_para, callout_para],
            regions,
            None,
            cfg,
        )

        assert isinstance(result, SemanticResolution)
        assert len(result.blocks) == 4

        # Caption detected
        captions = [b for b in result.blocks if isinstance(b, CaptionBlock)]
        assert len(captions) == 1
        assert captions[0].figure_block_id == "b1"

        # Callout promoted
        callouts = [b for b in result.blocks if isinstance(b, CalloutBlock)]
        assert len(callouts) == 1
        assert callouts[0].region_id == "r002"

        # Anchor edges present
        edge_kinds = {e.edge_kind for e in result.anchor_edges}
        assert AnchorEdgeKind.CAPTION_TO_FIGURE in edge_kinds
        assert AnchorEdgeKind.BLOCK_TO_CALLOUT in edge_kinds
        assert AnchorEdgeKind.BLOCK_TO_REGION in edge_kinds

        # Resolved blocks
        assert len(result.resolved_blocks) == 4
        assert 0.5 <= result.block_classification_confidence <= 1.0

    def test_empty_blocks(self) -> None:
        result = resolve_semantics([], [], None, StructureConfig())
        assert result.blocks == []
        assert result.anchor_edges == []
        assert result.resolved_blocks == []

    def test_with_table_evidence(self) -> None:
        para = _para("b1", 50, 100, 400, 200, text="Row data")
        regions = [_region("r001", RegionKind.TABLE_AREA, 40, 90, 410, 210)]
        tc = _table_candidate("e.tbl.001", 45, 95, 405, 205, confidence=0.9)
        ev = _evidence([tc])
        cfg = StructureConfig(table_min_confidence=0.6)

        result = resolve_semantics([para], regions, ev, cfg)
        tables = [b for b in result.blocks if isinstance(b, TableBlock)]
        assert len(tables) == 1
