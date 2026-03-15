"""Deterministic symbol template matching using OpenCV."""

from __future__ import annotations

from pathlib import Path

import cv2

from atr_schemas.common import Rect
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.symbol_catalog_v1 import SymbolCatalogV1
from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1

# Scale factors to try when matching templates against the rasterized page.
# Templates are at native pixel size; the page raster may be at 300 DPI,
# so the icon could appear 2-5x larger than the template.
_SCALE_FACTORS = [1.0, 2.0, 3.0, 4.0, 4.17, 5.0]


def match_symbols(
    native_page: NativePageV1,
    page_image_path: Path,
    catalog: SymbolCatalogV1,
    *,
    repo_root: Path | None = None,
) -> SymbolMatchSetV1:
    """Detect symbols on a page image using multi-scale template matching."""
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

    matches: list[SymbolMatch] = []
    instance_counter = 0

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

        best_score = 0.0
        best_loc: tuple[int, int] = (0, 0)
        best_tw = 0
        best_th = 0

        # Try multiple scales
        for scale in _SCALE_FACTORS:
            th = int(template_gray.shape[0] * scale)
            tw = int(template_gray.shape[1] * scale)
            if th < 4 or tw < 4 or th > page_h or tw > page_w:
                continue

            scaled = cv2.resize(template_gray, (tw, th), interpolation=cv2.INTER_LINEAR)
            result = cv2.matchTemplate(page_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_score:
                best_score = max_val
                best_loc = max_loc  # (x, y) in pixel coords
                best_tw = tw
                best_th = th

        if best_score >= symbol.match_threshold:
            instance_counter += 1
            px, py = best_loc
            bbox = Rect(
                x0=round(px * sx, 1),
                y0=round(py * sy, 1),
                x1=round((px + best_tw) * sx, 1),
                y1=round((py + best_th) * sy, 1),
            )
            matches.append(
                SymbolMatch(
                    symbol_id=symbol.symbol_id,
                    instance_id=f"syminst.{native_page.page_id}.{instance_counter:02d}",
                    bbox=bbox,
                    score=round(best_score, 4),
                    inline=symbol.inline,
                )
            )

    return SymbolMatchSetV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
        matches=matches,
    )
