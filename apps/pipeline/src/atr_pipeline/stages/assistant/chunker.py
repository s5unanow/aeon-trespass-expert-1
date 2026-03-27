"""Semantic chunker — splits PageIRV1 blocks into RuleChunkV1 units."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from atr_schemas.common import NormRect, Rect
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    IconInline,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    TableBlock,
    TermMarkInline,
    TextInline,
    UnknownBlock,
)
from atr_schemas.rule_chunk_v1 import GlossaryConcept, RuleChunkV1

_MAX_PARAGRAPHS_PER_HEADING_GROUP = 3

# Block types that always form their own standalone chunk
_STANDALONE_TYPES = (CalloutBlock, TableBlock, ListBlock, ListItemBlock, CaptionBlock)


@dataclass
class _GroupAccumulator:
    """Tracks block grouping state during reading-order walk."""

    groups: list[list[str]] = field(default_factory=list)
    current: list[str] = field(default_factory=list)
    in_heading: bool = False
    para_count: int = 0

    def flush(self) -> None:
        if self.current:
            self.groups.append(self.current)
            self.current = []
        self.in_heading = False
        self.para_count = 0

    def start_heading(self, bid: str) -> None:
        self.flush()
        self.current = [bid]
        self.in_heading = True
        self.para_count = 0

    def add_standalone(self, bid: str) -> None:
        self.flush()
        self.groups.append([bid])

    def add_paragraph(self, bid: str) -> None:
        if self.in_heading and self.para_count < _MAX_PARAGRAPHS_PER_HEADING_GROUP:
            self.current.append(bid)
            self.para_count += 1
        else:
            self.flush()
            self.current = [bid]


def chunk_page(
    page_ir: PageIRV1,
    document_id: str,
    edition: str,
) -> list[RuleChunkV1]:
    """Split a single PageIRV1 into semantic RuleChunkV1 chunks."""
    block_map = {_block_id(b): b for b in page_ir.blocks}
    order = page_ir.reading_order or [_block_id(b) for b in page_ir.blocks]

    acc = _GroupAccumulator()
    for bid in order:
        block = block_map.get(bid)
        if block is None:
            continue
        _classify_block(acc, bid, block)
    acc.flush()

    return [
        chunk
        for group in acc.groups
        if (chunk := _build_chunk(group, block_map, page_ir, document_id, edition)) is not None
    ]


def _classify_block(acc: _GroupAccumulator, bid: str, block: Block) -> None:
    """Route a single block into the accumulator."""
    if isinstance(block, (DividerBlock, UnknownBlock)):
        acc.flush()
    elif isinstance(block, FigureBlock):
        acc.flush()
        if _has_text(block):
            acc.groups.append([bid])
    elif isinstance(block, HeadingBlock):
        acc.start_heading(bid)
    elif isinstance(block, _STANDALONE_TYPES):
        acc.add_standalone(bid)
    else:
        acc.add_paragraph(bid)


def _block_id(block: Block) -> str:
    return block.block_id


def _has_text(block: Block) -> bool:
    children = getattr(block, "children", [])
    return any(isinstance(c, TextInline) and c.text.strip() for c in children)


def _build_chunk(
    block_ids: list[str],
    block_map: dict[str, Block],
    page_ir: PageIRV1,
    document_id: str,
    edition: str,
) -> RuleChunkV1 | None:
    blocks = [block_map[bid] for bid in block_ids if bid in block_map]
    if not blocks:
        return None

    text = _extract_text(blocks)
    if not text.strip():
        return None

    anchor = _canonical_anchor(page_ir.page_id, block_ids)
    section_path: list[str] = []
    if page_ir.section_hint and page_ir.section_hint.path:
        section_path = list(page_ir.section_hint.path)

    return RuleChunkV1(
        rule_chunk_id=f"{document_id}.{anchor}.{page_ir.language.value}",
        document_id=document_id,
        edition=edition,
        page_id=page_ir.page_id,
        source_page_number=page_ir.page_number,
        section_path=section_path,
        block_ids=block_ids,
        canonical_anchor_id=anchor,
        language=page_ir.language,
        text=text,
        normalized_text=_normalize_text(text),
        glossary_concepts=_harvest_concepts(blocks),
        symbol_ids=_harvest_symbols(blocks),
        deep_link=f"/documents/{document_id}/{edition}/{page_ir.page_id}#anchor={anchor}",
        facsimile_bbox_refs=_compute_bbox_refs(blocks, page_ir),
    )


def _extract_text(blocks: list[Block]) -> str:
    """Extract text from blocks, respecting word boundaries at non-text inlines."""
    parts: list[str] = []
    for block in blocks:
        children = getattr(block, "children", [])
        if not children:
            raw = getattr(block, "raw_text", "")
            if raw:
                parts.append(raw)
            continue
        block_parts: list[str] = []
        for child in children:
            if isinstance(child, TextInline):
                block_parts.append(child.text)
            else:
                block_parts.append(" ")
        parts.append("".join(block_parts).strip())
    return " ".join(p for p in parts if p)


def _canonical_anchor(page_id: str, block_ids: list[str]) -> str:
    """Deterministic anchor from page + block IDs content hash."""
    key = "|".join(block_ids)
    short_hash = hashlib.sha256(key.encode()).hexdigest()[:8]
    page_num = page_id.lstrip("p")
    return f"chunk.{page_num}.{short_hash}"


def _normalize_text(text: str) -> str:
    """Lowercase, NFKD-normalize, collapse whitespace for FTS."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"\s+", " ", text).strip()


def _harvest_concepts(blocks: list[Block]) -> list[GlossaryConcept]:
    """Collect unique glossary concepts from TermMarkInline nodes."""
    seen: set[str] = set()
    concepts: list[GlossaryConcept] = []
    for block in blocks:
        for child in getattr(block, "children", []):
            if isinstance(child, TermMarkInline) and child.concept_id not in seen:
                seen.add(child.concept_id)
                concepts.append(
                    GlossaryConcept(
                        concept_id=child.concept_id,
                        surface_form=child.surface_form,
                    )
                )
    return concepts


def _harvest_symbols(blocks: list[Block]) -> list[str]:
    """Collect unique symbol IDs from IconInline nodes."""
    seen: set[str] = set()
    symbols: list[str] = []
    for block in blocks:
        for child in getattr(block, "children", []):
            if isinstance(child, IconInline) and child.symbol_id not in seen:
                seen.add(child.symbol_id)
                symbols.append(child.symbol_id)
    return symbols


def _compute_bbox_refs(blocks: list[Block], page_ir: PageIRV1) -> list[NormRect]:
    """Normalize block bboxes to [0,1] page coordinates."""
    if page_ir.dimensions_pt is None:
        return []
    w = page_ir.dimensions_pt.width
    h = page_ir.dimensions_pt.height
    if w <= 0 or h <= 0:
        return []

    refs: list[NormRect] = []
    for block in blocks:
        bbox: Rect | None = getattr(block, "bbox", None)
        if bbox is None:
            continue
        refs.append(
            NormRect(
                x0=max(0.0, min(1.0, bbox.x0 / w)),
                y0=max(0.0, min(1.0, bbox.y0 / h)),
                x1=max(0.0, min(1.0, bbox.x1 / w)),
                y1=max(0.0, min(1.0, bbox.y1 / h)),
            )
        )
    return refs
