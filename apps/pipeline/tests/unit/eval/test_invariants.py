"""Tests for extraction artifact invariant checks."""

from __future__ import annotations

from atr_pipeline.eval.invariants import (
    ANCHOR_CYCLE,
    BBOX_OUT_OF_PAGE,
    DANGLING_ANCHOR_REF,
    DANGLING_EVIDENCE_REF,
    DANGLING_FLOW_REF,
    DANGLING_REGION_REF,
    DUPLICATE_SYMBOL_INSTANCE,
    MISSING_FALLBACK_PROVENANCE,
    ORPHAN_CAPTION,
    run_invariant_checks,
)
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import AnchorEdgeKind, BlockType, RegionKind, SymbolAnchorKind
from atr_schemas.evidence_primitives_v1 import EvidenceChar
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
from atr_schemas.resolved_page_v1 import (
    AnchorEdge,
    FallbackProvenance,
    ResolvedBlock,
    ResolvedPageV1,
    ResolvedRegion,
    ResolvedSymbolRef,
)

_DIMS = PageDimensions(width=612.0, height=792.0)
_NORM = NormRect(x0=0.0, y0=0.0, x1=0.5, y1=0.5)
_BBOX = Rect(x0=0.0, y0=0.0, x1=100.0, y1=100.0)


def _make_resolved(
    *,
    regions: list[ResolvedRegion] | None = None,
    blocks: list[ResolvedBlock] | None = None,
    main_flow_order: list[str] | None = None,
    anchor_edges: list[AnchorEdge] | None = None,
    symbol_refs: list[ResolvedSymbolRef] | None = None,
) -> ResolvedPageV1:
    return ResolvedPageV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        regions=regions or [],
        blocks=blocks or [],
        main_flow_order=main_flow_order or [],
        anchor_edges=anchor_edges or [],
        symbol_refs=symbol_refs or [],
    )


def _make_evidence(
    *,
    entities: list[EvidenceChar] | None = None,
    dims: PageDimensions | None = None,
) -> PageEvidenceV1:
    return PageEvidenceV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=dims or _DIMS),
        entities=entities or [],
    )


def _char(eid: str, bbox: Rect | None = None) -> EvidenceChar:
    return EvidenceChar(
        evidence_id=eid,
        text="x",
        bbox=bbox or _BBOX,
        norm_bbox=_NORM,
    )


# --- Happy path ---


def test_valid_page_passes_all_checks() -> None:
    """A well-formed page with consistent refs produces no records."""
    region = ResolvedRegion(region_id="r001", kind=RegionKind.BODY, bbox=_BBOX, norm_bbox=_NORM)
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        region_id="r001",
        evidence_ids=["e.char.001"],
    )
    edge = AnchorEdge(
        edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
        source_id="p0001.b001",
        target_id="r001",
    )
    resolved = _make_resolved(
        regions=[region],
        blocks=[block],
        main_flow_order=["p0001.b001"],
        anchor_edges=[edge],
    )
    evidence = _make_evidence(entities=[_char("e.char.001")])

    records = run_invariant_checks(resolved, evidence)
    assert records == []


# --- Individual invariant failure tests ---


def test_dangling_region_ref() -> None:
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        region_id="r999",
    )
    resolved = _make_resolved(blocks=[block])
    records = run_invariant_checks(resolved)
    assert len(records) == 1
    assert records[0].code == DANGLING_REGION_REF
    assert records[0].entity_ref == "p0001.b001"


def test_dangling_region_ref_empty_is_ok() -> None:
    """Blocks with empty region_id should not trigger the check."""
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        region_id="",
    )
    resolved = _make_resolved(blocks=[block])
    records = run_invariant_checks(resolved)
    assert all(r.code != DANGLING_REGION_REF for r in records)


def test_dangling_flow_ref() -> None:
    resolved = _make_resolved(main_flow_order=["p0001.b999"])
    records = run_invariant_checks(resolved)
    assert len(records) == 1
    assert records[0].code == DANGLING_FLOW_REF
    assert records[0].entity_ref == "p0001.b999"


