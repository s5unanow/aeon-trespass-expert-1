"""Span classification and grouping primitives.

Extracted from ``real_block_builder`` in S5U-710. No behavior changes —
these helpers were moved verbatim to keep ``real_block_builder.py``
under the 400-line ceiling. The primitives here are consumed by the
main ``build_page_ir_real`` orchestrator and by the sibling icon /
table / figure extraction modules.
"""

from __future__ import annotations

import re

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.text_normalize import normalize_text_inlines
from atr_schemas.common import Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.page_ir_v1 import TextInline

# Horizontal gap (pt) below which spans are treated as the same word.
_WORD_GAP_THRESHOLD = 1.5

# Standalone numbered step: "1", "2.", "3)", "10:", etc.
_NUMBERED_STEP_RE = re.compile(r"^\d{1,3}[.):]*$")


def _bbox_from_spans(spans: list[SpanEvidence]) -> Rect | None:
    """Compute bounding box union from constituent spans."""
    if not spans:
        return None
    first = spans[0].bbox
    x0, y0, x1, y1 = first.x0, first.y0, first.x1, first.y1
    for s in spans[1:]:
        x0 = min(x0, s.bbox.x0)
        y0 = min(y0, s.bbox.y0)
        x1 = max(x1, s.bbox.x1)
        y1 = max(y1, s.bbox.y1)
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _classify_span(span: SpanEvidence, cfg: StructureConfig) -> str:
    """Classify a span into a structural role."""
    if span.bbox.y0 >= cfg.footer_y_threshold:
        return "footer"
    if span.font_name in cfg.heading_fonts and span.font_size >= cfg.heading_min_size:
        return "heading"
    if span.font_name in cfg.decorative_fonts:
        return "decorative"
    # Heading font at sub-body size → diagram/figure label text, not prose.
    if span.font_name in cfg.heading_fonts and span.font_size < cfg.body_size_min:
        return "diagram_label"
    if span.font_name == cfg.bold_font and span.font_size >= cfg.subheading_bold_min_size:
        return "subheading"
    if span.font_name == cfg.dingbat_font:
        return "bullet"
    if span.font_name == cfg.italic_font:
        return "italic"
    if span.font_name == cfg.bold_font:
        return "bold"
    if span.font_name == cfg.bold_italic_font:
        return "bold_italic"
    return "body"


def _same_line(a: SpanEvidence, b: SpanEvidence, tolerance: float = 3.0) -> bool:
    """Check if two spans are on the same line (similar y position)."""
    return abs(a.bbox.y0 - b.bbox.y0) < tolerance


def _group_spans_by_line(
    spans: list[SpanEvidence],
    tolerance: float = 3.0,
) -> list[list[SpanEvidence]]:
    """Group consecutive spans into visual lines by y-position proximity."""
    if not spans:
        return []
    lines: list[list[SpanEvidence]] = [[spans[0]]]
    for s in spans[1:]:
        if _same_line(lines[-1][-1], s, tolerance):
            lines[-1].append(s)
        else:
            lines.append([s])
    return lines


def _spans_to_text_inline(
    spans: list[SpanEvidence],
    cfg: StructureConfig,
) -> list[TextInline]:
    """Convert a group of spans into TextInline nodes, merging adjacent same-role spans."""
    if not spans:
        return []

    inlines: list[TextInline] = []
    prev_span: SpanEvidence | None = None
    for span in spans:
        role = _classify_span(span, cfg)
        marks: list[str] = []
        if role == "bold" or role == "subheading":
            marks = ["bold"]
        elif role == "italic":
            marks = ["italic"]
        elif role == "bold_italic":
            marks = ["bold", "italic"]

        text = span.text
        if not text.strip():
            continue

        # Insert whitespace between non-adjacent spans (but not for
        # horizontally touching spans like small-caps word parts).
        if inlines and prev_span is not None:
            prev_text = inlines[-1].text
            if prev_text and text and not prev_text[-1].isspace() and not text[0].isspace():
                gap = span.bbox.x0 - prev_span.bbox.x1
                if abs(gap) > _WORD_GAP_THRESHOLD:
                    text = " " + text

        # Merge with previous if same marks
        if inlines and inlines[-1].marks == marks:
            inlines[-1] = TextInline(
                text=inlines[-1].text + text,
                marks=marks,
                lang=LanguageCode.EN,
            )
        else:
            inlines.append(TextInline(text=text, marks=marks, lang=LanguageCode.EN))
        prev_span = span

    return normalize_text_inlines(inlines)
