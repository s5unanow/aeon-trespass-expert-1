"""Pairing-stability and occlusion-suppression helpers for facsimile annotations.

Extracted from ``annotation_builder.py`` in S5U-697 round-2 to keep the
builder module under the 400-line source ceiling. These helpers implement
the three defences the Linear issue's "Must refuse" section requires:

* bbox-finite validation (both raw-coord and normalized),
* EN/RU length-ratio plausibility check (per-annotation and page-level),
* fully-occluded outer-hotspot suppression with mutual-containment tiebreak.

See the module docstring in ``annotation_builder.py`` for the broader
pipeline context.
"""

from __future__ import annotations

import math

from atr_schemas.common import NormRect
from atr_schemas.render_page_v1 import FacsimileAnnotation

# S5U-697 pairing-stability thresholds. A stale RU IR produces `block_id`
# matches whose translated text has wildly different length from the English
# source; real translations cluster within a factor of ~2x. These bounds are
# intentionally generous (5x / 0.2x) so that abbreviation-heavy pairs
# (e.g. "HP" -> "zdorove") still pass, but multi-paragraph leakage is caught.
PAIRING_MAX_LENGTH_RATIO = 5.0
PAIRING_MIN_LENGTH_RATIO = 0.2
PAIRING_MIN_EN_LENGTH = 4  # below this we don't have enough signal to judge

# S5U-697 page-level staleness threshold. If >=30% of paired EN/RU blocks on
# a page fail the per-annotation length-ratio plausibility check, the entire
# RU IR is treated as stale (generated from a different extraction run than
# the current EN IR). In that case every translated_text on the page is
# cleared — the reader will show EN-only tooltips rather than ship confident
# but wrong pairings. This is the "fail closed" escape hatch the issue asks
# for when tooltip mappings reference stale content.
PAGE_STALENESS_RATIO = 0.30

# Bbox overlap suppression threshold. A bbox is "fully contained" if >=90% of
# its area lies inside another bbox; the *outer* (less-specific) annotation
# is dropped so the inner hotspot stays reachable. 90% rather than 100% to
# tolerate 1-pixel extractor jitter.
FULL_CONTAINMENT_RATIO = 0.9


def bbox_area(bbox: NormRect) -> float:
    """Compute normalized area of a bounding box (clamped to >= 0)."""
    w = max(0.0, bbox.x1 - bbox.x0)
    h = max(0.0, bbox.y1 - bbox.y0)
    return w * h