def test_dangling_anchor_ref() -> None:
    edge = AnchorEdge(
        edge_kind=AnchorEdgeKind.CAPTION_TO_FIGURE,
        source_id="p0001.b001",
        target_id="p0001.b999",
    )
    resolved = _make_resolved(anchor_edges=[edge])
    records = [r for r in run_invariant_checks(resolved) if r.code == DANGLING_ANCHOR_REF]
    assert len(records) == 2
    refs = {r.entity_ref for r in records}
    assert "p0001.b001" in refs
    assert "p0001.b999" in refs


def test_dangling_evidence_ref() -> None:
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        evidence_ids=["e.char.999"],
    )
    resolved = _make_resolved(blocks=[block])
    evidence = _make_evidence(entities=[_char("e.char.001")])

    records = run_invariant_checks(resolved, evidence)
    assert any(r.code == DANGLING_EVIDENCE_REF for r in records)
    dangling = [r for r in records if r.code == DANGLING_EVIDENCE_REF]
    assert dangling[0].entity_ref == "p0001.b001:e.char.999"


def test_dangling_evidence_ref_on_region() -> None:
    region = ResolvedRegion(
        region_id="r001",
        kind=RegionKind.BODY,
        bbox=_BBOX,
        norm_bbox=_NORM,
        evidence_ids=["e.char.999"],
    )
    resolved = _make_resolved(regions=[region])
    evidence = _make_evidence(entities=[_char("e.char.001")])

    records = run_invariant_checks(resolved, evidence)
    dangling = [r for r in records if r.code == DANGLING_EVIDENCE_REF]
    assert len(dangling) == 1
    assert dangling[0].entity_ref == "r001:e.char.999"


def test_bbox_out_of_page() -> None:
    out_bbox = Rect(x0=-10.0, y0=0.0, x1=100.0, y1=100.0)
    evidence = _make_evidence(entities=[_char("e.char.001", bbox=out_bbox)])
    resolved = _make_resolved()

    records = run_invariant_checks(resolved, evidence)
    assert any(r.code == BBOX_OUT_OF_PAGE for r in records)


def test_bbox_within_tolerance_is_ok() -> None:
    """Bbox slightly outside page (within tolerance) should pass."""
    slight_bbox = Rect(x0=-0.3, y0=0.0, x1=100.0, y1=100.0)
    evidence = _make_evidence(entities=[_char("e.char.001", bbox=slight_bbox)])
    resolved = _make_resolved()

    records = run_invariant_checks(resolved, evidence)
    assert all(r.code != BBOX_OUT_OF_PAGE for r in records)


def test_duplicate_symbol_instance() -> None:
    sym1 = ResolvedSymbolRef(
        symbol_id="sym_a", instance_id="inst_1", anchor_kind=SymbolAnchorKind.INLINE
    )
    sym2 = ResolvedSymbolRef(
        symbol_id="sym_b", instance_id="inst_1", anchor_kind=SymbolAnchorKind.INLINE
    )
    resolved = _make_resolved(symbol_refs=[sym1, sym2])

    records = run_invariant_checks(resolved)
    dups = [r for r in records if r.code == DUPLICATE_SYMBOL_INSTANCE]
    assert len(dups) == 1
    assert dups[0].entity_ref == "inst_1"


def test_duplicate_symbol_instance_empty_id_ignored() -> None:
    """Symbols with empty instance_id should not trigger duplicate check."""
    sym1 = ResolvedSymbolRef(symbol_id="sym_a", instance_id="", anchor_kind=SymbolAnchorKind.INLINE)
    sym2 = ResolvedSymbolRef(symbol_id="sym_b", instance_id="", anchor_kind=SymbolAnchorKind.INLINE)
    resolved = _make_resolved(symbol_refs=[sym1, sym2])

    records = run_invariant_checks(resolved)
    assert all(r.code != DUPLICATE_SYMBOL_INSTANCE for r in records)


def test_orphan_caption() -> None:
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.CAPTION,
    )
    resolved = _make_resolved(blocks=[block])

    records = run_invariant_checks(resolved)
    orphans = [r for r in records if r.code == ORPHAN_CAPTION]
    assert len(orphans) == 1
    assert orphans[0].entity_ref == "p0001.b001"


