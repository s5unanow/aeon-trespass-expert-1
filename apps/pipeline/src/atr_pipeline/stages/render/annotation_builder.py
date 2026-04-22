"""Build facsimile annotations from PageIRV1 blocks with bounding boxes.

See S5U-697 for the pairing-stability and occlusion-suppression rules added
to this module: the render stage feeds this with whichever EN / RU IR it can
find on disk, so the builder cannot assume the two IRs came from the same
extraction run. Mis-matched ``block_id`` lookups, degenerate bboxes, and
overlapping hotspots are all rejected here so they never reach the reader.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from atr_pipeline.stages.render.annotation_safeguards import (
    bbox_area,
    is_bbox_valid,
    strip_implausible_pairings,
    suppress_fully_occluded,
)
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
    keep_texts: list[str] | None = None,
) -> list[FacsimileAnnotation]:
    """Convert PageIRV1 blocks to positioned facsimile annotations.

    Builds candidate annotations, applies per-annotation quality filters,
    then evaluates page-level quality. Returns an empty list if the
    overlay would be too noisy.

    When *keep_texts* is provided, only candidates whose English text
    contains at least one of the given substrings are kept (applied
    before quality filtering).
    """
    cfg = quality or AnnotationQualityConfig()
    candidates = _build_candidates(en_ir, ru_ir)
    curated = keep_texts is not None
    if keep_texts is not None:
        candidates = [c for c in candidates if any(kt in c.text for kt in keep_texts)]
    # S5U-697: strip translations that look like stale-IR leakage *before*
    # running the quality filters so the length-ratio check does not have to
    # reason about a filter pipeline that may already have dropped context.
    candidates = strip_implausible_pairings(candidates)
    filtered = _filter_annotations(candidates, cfg, curated=curated)
    # S5U-697: after per-annotation filtering, drop outer hotspots that fully
    # occlude an inner one. Applied late so we do not waste a containment pass
    # on annotations that were going to be filtered for unrelated reasons.
    # Skipped in curated mode — the operator has explicitly listed which
    # captions to surface and is expected to resolve overlaps manually.
    pre_occlusion = filtered
    if not curated:
        filtered = suppress_fully_occluded(filtered)
    # S5U-697 Codex round-2: the drop-ratio gate compares against candidates
    # *minus* any drops that were purely occlusion-suppression (which are
    # legitimate deduplications, not quality rejections). Otherwise a page
    # with several nested hotspots hits the drop-ratio gate and ships []
    # even though the surviving overlay is clean.
    occlusion_drops = len(pre_occlusion) - len(filtered)
    effective_candidates = max(0, len(candidates) - occlusion_drops)
    if not curated and not _page_quality_ok(filtered, cfg, candidate_count=effective_candidates):
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

        # S5U-697: reject non-finite raw bbox coords *before* clamping into
        # [0,1]. Codex review caught that `min/max` coerce NaN to finite
        # boundary values (nan -> 1.0, inf -> 1.0, -inf -> 0.0) in Python,
        # so a post-normalization `math.isfinite` check runs too late — a
        # corrupted extractor bbox would emerge as a valid-looking hotspot.
        raw_coords = (block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1)
        if not all(math.isfinite(c) for c in raw_coords):
            continue

        bbox = NormRect(
            x0=max(0.0, min(1.0, block.bbox.x0 / dims.width)),
            y0=max(0.0, min(1.0, block.bbox.y0 / dims.height)),
            x1=max(0.0, min(1.0, block.bbox.x1 / dims.width)),
            y1=max(0.0, min(1.0, block.bbox.y1 / dims.height)),
        )
        # S5U-697: reject degenerate bboxes (zero width/height after
        # normalization). Non-finite coords are already rejected above on
        # the raw values; this belt-and-suspenders also catches bboxes
        # that collapsed because x1 == x0 on the raw side.
        if not is_bbox_valid(bbox):
            continue

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
    *,
    curated: bool = False,
) -> list[FacsimileAnnotation]:
    """Apply per-annotation quality filters.

    When *curated* is True (keep_texts was specified), the bbox-area
    check is skipped — the caller already curated the candidate set.
    """
    result: list[FacsimileAnnotation] = []
    for ann in candidates:
        if _is_identical_translation(ann.text, ann.translated_text):
            continue
        if not curated and bbox_area(ann.bbox) > cfg.max_bbox_area:
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
    total_area = sum(bbox_area(a.bbox) for a in annotations)
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


def _is_garbled(text: str, min_letter_ratio: float) -> bool:
    """Return True if text is mostly non-letter characters (OCR noise)."""
    stripped = text.replace(" ", "")
    if len(stripped) < 2:
        return False  # single chars are fine (game labels like "I", "?")
    alphanumeric = sum(1 for c in stripped if c.isalnum())
    return (alphanumeric / len(stripped)) < min_letter_ratio
