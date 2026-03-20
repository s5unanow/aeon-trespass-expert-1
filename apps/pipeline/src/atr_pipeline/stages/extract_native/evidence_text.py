"""Extract char, line, and text-span evidence from a PyMuPDF page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.evidence_primitives_v1 import (
    EvidenceChar,
    EvidenceLine,
    EvidenceTextSpan,
)

if TYPE_CHECKING:
    import fitz


def normalize_rect(rect: Rect, dims: PageDimensions) -> NormRect:
    """Convert PDF-point rect to normalised [0,1] page space, clamped."""
    return NormRect(
        x0=max(0.0, min(1.0, rect.x0 / dims.width)) if dims.width else 0.0,
        y0=max(0.0, min(1.0, rect.y0 / dims.height)) if dims.height else 0.0,
        x1=max(0.0, min(1.0, rect.x1 / dims.width)) if dims.width else 0.0,
        y1=max(0.0, min(1.0, rect.y1 / dims.height)) if dims.height else 0.0,
    )


def extract_text_evidence(
    page: fitz.Page,
    dims: PageDimensions,
) -> tuple[list[EvidenceChar], list[EvidenceLine], list[EvidenceTextSpan]]:
    """Extract char-, line-, and span-level text evidence using rawdict.

    Returns:
        Tuple of (chars, lines, spans) evidence entity lists.
    """
    chars: list[EvidenceChar] = []
    lines: list[EvidenceLine] = []
    spans: list[EvidenceTextSpan] = []

    char_idx = 0
    line_idx = 0
    span_idx = 0

    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for raw_line in block.get("lines", []):
            line_char_ids: list[str] = []
            line_text_parts: list[str] = []
            line_bbox = _init_bbox()

            direction = _writing_direction(raw_line.get("dir", (1.0, 0.0)))

            for raw_span in raw_line.get("spans", []):
                span_char_ids: list[str] = []
                span_bbox = _init_bbox()
                font_name = raw_span.get("font", "")
                font_size = raw_span.get("size", 0.0)
                flags = raw_span.get("flags", 0)
                color = raw_span.get("color", 0)

                for raw_char in raw_span.get("chars", []):
                    cb = raw_char.get("bbox", (0, 0, 0, 0))
                    char_rect = Rect(x0=cb[0], y0=cb[1], x1=cb[2], y1=cb[3])
                    eid = f"e.char.{char_idx:03d}"
                    chars.append(
                        EvidenceChar(
                            evidence_id=eid,
                            text=raw_char.get("c", ""),
                            bbox=char_rect,
                            norm_bbox=normalize_rect(char_rect, dims),
                            font_name=font_name,
                            font_size=font_size,
                            flags=flags,
                            color=color,
                        )
                    )
                    span_char_ids.append(eid)
                    line_char_ids.append(eid)
                    span_bbox = _union_bbox(span_bbox, char_rect)
                    line_bbox = _union_bbox(line_bbox, char_rect)
                    char_idx += 1

                span_text = raw_span.get("text", "")
                line_text_parts.append(span_text)

                if span_char_ids:
                    spans.append(
                        EvidenceTextSpan(
                            evidence_id=f"e.span.{span_idx:03d}",
                            text=span_text,
                            bbox=span_bbox,
                            norm_bbox=normalize_rect(span_bbox, dims),
                            font_name=font_name,
                            font_size=font_size,
                            flags=flags,
                            color=color,
                            char_ids=span_char_ids,
                        )
                    )
                    span_idx += 1

            if line_char_ids:
                lines.append(
                    EvidenceLine(
                        evidence_id=f"e.line.{line_idx:03d}",
                        text="".join(line_text_parts),
                        bbox=line_bbox,
                        norm_bbox=normalize_rect(line_bbox, dims),
                        char_ids=line_char_ids,
                        writing_direction=direction,
                    )
                )
                line_idx += 1

    return chars, lines, spans


def _writing_direction(dir_tuple: tuple[float, ...]) -> str:
    """Determine writing direction from PyMuPDF line dir vector."""
    if len(dir_tuple) >= 2 and dir_tuple[0] < 0:
        return "rtl"
    return "ltr"


def _init_bbox() -> Rect:
    """Return a sentinel bbox for union accumulation."""
    return Rect(x0=float("inf"), y0=float("inf"), x1=0.0, y1=0.0)


def _union_bbox(a: Rect, b: Rect) -> Rect:
    """Return the union bounding box of two rects."""
    return Rect(
        x0=min(a.x0, b.x0),
        y0=min(a.y0, b.y0),
        x1=max(a.x1, b.x1),
        y1=max(a.y1, b.y1),
    )
