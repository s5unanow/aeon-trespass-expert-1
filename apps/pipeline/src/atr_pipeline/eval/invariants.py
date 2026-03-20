"""Core extraction artifact invariant checks.

Each check function takes a ResolvedPageV1 (and optionally PageEvidenceV1)
and returns a list of QARecordV1 records for any violations found.
"""

from __future__ import annotations

from atr_schemas.enums import AnchorEdgeKind, BlockType, QALayer, Severity
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.resolved_page_v1 import ResolvedPageV1

# --- Invariant codes ---

DANGLING_REGION_REF = "DANGLING_REGION_REF"
DANGLING_FLOW_REF = "DANGLING_FLOW_REF"
DANGLING_ANCHOR_REF = "DANGLING_ANCHOR_REF"
DANGLING_EVIDENCE_REF = "DANGLING_EVIDENCE_REF"
BBOX_OUT_OF_PAGE = "BBOX_OUT_OF_PAGE"
DUPLICATE_SYMBOL_INSTANCE = "DUPLICATE_SYMBOL_INSTANCE"
ORPHAN_CAPTION = "ORPHAN_CAPTION"
ANCHOR_CYCLE = "ANCHOR_CYCLE"
MISSING_FALLBACK_PROVENANCE = "MISSING_FALLBACK_PROVENANCE"

_TREE_EDGE_KINDS = frozenset({AnchorEdgeKind.BLOCK_TO_REGION, AnchorEdgeKind.ASIDE_TO_MAIN})

# Small tolerance for floating-point bbox comparisons (PDF points).
_BBOX_TOLERANCE = 0.5


def _make_record(
    *,
    page_id: str,
    document_id: str,
    code: str,
    severity: Severity,
    entity_ref: str,
    message: str,
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{page_id}.inv.{code.lower()}.{entity_ref}",
        layer=QALayer.EXTRACTION,
        severity=severity,
        code=code,
        document_id=document_id,
        page_id=page_id,
        entity_ref=entity_ref,
        message=message,
    )


