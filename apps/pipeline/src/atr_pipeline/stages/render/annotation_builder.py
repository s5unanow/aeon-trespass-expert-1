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

# S5U-697 pairing-stability thresholds. A stale RU IR produces `block_id`
# matches whose translated text has wildly different length from the English
# source; real translations cluster within a factor of ~2x. These bounds are
# intentionally generous (5x / 0.2x) so that abbreviation-heavy pairs
# (e.g. "HP" -> "zdorove") still pass, but multi-paragraph leakage is caught.
_PAIRING_MAX_LENGTH_RATIO = 5.0
_PAIRING_MIN_LENGTH_RATIO = 0.2
_PAIRING_MIN_EN_LENGTH = 4  # below this we don't have enough signal to judge

# S5U-697 page-level staleness threshold. If >=30% of paired EN/RU blocks on
# a page fail the per-annotation length-ratio plausibility check, the entire
# RU IR is treated as stale (generated from a different extraction run than
# the current EN IR). In that case every translated_text on the page is
# cleared — the reader will show EN-only tooltips rather than ship confident
# but wrong pairings. This is the "fail closed" escape hatch the issue asks
# for when tooltip mappings reference stale content.
_PAGE_STALENESS_RATIO = 0.30

# Bbox overlap suppression threshold. A bbox is "fully contained" if >=90% of
# its area lies inside another bbox; the *outer* (less-specific) annotation
# is dropped so the inner hotspot stays reachable. 90% rather than 100% to
# tolerate 1-pixel extractor jitter.
_FULL_CONTAINMENT_RATIO = 0.9

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
    candidates = _strip_implausible_pairings(candidates)
    filtered = _filter_annotations(candidates, cfg, curated=curated)
    # S5U-697: after per-annotation filtering, drop outer hotspots that fully
    # occlude an inner one. Applied late so we do not waste a containment pass
    # on annotations that were going to be filtered for unrelated reasons.
    # Skipped in curated mode — the operator has explicitly listed which
    # captions to surface and is expected to resolve overlaps manually.
    if not curated:
        filtered = _suppress_fully_occluded(filtered)
    if not curated and not _page_quality_ok(filtered, cfg, candidate_count=len(candidates)):
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
        # S5U-697: reject degenerate bboxes (zero width/height, NaN, inf).
        # A marker on a collapsed rect renders a centroid the user can see
        # but cannot interact with in a predictable way, and a non-finite
        # bbox bypasses the downstream area math entirely.
        if not _is_bbox_valid(bbox):
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
        if not curated and _bbox_area(ann.bbox) > cfg.max_bbox_area:
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


# ---------------------------------------------------------------------------
# S5U-697 — pairing-stability + occlusion-suppression helpers
# ---------------------------------------------------------------------------