def is_bbox_valid(bbox: NormRect) -> bool:
    """Return True iff bbox coordinates are finite and area is positive.

    Zero-width or zero-height bboxes cannot host a clickable marker
    meaningfully, and non-finite coordinates would break every downstream
    overlap / area calculation silently.
    """
    coords = (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    if not all(math.isfinite(c) for c in coords):
        return False
    return not (bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0)


def is_plausible_pair(en_text: str, ru_text: str) -> bool:
    """Return True when EN/RU texts could plausibly be translations of each other.

    Uses a length-ratio heuristic: real translations cluster around 1x (a bit
    higher for Cyrillic expansion, lower for very terse RU labels). Pairs that
    exceed ``PAIRING_MAX_LENGTH_RATIO`` or fall below ``PAIRING_MIN_LENGTH_RATIO``
    are treated as stale-IR leakage.

    Short EN texts (``< PAIRING_MIN_EN_LENGTH`` chars) are always considered
    plausible — with so little signal, a length check produces more false
    positives than it catches true mismatches.
    """
    en_stripped = en_text.strip()
    ru_stripped = ru_text.strip()
    if not en_stripped or not ru_stripped:
        return True  # caller handles the empty-translation case separately
    if len(en_stripped) < PAIRING_MIN_EN_LENGTH:
        return True
    ratio = len(ru_stripped) / len(en_stripped)
    return PAIRING_MIN_LENGTH_RATIO <= ratio <= PAIRING_MAX_LENGTH_RATIO


def strip_implausible_pairings(
    annotations: list[FacsimileAnnotation],
) -> list[FacsimileAnnotation]:
    """Rewrite annotations whose RU translation fails the plausibility check.

    The annotation itself is preserved (so the EN caption still renders) but
    ``translated_text`` is cleared. Dropping the pair outright would hide a
    legitimate EN-only hotspot; keeping the stale translation would ship the
    user-visible wrong-tooltip defect. Clearing it yields the least-surprising
    behaviour and is also what the caller's existing identical-translation
    filter already does when the translator returns the source text unchanged.

    Page-level escalation: when the implausible-pair rate on a page is high
    (``>= PAGE_STALENESS_RATIO``), assume the RU IR is stale relative to the
    current EN IR and clear every translation on the page. Per-annotation
    length ratios that individually pass the plausibility check may still be
    wrong pairings (see S5U-697 for the motivating case where a 1.8x ratio
    slipped through the per-annotation check but came from a shuffled
    block_id map), so an aggregate signal is the only way to catch them
    without running a full content-based EN/RU alignment.
    """
    paired = [ann for ann in annotations if ann.translated_text]
    if paired:
        bad = sum(1 for ann in paired if not is_plausible_pair(ann.text, ann.translated_text))
        if (bad / len(paired)) >= PAGE_STALENESS_RATIO:
            return [
                ann.model_copy(update={"translated_text": ""}) if ann.translated_text else ann
                for ann in annotations
            ]

    result: list[FacsimileAnnotation] = []
    for ann in annotations:
        if ann.translated_text and not is_plausible_pair(ann.text, ann.translated_text):
            result.append(ann.model_copy(update={"translated_text": ""}))
        else:
            result.append(ann)
    return result


def contains_bbox(outer: NormRect, inner: NormRect) -> bool:
    """Return True when ``inner`` is (approximately) fully contained in ``outer``.

    Uses the intersection-over-inner-area ratio so that a small 1px extraction
    jitter on the boundary does not defeat the containment test.
    """
    inner_area = bbox_area(inner)
    if inner_area <= 0:
        return False
    ix0 = max(outer.x0, inner.x0)
    iy0 = max(outer.y0, inner.y0)
    ix1 = min(outer.x1, inner.x1)
    iy1 = min(outer.y1, inner.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    intersection = (ix1 - ix0) * (iy1 - iy0)
    return (intersection / inner_area) >= FULL_CONTAINMENT_RATIO


def suppress_fully_occluded(
    annotations: list[FacsimileAnnotation],
) -> list[FacsimileAnnotation]:
    """Drop outer annotations that fully contain another annotation.

    Iterates pairwise; when A contains B (and A != B), A is dropped because
    B is the more specific, still-reachable hotspot. If A and B are
    mutually containing (near-identical bboxes — can happen when the 0.9
    containment threshold triggers in both directions on boxes that differ
    only by 1-pixel extraction jitter), drop the larger-area one; ties
    break on priority then on index order for determinism.
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
            if not contains_bbox(outer.bbox, inner.bbox):
                continue
            # If inner also contains outer, they are near-identical. Keep
            # the smaller-area annotation (or higher priority on area tie,
            # or lower-index on priority tie) so the user-visible hotspot
            # is the most-specific one.
            if contains_bbox(inner.bbox, outer.bbox):
                outer_area = bbox_area(outer.bbox)
                inner_area = bbox_area(inner.bbox)
                if outer_area > inner_area or (
                    outer_area == inner_area
                    and (
                        inner.priority > outer.priority
                        or (inner.priority == outer.priority and j < i)
                    )
                ):
                    dropped.add(i)
                    break
                dropped.add(j)
                continue
            # Strict containment: drop the outer (less specific).
            dropped.add(i)
            break
    return [a for idx, a in enumerate(annotations) if idx not in dropped]
