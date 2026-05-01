"""S5U-589 — semantic resolver attaches FallbackProvenance on non-primary paths.

The structure stage threads ``LayoutPageV1.extraction_path`` into
``resolve_semantics`` so resolved blocks emitted for hard-page recovery
runs carry a populated ``ResolvedBlock.fallback`` field. Audit reporting
counts those as ``fallback_route_pages`` — the metric that motivated
S5U-589 (the audit was reporting 24 hard pages and 0 fallback-route
pages before this change).

These tests pin the contract that ``extraction_path != "primary"`` must
populate ``fallback`` on every emitted resolved block, and that the
``"primary"`` path leaves ``fallback`` as ``None`` so audit counts stay
honest.
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.semantic_resolver import resolve_semantics
from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.page_ir_v1 import ParagraphBlock, TextInline
from atr_schemas.resolved_page_v1 import ResolvedRegion


def _para(bid: str, text: str = "Text") -> ParagraphBlock:
    return ParagraphBlock(
        block_id=bid,
        bbox=Rect(x0=10, y0=10, x1=200, y1=30),
        children=[TextInline(text=text)],
    )


def _region() -> ResolvedRegion:
    bbox = Rect(x0=0, y0=0, x1=612, y1=792)
    return ResolvedRegion(
        region_id="r001",
        kind=RegionKind.BODY,
        bbox=bbox,
        norm_bbox=NormRect(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
    )


def _resolve(extraction_path: str = "primary"):
    blocks = [_para("b001"), _para("b002")]
    regions = [_region()]
    return resolve_semantics(blocks, regions, None, StructureConfig(), None, extraction_path)


def test_primary_path_leaves_fallback_none() -> None:
    """Default 'primary' path must NOT stamp fallback (audit count stays honest)."""
    sem = _resolve("primary")
    assert sem.resolved_blocks
    for b in sem.resolved_blocks:
        assert b.fallback is None


def test_ocr_fallback_path_stamps_fallback_on_every_block() -> None:
    """'ocr_fallback' path stamps FallbackProvenance(strategy='ocr_fallback') on every block."""
    sem = _resolve("ocr_fallback")
    assert sem.resolved_blocks
    for b in sem.resolved_blocks:
        assert b.fallback is not None
        assert b.fallback.strategy == "ocr_fallback"
        # Reason is populated so the MISSING_FALLBACK_PROVENANCE invariant
        # (which warns on empty strategy) and reviewer eyeballing both
        # have a non-empty explanation.
        assert b.fallback.reason


def test_extraction_failed_path_stamps_fallback() -> None:
    """'extraction_failed' path stamps FallbackProvenance(strategy='extraction_failed')."""
    sem = _resolve("extraction_failed")
    assert sem.resolved_blocks
    for b in sem.resolved_blocks:
        assert b.fallback is not None
        assert b.fallback.strategy == "extraction_failed"


def test_unknown_path_stamps_generic_fallback() -> None:
    """Unknown extraction_path values still stamp fallback (no silent drop).

    The semantic resolver doesn't gate on a closed enum — any non-'primary'
    string is treated as a fallback marker so future label additions in
    ExtractLayoutStage propagate to audit counts without a paired
    semantic_resolver edit. The strategy carries the verbatim label so
    reviewers can attribute the route from the artifact alone.
    """
    sem = _resolve("custom_route_v2")
    for b in sem.resolved_blocks:
        assert b.fallback is not None
        assert b.fallback.strategy == "custom_route_v2"