def _is_bbox_valid(bbox: NormRect) -> bool:
    """Return True iff bbox coordinates are finite and area is positive.

    Zero-width or zero-height bboxes cannot host a clickable marker
    meaningfully, and non-finite coordinates would break every downstream
    overlap / area calculation silently.
    """
    coords = (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    if not all(math.isfinite(c) for c in coords):
        return False
    return not (bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0)


def _is_plausible_pair(en_text: str, ru_text: str) -> bool:
    """Return True when EN/RU texts could plausibly be translations of each other.

    Uses a length-ratio heuristic: real translations cluster around 1x (a bit
    higher for Cyrillic expansion, lower for very terse RU labels). Pairs that
    exceed ``_PAIRING_MAX_LENGTH_RATIO`` or fall below
    ``_PAIRING_MIN_LENGTH_RATIO`` are treated as stale-IR leakage.

    Short EN texts (``< _PAIRING_MIN_EN_LENGTH`` chars) are always considered
    plausible — with so little signal, a length check produces more false
    positives than it catches true mismatches.
    """
    en_stripped = en_text.strip()
    ru_stripped = ru_text.strip()
    if not en_stripped or not ru_stripped:
        return True  # caller handles the empty-translation case separately
    if len(en_stripped) < _PAIRING_MIN_EN_LENGTH:
        return True
    ratio = len(ru_stripped) / len(en_stripped)
    return _PAIRING_MIN_LENGTH_RATIO <= ratio <= _PAIRING_MAX_LENGTH_RATIO


def _strip_implausible_pairings(
    annotations: list[FacsimileAnnotation],
) -> list[FacsimileAnnotation]:
    """Rewrite annotations whose RU translation fails the plausibility check.

    The annotation itself is preserved (so the EN caption still renders) but
    ``translated_text`` is cleared. Dropping the pair outright would hide a
    legitimate EN-only hotspot; keeping the stale translation would ship the
    user-visible wrong-tooltip defect. Clearing it yields the least-surprising
    behaviour and is also what ``_is_identical_translation`` already does when
    the translator returns the source text unchanged.

    Page-level escalation: when the implausible-pair rate on a page is high
    (``>= _PAGE_STALENESS_RATIO``), assume the RU IR is stale relative to the
    current EN IR and clear every translation on the page. Per-annotation
    length ratios that individually pass the plausibility check may still be
    wrong pairings (see S5U-697 for the motivating case where a 1.8x ratio
    slipped through the per-annotation check but came from a shuffled
    block_id map), so an aggregate signal is the only way to catch them
    without running a full content-based EN/RU alignment.
    """
    paired = [ann for ann in annotations if ann.translated_text]
    if paired:
        bad = sum(1 for ann in paired if not _is_plausible_pair(ann.text, ann.translated_text))
        if (bad / len(paired)) >= _PAGE_STALENESS_RATIO:
            return [
                ann.model_copy(update={"translated_text": ""}) if ann.translated_text else ann
                for ann in annotations
            ]

    result: list[FacsimileAnnotation] = []
    for ann in annotations:
        if ann.translated_text and not _is_plausible_pair(ann.text, ann.translated_text):
            result.append(ann.model_copy(update={"translated_text": ""}))
        else:
            result.append(ann)
    return result


def _contains_bbox(outer: NormRect, inner: NormRect) -> bool:
    """Return True when ``inner`` is (approximately) fully contained in ``outer``.

    Uses the intersection-over-inner-area ratio so that a small 1px extraction
    jitter on the boundary does not defeat the containment test.
    """
    inner_area = _bbox_area(inner)
    if inner_area <= 0:
        return False
    ix0 = max(outer.x0, inner.x0)
    iy0 = max(outer.y0, inner.y0)
    ix1 = min(outer.x1, inner.x1)
    iy1 = min(outer.y1, inner.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    intersection = (ix1 - ix0) * (iy1 - iy0)
    return (intersection / inner_area) >= _FULL_CONTAINMENT_RATIO


def _suppress_fully_occluded(
    annotations: list[FacsimileAnnotation],
) -> list[FacsimileAnnotation]:
    """Drop outer annotations that fully contain another annotation.

    Iterates pairwise; when A contains B (and A != B), A is dropped because
    B is the more specific, still-reachable hotspot. If A and B are
    mutually containing (same bbox), keep the one with higher priority as a
    stable tiebreak — this is a rare edge case from duplicate extraction.
    """
    if len(annotations) < 2:
        return list(annotations)
    dropped: set[int] = set()
    for i, outer in enumerate(annotations):
        if i in dropped:
            continue
        for j, inner in enumerate(annotations):
            if i == j or j in dropped:
                continue
            if not _contains_bbox(outer.bbox, inner.bbox):
                continue
            # If inner also contains outer, keep the higher-priority one.
            if _contains_bbox(inner.bbox, outer.bbox):
                if outer.priority >= inner.priority:
                    dropped.add(j)
                    continue
                dropped.add(i)
                break
            # Strict containment: drop the outer (less specific).
            dropped.add(i)
            break
    return [a for idx, a in enumerate(annotations) if idx not in dropped]
