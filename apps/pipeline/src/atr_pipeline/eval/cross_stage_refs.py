"""Cross-stage reference-integrity checks.

Each check function takes artifacts from two adjacent pipeline stages
and returns a list of QARecordV1 records for any broken cross-stage references.

Stage boundaries verified:
  NativePageV1  →  PageIRV1          (source_word_ids)
  PageEvidenceV1 → PageIRV1          (evidence_refs)
  SymbolMatchSetV1 → PageIRV1        (symbol_id in IconInline)
  PageIRV1       → RenderPageV1      (block_ids, figure asset_ids)
  RenderPageV1   → published bundle  (page JSON + figure files)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from atr_schemas.enums import QALayer, Severity
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.page_ir_v1 import (
    FigureBlock,
    IconInline,
    PageIRV1,
    TextInline,
)
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import (
    RenderFigureBlock,
    RenderFigureRefInline,
    RenderPageV1,
)
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1

# --- Cross-stage reference codes ---

XREF_NATIVE_WORD = "XREF_NATIVE_WORD"
XREF_EVIDENCE_TO_IR = "XREF_EVIDENCE_TO_IR"
XREF_SYMBOL_TO_IR = "XREF_SYMBOL_TO_IR"
XREF_SYMBOL_DROPPED = "XREF_SYMBOL_DROPPED"
XREF_IR_TO_RENDER = "XREF_IR_TO_RENDER"
XREF_RENDER_ASSET = "XREF_RENDER_ASSET"
XREF_IR_FIGURE_REMAP = "XREF_IR_FIGURE_REMAP"
XREF_RENDER_TO_PUBLISH = "XREF_RENDER_TO_PUBLISH"


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
        qa_id=f"qa.{page_id}.xref.{code.lower()}.{entity_ref}",
        layer=QALayer.EXTRACTION,
        severity=severity,
        code=code,
        document_id=document_id,
        page_id=page_id,
        entity_ref=entity_ref,
        message=message,
    )


def _collect_source_word_ids(ir: PageIRV1) -> list[tuple[str, str]]:
    """Collect (block_id, word_id) pairs from IR blocks."""
    pairs: list[tuple[str, str]] = []
    for block in ir.blocks:
        if hasattr(block, "source_ref") and block.source_ref:
            for wid in block.source_ref.word_ids:
                pairs.append((block.block_id, wid))
        if hasattr(block, "children"):
            for inline in block.children:
                if isinstance(inline, TextInline):
                    for wid in inline.source_word_ids:
                        pairs.append((block.block_id, wid))
    return pairs


def check_native_to_ir(
    native: NativePageV1,
    ir: PageIRV1,
) -> list[QARecordV1]:
    """source_word_ids in IR must exist in NativePageV1 words."""
    word_ids = {w.word_id for w in native.words}
    records: list[QARecordV1] = []
    for block_id, wid in _collect_source_word_ids(ir):
        if wid not in word_ids:
            records.append(
                _make_record(
                    page_id=ir.page_id,
                    document_id=ir.document_id,
                    code=XREF_NATIVE_WORD,
                    severity=Severity.ERROR,
                    entity_ref=f"{block_id}:{wid}",
                    message=f"Block {block_id} references word {wid} not found in native page.",
                )
            )
    return records


def check_evidence_to_ir(
    evidence: PageEvidenceV1,
    ir: PageIRV1,
) -> list[QARecordV1]:
    """evidence_refs in IR SourceRef must exist in PageEvidenceV1 entities."""
    evidence_ids = {e.evidence_id for e in evidence.entities}
    records: list[QARecordV1] = []
    for block in ir.blocks:
        if not hasattr(block, "source_ref") or not block.source_ref:
            continue
        for eref in block.source_ref.evidence_refs:
            if eref not in evidence_ids:
                records.append(
                    _make_record(
                        page_id=ir.page_id,
                        document_id=ir.document_id,
                        code=XREF_EVIDENCE_TO_IR,
                        severity=Severity.ERROR,
                        entity_ref=f"{block.block_id}:{eref}",
                        message=f"Block {block.block_id} references evidence "
                        f"{eref} not found in page evidence.",
                    )
                )
    return records


def _collect_ir_symbol_ids(ir: PageIRV1) -> set[str]:
    """Collect all symbol_ids referenced in IR IconInline nodes."""
    ids: set[str] = set()
    for block in ir.blocks:
        if not hasattr(block, "children"):
            continue
        for inline in block.children:
            if isinstance(inline, IconInline):
                ids.add(inline.symbol_id)
    return ids


def check_symbols_to_ir(
    symbols: SymbolMatchSetV1,
    ir: PageIRV1,
) -> list[QARecordV1]:
    """Symbol matches ↔ IR IconInline consistency.

    ERROR if IR references a symbol_id not present in matches (phantom).
    WARNING if a match is not present in IR (dropped — may be intentional).
    """
    match_ids = {m.symbol_id for m in symbols.matches}
    ir_ids = _collect_ir_symbol_ids(ir)
    records: list[QARecordV1] = []

    for sid in ir_ids - match_ids:
        records.append(
            _make_record(
                page_id=ir.page_id,
                document_id=ir.document_id,
                code=XREF_SYMBOL_TO_IR,
                severity=Severity.ERROR,
                entity_ref=sid,
                message=f"IR references symbol {sid} with no "
                f"corresponding match in SymbolMatchSet.",
            )
        )

    for sid in match_ids - ir_ids:
        records.append(
            _make_record(
                page_id=ir.page_id,
                document_id=ir.document_id,
                code=XREF_SYMBOL_DROPPED,
                severity=Severity.WARNING,
                entity_ref=sid,
                message=f"Symbol match {sid} not present in IR (may have been filtered).",
            )
        )

    return records


def _check_figure_asset_remap(
    ir: PageIRV1,
    render: RenderPageV1,
) -> list[QARecordV1]:
    """Verify IR figure asset_ids are preserved in corresponding render blocks."""
    render_figure_blocks: dict[str, str] = {}
    for rb in render.blocks:
        if isinstance(rb, RenderFigureBlock) and rb.asset_id:
            render_figure_blocks[rb.id] = rb.asset_id

    records: list[QARecordV1] = []
    for block in ir.blocks:
        if not isinstance(block, FigureBlock) or not block.asset_id:
            continue
        render_asset = render_figure_blocks.get(block.block_id)
        if render_asset is None:
            continue  # block absence is caught by the block_id check
        if render_asset != block.asset_id:
            records.append(
                _make_record(
                    page_id=ir.page_id,
                    document_id=ir.document_id,
                    code=XREF_IR_FIGURE_REMAP,
                    severity=Severity.ERROR,
                    entity_ref=block.block_id,
                    message=f"IR figure {block.block_id} has asset_id "
                    f"'{block.asset_id}' but render has '{render_asset}'.",
                )
            )
    return records


def _check_render_figure_consistency(
    ir: PageIRV1,
    render: RenderPageV1,
) -> list[QARecordV1]:
    """Render-internal: referenced figure asset_ids must exist in figures dict."""
    render_figure_ids = set(render.figures.keys())
    render_inline_asset_ids: set[str] = set()
    for rb in render.blocks:
        if isinstance(rb, RenderFigureBlock) and rb.asset_id:
            render_inline_asset_ids.add(rb.asset_id)
        if hasattr(rb, "children"):
            for ri in rb.children:
                if isinstance(ri, RenderFigureRefInline) and ri.asset_id:
                    render_inline_asset_ids.add(ri.asset_id)

    records: list[QARecordV1] = []
    for aid in render_inline_asset_ids - render_figure_ids:
        records.append(
            _make_record(
                page_id=ir.page_id,
                document_id=ir.document_id,
                code=XREF_RENDER_ASSET,
                severity=Severity.ERROR,
                entity_ref=aid,
                message=f"Render references figure asset {aid} not present in figures dict.",
            )
        )
    return records


def check_ir_to_render(
    ir: PageIRV1,
    render: RenderPageV1,
) -> list[QARecordV1]:
    """IR block_ids and figure assets must be preserved in render output."""
    render_block_ids = {b.id for b in render.blocks}
    records: list[QARecordV1] = []

    for block in ir.blocks:
        if not getattr(block, "translatable", True):
            continue
        if block.block_id not in render_block_ids:
            records.append(
                _make_record(
                    page_id=ir.page_id,
                    document_id=ir.document_id,
                    code=XREF_IR_TO_RENDER,
                    severity=Severity.WARNING,
                    entity_ref=block.block_id,
                    message=f"IR block {block.block_id} not found in render output.",
                )
            )

    records.extend(_check_figure_asset_remap(ir, render))
    records.extend(_check_render_figure_consistency(ir, render))
    return records


def check_render_to_publish(
    render: RenderPageV1,
    release_dir: Path,
    page_id: str,
    document_id: str,
) -> list[QARecordV1]:
    """Published bundle must contain files for rendered pages and figures."""
    records: list[QARecordV1] = []

    page_json = release_dir / "pages" / f"{page_id}.json"
    if not page_json.exists():
        records.append(
            _make_record(
                page_id=page_id,
                document_id=document_id,
                code=XREF_RENDER_TO_PUBLISH,
                severity=Severity.ERROR,
                entity_ref=page_id,
                message=f"Published page JSON missing: {page_json.name}",
            )
        )

    for asset_id, fig in render.figures.items():
        if not fig.src:
            continue
        asset_path = release_dir / fig.src
        if not asset_path.exists():
            records.append(
                _make_record(
                    page_id=page_id,
                    document_id=document_id,
                    code=XREF_RENDER_TO_PUBLISH,
                    severity=Severity.ERROR,
                    entity_ref=asset_id,
                    message=f"Published figure asset missing: {fig.src}",
                )
            )

    return records


@dataclass
class PageArtifacts:
    """Bundle of per-page artifacts for cross-stage verification."""

    page_id: str
    document_id: str
    native: NativePageV1 | None = field(default=None)
    evidence: PageEvidenceV1 | None = field(default=None)
    ir: PageIRV1 | None = field(default=None)
    symbols: SymbolMatchSetV1 | None = field(default=None)
    render: RenderPageV1 | None = field(default=None)
    release_dir: Path | None = field(default=None)


def run_cross_stage_checks(artifacts: PageArtifacts) -> list[QARecordV1]:
    """Run all applicable cross-stage checks for a page."""
    records: list[QARecordV1] = []
    if artifacts.native is not None and artifacts.ir is not None:
        records.extend(check_native_to_ir(artifacts.native, artifacts.ir))
    if artifacts.evidence is not None and artifacts.ir is not None:
        records.extend(check_evidence_to_ir(artifacts.evidence, artifacts.ir))
    if artifacts.symbols is not None and artifacts.ir is not None:
        records.extend(check_symbols_to_ir(artifacts.symbols, artifacts.ir))
    if artifacts.ir is not None and artifacts.render is not None:
        records.extend(check_ir_to_render(artifacts.ir, artifacts.render))
    if artifacts.render is not None and artifacts.release_dir is not None:
        records.extend(
            check_render_to_publish(
                artifacts.render,
                artifacts.release_dir,
                artifacts.page_id,
                artifacts.document_id,
            )
        )
    return records
