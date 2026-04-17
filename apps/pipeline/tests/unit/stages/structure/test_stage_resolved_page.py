"""Regression: ``ResolvedPageV1.main_flow_order`` must reference block IDs (S5U-585).

Before the fix, the structure stage stored region IDs from
``ReadingOrderResult.main_flow_order`` directly into
``ResolvedPageV1.main_flow_order``, which is defined as block IDs and
gates the ``DANGLING_FLOW_REF`` invariant.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from atr_pipeline.stages.structure.reading_order import ReadingOrderResult
from atr_pipeline.stages.structure.semantic_resolver import SemanticResolution
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import BlockType, RegionKind
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.resolved_page_v1 import ResolvedBlock, ResolvedPageV1, ResolvedRegion


def _region(region_id: str, x0: float, y0: float, x1: float, y1: float) -> ResolvedRegion:
    return ResolvedRegion(
        region_id=region_id,
        kind=RegionKind.BODY,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        norm_bbox=NormRect(x0=x0 / 612, y0=y0 / 792, x1=x1 / 612, y1=y1 / 792),
    )


def _resolved_block(block_id: str, region_id: str) -> ResolvedBlock:
    return ResolvedBlock(
        block_id=block_id,
        block_type=BlockType.PARAGRAPH,
        region_id=region_id,
    )


def _native() -> NativePageV1:
    return NativePageV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
        words=[],
        spans=[],
        image_blocks=[],
    )


def _load_resolved(store: ArtifactStore) -> ResolvedPageV1:
    data = store.load_latest_json(
        document_id="test_doc",
        schema_family="resolved_page.v1",
        scope="page",
        entity_id="p0001",
    )
    assert data is not None
    return ResolvedPageV1.model_validate(data)


def test_main_flow_order_contains_block_ids_not_region_ids(tmp_path: Path) -> None:
    """Writing ResolvedPageV1 must store block IDs in main_flow_order."""
    store = ArtifactStore(tmp_path / "artifacts")
    ctx = SimpleNamespace(document_id="test_doc", artifact_store=store)

    regions = [
        _region("r001", 0, 0, 612, 400),
        _region("r002", 0, 400, 612, 792),
    ]
    resolved_blocks = [
        _resolved_block("p0001.b001", "r001"),
        _resolved_block("p0001.b002", "r001"),
        _resolved_block("p0001.b003", "r002"),
    ]
    semantics = SemanticResolution(resolved_blocks=resolved_blocks)
    order = ReadingOrderResult(main_flow_order=["r001", "r002"])
    block_flow = ["p0001.b001", "p0001.b002", "p0001.b003"]

    StructureStage._store_regions(
        ctx,  # type: ignore[arg-type]
        _native(),
        regions,
        order,
        semantics=semantics,
        main_flow_block_ids=block_flow,
    )

    resolved = _load_resolved(store)
    block_ids = {b.block_id for b in resolved.blocks}
    region_ids = {r.region_id for r in resolved.regions}

    assert resolved.main_flow_order == block_flow
    assert region_ids.isdisjoint(set(resolved.main_flow_order)), (
        "main_flow_order leaked region IDs (S5U-585 regression)"
    )
    for ref in resolved.main_flow_order:
        assert ref in block_ids, f"main_flow_order entry {ref!r} is not a block ID"


def test_main_flow_order_is_empty_when_no_block_flow_supplied(tmp_path: Path) -> None:
    """Simple-builder path (no semantics / no block flow) leaves main_flow_order empty.

    The previous code populated ``main_flow_order`` with region IDs from
    ``ReadingOrderResult`` even when no blocks existed on the resolved page,
    which surfaced as DANGLING_FLOW_REF findings.
    """
    store = ArtifactStore(tmp_path / "artifacts")
    ctx = SimpleNamespace(document_id="test_doc", artifact_store=store)

    regions = [_region("r001", 0, 0, 612, 792)]
    order = ReadingOrderResult(main_flow_order=["r001"])

    StructureStage._store_regions(
        ctx,  # type: ignore[arg-type]
        _native(),
        regions,
        order,
    )

    resolved = _load_resolved(store)
    assert resolved.main_flow_order == []