def test_caption_with_edge_is_ok() -> None:
    block = ResolvedBlock(block_id="p0001.b001", block_type=BlockType.CAPTION)
    fig = ResolvedBlock(block_id="p0001.b002", block_type=BlockType.FIGURE)
    edge = AnchorEdge(
        edge_kind=AnchorEdgeKind.CAPTION_TO_FIGURE,
        source_id="p0001.b001",
        target_id="p0001.b002",
    )
    resolved = _make_resolved(blocks=[block, fig], anchor_edges=[edge])

    records = run_invariant_checks(resolved)
    assert all(r.code != ORPHAN_CAPTION for r in records)


def test_anchor_cycle() -> None:
    region_a = ResolvedRegion(region_id="r001", kind=RegionKind.BODY, bbox=_BBOX, norm_bbox=_NORM)
    region_b = ResolvedRegion(
        region_id="r002", kind=RegionKind.SIDEBAR, bbox=_BBOX, norm_bbox=_NORM
    )
    edges = [
        AnchorEdge(edge_kind=AnchorEdgeKind.ASIDE_TO_MAIN, source_id="r001", target_id="r002"),
        AnchorEdge(edge_kind=AnchorEdgeKind.ASIDE_TO_MAIN, source_id="r002", target_id="r001"),
    ]
    resolved = _make_resolved(regions=[region_a, region_b], anchor_edges=edges)

    records = run_invariant_checks(resolved)
    cycles = [r for r in records if r.code == ANCHOR_CYCLE]
    assert len(cycles) == 1


def test_no_anchor_cycle_when_acyclic() -> None:
    region = ResolvedRegion(region_id="r001", kind=RegionKind.BODY, bbox=_BBOX, norm_bbox=_NORM)
    block = ResolvedBlock(block_id="p0001.b001", block_type=BlockType.PARAGRAPH, region_id="r001")
    edge = AnchorEdge(
        edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
        source_id="p0001.b001",
        target_id="r001",
    )
    resolved = _make_resolved(regions=[region], blocks=[block], anchor_edges=[edge])

    records = run_invariant_checks(resolved)
    assert all(r.code != ANCHOR_CYCLE for r in records)


def test_missing_fallback_provenance() -> None:
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        fallback=FallbackProvenance(strategy=""),
    )
    resolved = _make_resolved(blocks=[block])

    records = run_invariant_checks(resolved)
    fb = [r for r in records if r.code == MISSING_FALLBACK_PROVENANCE]
    assert len(fb) == 1
    assert fb[0].entity_ref == "p0001.b001"


def test_fallback_with_strategy_is_ok() -> None:
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        fallback=FallbackProvenance(strategy="ocr_fallback"),
    )
    resolved = _make_resolved(blocks=[block])

    records = run_invariant_checks(resolved)
    assert all(r.code != MISSING_FALLBACK_PROVENANCE for r in records)


# --- Edge cases ---


def test_empty_page_passes() -> None:
    """A page with no blocks, regions, or edges should pass."""
    resolved = _make_resolved()
    records = run_invariant_checks(resolved)
    assert records == []


def test_evidence_checks_skipped_without_evidence() -> None:
    """When no evidence is provided, evidence-dependent checks are skipped."""
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        evidence_ids=["e.char.999"],
    )
    resolved = _make_resolved(blocks=[block])

    records = run_invariant_checks(resolved, evidence=None)
    assert all(r.code != DANGLING_EVIDENCE_REF for r in records)
    assert all(r.code != BBOX_OUT_OF_PAGE for r in records)


def test_block_symbol_refs_checked_for_duplicates() -> None:
    """Symbol refs on blocks (not just page-level) are checked."""
    sym = ResolvedSymbolRef(
        symbol_id="sym_a", instance_id="inst_1", anchor_kind=SymbolAnchorKind.INLINE
    )
    block = ResolvedBlock(
        block_id="p0001.b001",
        block_type=BlockType.PARAGRAPH,
        symbol_refs=[sym],
    )
    resolved = _make_resolved(
        blocks=[block],
        symbol_refs=[
            ResolvedSymbolRef(
                symbol_id="sym_b",
                instance_id="inst_1",
                anchor_kind=SymbolAnchorKind.INLINE,
            )
        ],
    )

    records = run_invariant_checks(resolved)
    dups = [r for r in records if r.code == DUPLICATE_SYMBOL_INSTANCE]
    assert len(dups) == 1
