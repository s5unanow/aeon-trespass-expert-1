"""Deterministic symbol template matching using OpenCV.

Optimised for multi-page runs: templates are loaded once into a
``TemplateCache`` and reused across pages.  Each symbol can now be
detected *multiple* times on a single page (NMS deduplication), and
scale search exits early when a near-perfect match is found.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from atr_schemas.common import Rect
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.symbol_catalog_v1 import SymbolCatalogV1, SymbolEntry
from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1

# Scale factors to try when matching templates against the rasterized page.
# Templates are at native pixel size; the page raster may be at 300 DPI,
# so the icon could appear 2-5x larger than the template.
_SCALE_FACTORS = [1.0, 2.0, 3.0, 4.0, 4.17, 5.0]

# If the best score at any scale exceeds this, skip remaining scales.
_EARLY_EXIT_SCORE = 0.98

# Minimum overlap (IoU) for NMS suppression.
_NMS_IOU_THRESHOLD = 0.3

# Secondary instances must score within this ratio of the best match.
# The same icon rendered identically produces near-identical scores;
# a >2% drop indicates the detection is matching noise.
_SECONDARY_SCORE_RATIO = 0.98


# ---------------------------------------------------------------------------
# Template cache
# ---------------------------------------------------------------------------


@dataclass
class _ScaledTemplate:
    """A single scale-variant of a template image."""

    scale: float
    gray: np.ndarray  # uint8 grayscale
    tw: int
    th: int


@dataclass
class _CachedEntry:
    """Pre-loaded template with all valid scaled variants."""

    symbol: SymbolEntry
    variants: list[_ScaledTemplate] = field(default_factory=list)


class TemplateCache:
    """Pre-loaded and pre-scaled template images.

    Create once per pipeline run (or per document) and pass into
    ``match_symbols`` for every page to avoid repeated disk I/O and
    rescaling.
    """

    def __init__(self) -> None:
        self._entries: list[_CachedEntry] = []

    @property
    def entries(self) -> list[_CachedEntry]:
        return self._entries

    @classmethod
    def from_catalog(
        cls,
        catalog: SymbolCatalogV1,
        *,
        repo_root: Path | None = None,
        page_h: int = 0,
        page_w: int = 0,
    ) -> TemplateCache:
        """Build cache by loading every template and pre-computing scales.

        If *page_h* / *page_w* are given, scaled variants that exceed the
        page dimensions are pruned immediately.
        """
        cache = cls()
        for symbol in catalog.symbols:
            template_path = Path(symbol.template_asset)
            if not template_path.is_absolute() and repo_root:
                template_path = repo_root / template_path
            if not template_path.exists():
                continue

            template_img = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
            if template_img is None:
                continue
            template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

            variants: list[_ScaledTemplate] = []
            for scale in _SCALE_FACTORS:
                th = int(template_gray.shape[0] * scale)
                tw = int(template_gray.shape[1] * scale)
                if th < 4 or tw < 4:
                    continue
                if page_h and th > page_h:
                    continue
                if page_w and tw > page_w:
                    continue
                scaled = cv2.resize(
                    template_gray, (tw, th), interpolation=cv2.INTER_LINEAR
                )
                variants.append(_ScaledTemplate(scale=scale, gray=scaled, tw=tw, th=th))

            if variants:
                cache._entries.append(_CachedEntry(symbol=symbol, variants=variants))

        return cache


# ---------------------------------------------------------------------------
# NMS helper
# ---------------------------------------------------------------------------


def _nms_boxes(
    boxes: list[tuple[int, int, int, int]],
    scores: list[float],
    iou_threshold: float,
) -> list[int]:
    """Non-maximum suppression over axis-aligned boxes.

    *boxes* are ``(x0, y0, x1, y1)`` in pixel coordinates.
    Returns indices of kept boxes sorted by descending score.
    """
    if not boxes:
        return []

    b = np.array(boxes, dtype=np.float64)
    s = np.array(scores, dtype=np.float64)
    order = s.argsort()[::-1]

    x0 = b[:, 0]
    y0 = b[:, 1]
    x1 = b[:, 2]
    y1 = b[:, 3]
    area = (x1 - x0) * (y1 - y0)

    keep: list[int] = []
    suppressed = np.zeros(len(boxes), dtype=bool)
    for idx in order:
        if suppressed[idx]:
            continue
        keep.append(int(idx))
        xx0 = np.maximum(x0[idx], x0)
        yy0 = np.maximum(y0[idx], y0)
        xx1 = np.minimum(x1[idx], x1)
        yy1 = np.minimum(y1[idx], y1)
        inter = np.maximum(0.0, xx1 - xx0) * np.maximum(0.0, yy1 - yy0)
        union = area[idx] + area - inter
        iou = np.where(union > 0, inter / union, 0.0)
        suppressed |= iou > iou_threshold

    return keep


# ---------------------------------------------------------------------------
# Single-symbol matching (used as thread task)
# ---------------------------------------------------------------------------


def _match_one_symbol(
    entry: _CachedEntry,
    page_gray: np.ndarray,
    page_h: int,
    page_w: int,
) -> list[tuple[float, int, int, int, int]]:
    """Match all instances of one symbol on a page.

    Returns list of ``(score, px, py, tw, th)`` tuples, one per instance.

    Uses iterative peak extraction: find the global-best match across all
    scales, record it, mask the region in every result map, and repeat
    until no peaks remain above threshold.  This naturally deduplicates
    cross-scale detections at the same physical location.
    """
    threshold = entry.symbol.match_threshold

    # 1. Pre-compute result maps for every viable scale
    result_maps: list[tuple[_ScaledTemplate, np.ndarray]] = []
    found_early_exit = False
    for variant in entry.variants:
        if variant.th > page_h or variant.tw > page_w:
            continue
        result = cv2.matchTemplate(
            page_gray, variant.gray, cv2.TM_CCOEFF_NORMED
        )
        result_maps.append((variant, result))

        if not found_early_exit:
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= _EARLY_EXIT_SCORE:
                found_early_exit = True
                # still keep this map, but skip remaining scales
                break

    if not result_maps:
        return []

    # 2. Iteratively extract best peaks with cross-scale masking.
    #    Secondary instances must score within _SECONDARY_SCORE_RATIO of
    #    the first (best) hit — identical icons produce near-identical
    #    scores, so a meaningful drop signals a false positive.
    hits: list[tuple[float, int, int, int, int]] = []
    _MAX_INSTANCES = 50  # safety cap
    first_score: float | None = None

    while len(hits) < _MAX_INSTANCES:
        best_score = -1.0
        best_idx = -1
        best_loc: Sequence[int] = (0, 0)

        for i, (_variant, rmap) in enumerate(result_maps):
            _, max_val, _, max_loc = cv2.minMaxLoc(rmap)
            if max_val > best_score:
                best_score = max_val
                best_idx = i
                best_loc = max_loc  # (x, y)

        if best_score < threshold:
            break

        # Secondary-instance quality gate
        if first_score is None:
            first_score = best_score
        elif best_score < first_score * _SECONDARY_SCORE_RATIO:
            break

        variant, _ = result_maps[best_idx]
        px, py = best_loc
        hits.append((best_score, px, py, variant.tw, variant.th))

        # Mask the detected region in ALL result maps so the same
        # physical location is not reported again at another scale.
        cx = px + variant.tw // 2
        cy = py + variant.th // 2
        for _i, (v, rmap) in enumerate(result_maps):
            radius = max(v.tw, v.th, variant.tw, variant.th)
            y0 = max(0, cy - v.th // 2 - radius)
            y1 = min(rmap.shape[0], cy - v.th // 2 + radius + 1)
            x0 = max(0, cx - v.tw // 2 - radius)
            x1 = min(rmap.shape[1], cx - v.tw // 2 + radius + 1)
            rmap[y0:y1, x0:x1] = -1.0

    return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_symbols(
    native_page: NativePageV1,
    page_image_path: Path,
    catalog: SymbolCatalogV1,
    *,
    repo_root: Path | None = None,
    template_cache: TemplateCache | None = None,
) -> SymbolMatchSetV1:
    """Detect symbols on a page image using multi-scale template matching.

    When *template_cache* is provided templates are not reloaded from disk,
    giving a significant speed-up on multi-page runs.
    """
    page_img = cv2.imread(str(page_image_path), cv2.IMREAD_COLOR)
    if page_img is None:
        msg = f"Could not read page image: {page_image_path}"
        raise FileNotFoundError(msg)

    page_gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
    page_h, page_w = page_gray.shape[:2]

    # Coordinate scale: pixel -> PDF points
    pdf_w = native_page.dimensions_pt.width
    pdf_h = native_page.dimensions_pt.height
    sx = pdf_w / page_w
    sy = pdf_h / page_h

    # Build or reuse template cache
    if template_cache is None:
        template_cache = TemplateCache.from_catalog(
            catalog, repo_root=repo_root, page_h=page_h, page_w=page_w,
        )

    # Match all symbols concurrently
    entries = template_cache.entries
    results_map: dict[int, list[tuple[float, int, int, int, int]]] = {}

    if len(entries) > 4:
        with ThreadPoolExecutor() as pool:
            futures = {
                i: pool.submit(_match_one_symbol, e, page_gray, page_h, page_w)
                for i, e in enumerate(entries)
            }
            for i, fut in futures.items():
                results_map[i] = fut.result()
    else:
        for i, e in enumerate(entries):
            results_map[i] = _match_one_symbol(e, page_gray, page_h, page_w)

    # Assemble matches
    matches: list[SymbolMatch] = []
    instance_counter = 0

    for i, entry in enumerate(entries):
        for score, px, py, tw, th in results_map.get(i, []):
            instance_counter += 1
            bbox = Rect(
                x0=round(px * sx, 1),
                y0=round(py * sy, 1),
                x1=round((px + tw) * sx, 1),
                y1=round((py + th) * sy, 1),
            )
            matches.append(
                SymbolMatch(
                    symbol_id=entry.symbol.symbol_id,
                    instance_id=f"syminst.{native_page.page_id}.{instance_counter:02d}",
                    bbox=bbox,
                    score=round(score, 4),
                    inline=entry.symbol.inline,
                )
            )

    return SymbolMatchSetV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
        matches=matches,
    )
