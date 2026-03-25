"""Build facsimile annotations from PageIRV1 blocks with bounding boxes."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from atr_schemas.common import NormRect
from atr_schemas.page_ir_v1 import (
    Block,
    DividerBlock,
    IconInline,
    PageIRV1,
    UnknownBlock,
)
from atr_schemas.render_page_v1 import FacsimileAnnotation

AnnotationKind = Literal["title", "body", "caption", "callout", "label"]

# Block type → (annotation kind, base priority)
_BLOCK_KIND_MAP: dict[str, tuple[AnnotationKind, int]] = {
    "heading": ("title", 100),
    "callout": ("callout", 80),
    "caption": ("caption", 60),
    "paragraph": ("body", 40),
    "list_item": ("body", 40),
    "list": ("body", 40),
    "table": ("body", 30),
    "figure": ("label", 10),
}


class AnnotationQualityConfig(BaseModel):
    """Thresholds for per-annotation and page-level quality filtering."""

    max_bbox_area: float = Field(default=0.10, ge=0.0, le=1.0)
    max_total_area: float = Field(default=0.30, ge=0.0)
    max_annotation_count: int = Field(default=25, ge=0)
    min_letter_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    max_drop_ratio: float = Field(default=0.5, ge=0.0, le=1.0)


def build_facsimile_annotations(
    en_ir: PageIRV1,
    ru_ir: PageIRV1 | None = None,
    *,
    quality: AnnotationQualityConfig | None = None,
) -> list[FacsimileAnnotation]:
    """Convert PageIRV1 blocks to positioned facsimile annotations.

    Builds candidate annotations, applies per-annotation quality filters,
    then evaluates page-level quality. Returns an empty list if the
    overlay would be too noisy.
    """
    cfg = quality or AnnotationQualityConfig()
    candidates = _build_candidates(en_ir, ru_ir)
    filtered = _filter_annotations(candidates, cfg)
    if not _page_quality_ok(filtered, cfg, candidate_count=len(candidates)):
        return []
    filtered.sort(key=lambda a: a.priority, reverse=True)
    return filtered


def _build_candidates(
    en_ir: PageIRV1,
    ru_ir: PageIRV1 | None,
) -> list[FacsimileAnnotation]:
    """Extract raw annotation candidates from IR blocks."""
    dims = en_ir.dimensions_pt
    if dims is None or dims.width <= 0 or dims.height <= 0:
        return []

    ru_blocks: dict[str, Block] = {}
    if ru_ir is not None:
        for block in ru_ir.blocks:
            ru_blocks[block.block_id] = block

    annotations: list[FacsimileAnnotation] = []
    for block in en_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        if block.bbox is None:
            continue

        en_text = _extract_block_text(block)
        if not en_text.strip():
            continue

        kind, priority = _BLOCK_KIND_MAP.get(block.type, ("body", 20))

        ru_text = ""
        ru_block = ru_blocks.get(block.block_id)
        if ru_block is not None:
            ru_text = _extract_block_text(ru_block)

        bbox = NormRect(
            x0=max(0.0, min(1.0, block.bbox.x0 / dims.width)),
            y0=max(0.0, min(1.0, block.bbox.y0 / dims.height)),
            x1=max(0.0, min(1.0, block.bbox.x1 / dims.width)),
            y1=max(0.0, min(1.0, block.bbox.y1 / dims.height)),
        )

        annotations.append(
            FacsimileAnnotation(
                text=en_text,
                translated_text=ru_text,
                bbox=bbox,
                kind=kind,
                priority=priority,
            )
        )
    return annotations


def _filter_annotations(
    candidates: list[FacsimileAnnotation],
    cfg: AnnotationQualityConfig,
) -> list[FacsimileAnnotation]:
    """Apply per-annotation quality filters."""
    result: list[FacsimileAnnotation] = []
    for ann in candidates:
        if _is_identical_translation(ann.text, ann.translated_text):
            continue
        if _bbox_area(ann.bbox) > cfg.max_bbox_area:
            continue
        if _is_garbled(ann.text, cfg.min_letter_ratio):
            continue
        result.append(ann)
    return result


def _page_quality_ok(
    annotations: list[FacsimileAnnotation],
    cfg: AnnotationQualityConfig,
    *,
    candidate_count: int = 0,
) -> bool:
    """Evaluate whether the annotation set is good enough to display."""
    if not annotations:
        return True  # empty is fine — nothing to suppress
    if len(annotations) > cfg.max_annotation_count:
        return False
    total_area = sum(_bbox_area(a.bbox) for a in annotations)
    if total_area > cfg.max_total_area:
        return False
    if candidate_count > 0:
        dropped = candidate_count - len(annotations)
        if (dropped / candidate_count) > cfg.max_drop_ratio:
            return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_block_text(block: Block) -> str:
    """Extract plain text from a block's inline children."""
    if isinstance(block, (DividerBlock, UnknownBlock)):
        return ""
    parts: list[str] = []
    for child in block.children:
        if child.type == "text":
            parts.append(child.text)
        elif isinstance(child, IconInline) and child.symbol_id:
            parts.append(f"[{child.symbol_id}]")
    return " ".join(parts)


def _normalize_for_compare(text: str) -> str:
    """Normalize text for EN/RU identity comparison."""
    t = unicodedata.normalize("NFC", text)
    t = " ".join(t.split())  # collapse whitespace
    t = t.casefold().strip()
    return t


def _is_identical_translation(en: str, ru: str) -> bool:
    """Return True if EN and RU are effectively the same text."""
    if not ru:
        return False  # no translation available — keep the annotation
    return _normalize_for_compare(en) == _normalize_for_compare(ru)


def _bbox_area(bbox: NormRect) -> float:
    """Compute normalized area of a bounding box."""
    w = max(0.0, bbox.x1 - bbox.x0)
    h = max(0.0, bbox.y1 - bbox.y0)
    return w * h


def _is_garbled(text: str, min_letter_ratio: float) -> bool:
    """Return True if text is mostly non-letter characters (OCR noise)."""
    stripped = text.replace(" ", "")
    if len(stripped) < 2:
        return False  # single chars are fine (game labels like "I", "?")
    alphanumeric = sum(1 for c in stripped if c.isalnum())
    return (alphanumeric / len(stripped)) < min_letter_ratio