def check_dangling_region_ref(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """block.region_id must exist in regions list (if non-empty)."""
    region_ids = {r.region_id for r in resolved.regions}
    records: list[QARecordV1] = []
    for block in resolved.blocks:
        if block.region_id and block.region_id not in region_ids:
            records.append(
                _make_record(
                    page_id=resolved.page_id,
                    document_id=resolved.document_id,
                    code=DANGLING_REGION_REF,
                    severity=Severity.ERROR,
                    entity_ref=block.block_id,
                    message=f"Block {block.block_id} references region "
                    f"{block.region_id} which does not exist.",
                )
            )
    return records


def check_dangling_flow_ref(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """main_flow_order entries must exist as block_ids."""
    block_ids = {b.block_id for b in resolved.blocks}
    records: list[QARecordV1] = []
    for ref in resolved.main_flow_order:
        if ref not in block_ids:
            records.append(
                _make_record(
                    page_id=resolved.page_id,
                    document_id=resolved.document_id,
                    code=DANGLING_FLOW_REF,
                    severity=Severity.ERROR,
                    entity_ref=ref,
                    message=f"main_flow_order references block {ref} which does not exist.",
                )
            )
    return records


def check_dangling_anchor_ref(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """anchor_edge source/target must exist as block or region id."""
    valid_ids = {b.block_id for b in resolved.blocks} | {r.region_id for r in resolved.regions}
    records: list[QARecordV1] = []
    for edge in resolved.anchor_edges:
        for ref_id, role in [(edge.source_id, "source"), (edge.target_id, "target")]:
            if ref_id not in valid_ids:
                records.append(
                    _make_record(
                        page_id=resolved.page_id,
                        document_id=resolved.document_id,
                        code=DANGLING_ANCHOR_REF,
                        severity=Severity.ERROR,
                        entity_ref=ref_id,
                        message=f"Anchor edge {edge.edge_kind} {role} {ref_id} does not exist.",
                    )
                )
    return records


def check_dangling_evidence_ref(
    resolved: ResolvedPageV1,
    evidence: PageEvidenceV1,
) -> list[QARecordV1]:
    """evidence_ids on blocks/regions must exist in evidence entities."""
    evidence_ids = {e.evidence_id for e in evidence.entities}
    records: list[QARecordV1] = []
    for block in resolved.blocks:
        for eid in block.evidence_ids:
            if eid not in evidence_ids:
                records.append(
                    _make_record(
                        page_id=resolved.page_id,
                        document_id=resolved.document_id,
                        code=DANGLING_EVIDENCE_REF,
                        severity=Severity.ERROR,
                        entity_ref=f"{block.block_id}:{eid}",
                        message=f"Block {block.block_id} references evidence "
                        f"{eid} which does not exist.",
                    )
                )
    for region in resolved.regions:
        for eid in region.evidence_ids:
            if eid not in evidence_ids:
                records.append(
                    _make_record(
                        page_id=resolved.page_id,
                        document_id=resolved.document_id,
                        code=DANGLING_EVIDENCE_REF,
                        severity=Severity.ERROR,
                        entity_ref=f"{region.region_id}:{eid}",
                        message=f"Region {region.region_id} references evidence "
                        f"{eid} which does not exist.",
                    )
                )
    return records


def check_bbox_out_of_page(evidence: PageEvidenceV1) -> list[QARecordV1]:
    """Evidence entity bboxes must be within page_dimensions_pt."""
    dims = evidence.transform.page_dimensions_pt
    records: list[QARecordV1] = []
    for entity in evidence.entities:
        bbox = entity.bbox
        if (
            bbox.x0 < -_BBOX_TOLERANCE
            or bbox.y0 < -_BBOX_TOLERANCE
            or bbox.x1 > dims.width + _BBOX_TOLERANCE
            or bbox.y1 > dims.height + _BBOX_TOLERANCE
        ):
            records.append(
                _make_record(
                    page_id=evidence.page_id,
                    document_id=evidence.document_id,
                    code=BBOX_OUT_OF_PAGE,
                    severity=Severity.WARNING,
                    entity_ref=entity.evidence_id,
                    message=f"Entity {entity.evidence_id} bbox "
                    f"({bbox.x0},{bbox.y0},{bbox.x1},{bbox.y1}) "
                    f"outside page ({dims.width}x{dims.height}).",
                )
            )
    return records


def check_duplicate_symbol_instance(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """symbol_ref instance_ids must be unique within page."""
    seen: dict[str, str] = {}
    records: list[QARecordV1] = []
    all_refs = list(resolved.symbol_refs)
    for block in resolved.blocks:
        all_refs.extend(block.symbol_refs)
    for ref in all_refs:
        if not ref.instance_id:
            continue
        if ref.instance_id in seen:
            records.append(
                _make_record(
                    page_id=resolved.page_id,
                    document_id=resolved.document_id,
                    code=DUPLICATE_SYMBOL_INSTANCE,
                    severity=Severity.ERROR,
                    entity_ref=ref.instance_id,
                    message=f"Duplicate symbol instance_id {ref.instance_id} "
                    f"(first on {seen[ref.instance_id]}, also on {ref.symbol_id}).",
                )
            )
        else:
            seen[ref.instance_id] = ref.symbol_id
    return records


def check_orphan_caption(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """CAPTION blocks must have a CAPTION_TO_FIGURE anchor edge."""
    caption_sources = {
        edge.source_id
        for edge in resolved.anchor_edges
        if edge.edge_kind == AnchorEdgeKind.CAPTION_TO_FIGURE
    }
    records: list[QARecordV1] = []
    for block in resolved.blocks:
        if block.block_type == BlockType.CAPTION and block.block_id not in caption_sources:
            records.append(
                _make_record(
                    page_id=resolved.page_id,
                    document_id=resolved.document_id,
                    code=ORPHAN_CAPTION,
                    severity=Severity.WARNING,
                    entity_ref=block.block_id,
                    message=f"Caption block {block.block_id} has no CAPTION_TO_FIGURE edge.",
                )
            )
    return records


def check_anchor_cycle(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """Tree-like anchor edges (BLOCK_TO_REGION, ASIDE_TO_MAIN) must be acyclic."""
    adj: dict[str, list[str]] = {}
    for edge in resolved.anchor_edges:
        if edge.edge_kind in _TREE_EDGE_KINDS:
            adj.setdefault(edge.source_id, []).append(edge.target_id)

    if not adj:
        return []

    white, gray, black = 0, 1, 2
    color: dict[str, int] = {}
    cycle_nodes: list[str] = []

    def dfs(node: str) -> bool:
        color[node] = gray
        for neighbour in adj.get(node, []):
            c = color.get(neighbour, white)
            if c == gray:
                cycle_nodes.append(neighbour)
                return True
            if c == white and dfs(neighbour):
                return True
        color[node] = black
        return False

    for node in adj:
        if color.get(node, white) == white and dfs(node):
            break

    records: list[QARecordV1] = []
    if cycle_nodes:
        records.append(
            _make_record(
                page_id=resolved.page_id,
                document_id=resolved.document_id,
                code=ANCHOR_CYCLE,
                severity=Severity.ERROR,
                entity_ref=cycle_nodes[0],
                message=f"Cycle detected in tree-like anchor edges near {cycle_nodes[0]}.",
            )
        )
    return records


def check_missing_fallback_provenance(resolved: ResolvedPageV1) -> list[QARecordV1]:
    """Blocks with fallback must have non-empty strategy."""
    records: list[QARecordV1] = []
    for block in resolved.blocks:
        if block.fallback is not None and not block.fallback.strategy:
            records.append(
                _make_record(
                    page_id=resolved.page_id,
                    document_id=resolved.document_id,
                    code=MISSING_FALLBACK_PROVENANCE,
                    severity=Severity.WARNING,
                    entity_ref=block.block_id,
                    message=f"Block {block.block_id} has fallback but empty strategy.",
                )
            )
    return records


def run_invariant_checks(
    resolved: ResolvedPageV1,
    evidence: PageEvidenceV1 | None = None,
) -> list[QARecordV1]:
    """Run all invariant checks and return combined QA records."""
    records: list[QARecordV1] = []
    # Resolved-only checks
    records.extend(check_dangling_region_ref(resolved))
    records.extend(check_dangling_flow_ref(resolved))
    records.extend(check_dangling_anchor_ref(resolved))
    records.extend(check_duplicate_symbol_instance(resolved))
    records.extend(check_orphan_caption(resolved))
    records.extend(check_anchor_cycle(resolved))
    records.extend(check_missing_fallback_provenance(resolved))
    # Evidence-dependent checks
    if evidence is not None:
        records.extend(check_dangling_evidence_ref(resolved, evidence))
        records.extend(check_bbox_out_of_page(evidence))
    return records
