"""Unit tests for the visual symbol resolver."""

from atr_pipeline.services.assets.resolver import (
    ResolvedSymbolPlacement,
    SymbolResolverInput,
    _classify_anchor,
    _compute_insertion_x,
    _find_containing_region,
    _find_nearest_text_line,
    build_symbol_refs,
    resolve_symbols,
)
from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import RegionKind, SymbolAnchorKind
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.resolved_page_v1 import ResolvedRegion
from atr_schemas.symbol_match_set_v1 import SymbolMatch

_BODY_REGION = ResolvedRegion(
    region_id="r001",
    kind=RegionKind.BODY,
    bbox=Rect(x0=50, y0=50, x1=500, y1=700),
    norm_bbox=NormRect(x0=0.08, y0=0.06, x1=0.84, y1=0.83),
)

_TABLE_REGION = ResolvedRegion(
    region_id="r002",
    kind=RegionKind.TABLE_AREA,
    bbox=Rect(x0=50, y0=200, x1=500, y1=400),
    norm_bbox=NormRect(x0=0.08, y0=0.24, x1=0.84, y1=0.48),
)

_MARGIN_REGION = ResolvedRegion(
    region_id="r003",
    kind=RegionKind.MARGIN_NOTE,
    bbox=Rect(x0=10, y0=100, x1=45, y1=200),
    norm_bbox=NormRect(x0=0.02, y0=0.12, x1=0.08, y1=0.24),
)


def _span(
    span_id: str,
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> SpanEvidence:
    return SpanEvidence(
        span_id=span_id,
        text=text,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        font_name="body",
        font_size=10.0,
    )


def _match(
    symbol_id: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    score: float = 0.9,
) -> SymbolMatch:
    return SymbolMatch(
        symbol_id=symbol_id,
        instance_id=f"{symbol_id}.001",
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        score=score,
        inline=True,
    )


# --- _classify_anchor ---


class TestClassifyAnchor:
    def test_body_inline(self) -> None:
        """Symbol overlapping text line in body region → INLINE."""
        spans = [_span("s1", "Hello world", 100, 100, 200, 112)]
        bbox = Rect(x0=140, y0=100, x1=152, y1=112)
        result = _classify_anchor(bbox, _BODY_REGION, spans)
        assert result == SymbolAnchorKind.INLINE

    def test_left_of_text_prefix(self) -> None:
        """Symbol x-center before first char → PREFIX."""
        spans = [_span("s1", "Some text", 100, 100, 200, 112)]
        bbox = Rect(x0=70, y0=100, x1=82, y1=112)
        result = _classify_anchor(bbox, _BODY_REGION, spans)
        assert result == SymbolAnchorKind.PREFIX

    def test_table_small_cell_local(self) -> None:
        """Small symbol in TABLE_AREA → CELL_LOCAL."""
        spans = [_span("s1", "Cell", 100, 300, 140, 312)]
        bbox = Rect(x0=120, y0=300, x1=130, y1=310)  # area=100
        result = _classify_anchor(bbox, _TABLE_REGION, spans)
        assert result == SymbolAnchorKind.CELL_LOCAL

    def test_margin_note_region_annotation(self) -> None:
        """Any symbol in MARGIN_NOTE region → REGION_ANNOTATION."""
        spans = [_span("s1", "Note", 15, 150, 40, 162)]
        bbox = Rect(x0=20, y0=150, x1=32, y1=162)
        result = _classify_anchor(bbox, _MARGIN_REGION, spans)
        assert result == SymbolAnchorKind.REGION_ANNOTATION

    def test_no_line_spans_region_annotation(self) -> None:
        """No nearby text line → REGION_ANNOTATION."""
        bbox = Rect(x0=100, y0=500, x1=112, y1=512)
        result = _classify_anchor(bbox, _BODY_REGION, [])
        assert result == SymbolAnchorKind.REGION_ANNOTATION

    def test_near_text_block_attached(self) -> None:
        """Symbol near text but not horizontally overlapping → BLOCK_ATTACHED."""
        spans = [_span("s1", "Body text", 100, 100, 200, 112)]
        # Symbol is to the right of text, on same line
        bbox = Rect(x0=210, y0=100, x1=222, y1=112)
        result = _classify_anchor(bbox, _BODY_REGION, spans)
        assert result == SymbolAnchorKind.BLOCK_ATTACHED


# --- _find_containing_region ---


class TestFindContainingRegion:
    def test_inside_region(self) -> None:
        bbox = Rect(x0=100, y0=100, x1=112, y1=112)
        result = _find_containing_region(bbox, [_BODY_REGION, _TABLE_REGION])
        assert result == _BODY_REGION

    def test_outside_all_regions(self) -> None:
        bbox = Rect(x0=550, y0=800, x1=562, y1=812)
        result = _find_containing_region(bbox, [_BODY_REGION])
        assert result is None

    def test_boundary_center_inside(self) -> None:
        """Symbol center is inside, even though bbox extends outside."""
        bbox = Rect(x0=48, y0=48, x1=60, y1=60)
        # Center is (54, 54) which is inside BODY_REGION (50-500, 50-700)
        result = _find_containing_region(bbox, [_BODY_REGION])
        assert result == _BODY_REGION


# --- _find_nearest_text_line ---


class TestFindNearestTextLine:
    def test_within_line(self) -> None:
        spans = [
            _span("s1", "Hello", 100, 100, 150, 112),
            _span("s2", "world", 155, 100, 210, 112),
        ]
        bbox = Rect(x0=130, y0=100, x1=142, y1=112)
        result = _find_nearest_text_line(bbox, spans)
        assert len(result) == 2

    def test_between_lines(self) -> None:
        """Symbol vertically between two lines → nearest one."""
        line1 = [_span("s1", "Line one", 100, 100, 200, 112)]
        line2 = [_span("s2", "Line two", 100, 130, 200, 142)]
        bbox = Rect(x0=130, y0=110, x1=142, y1=122)
        result = _find_nearest_text_line(bbox, line1 + line2)
        # Closer to line1 (y center 106) than line2 (y center 136)
        assert result == line1

    def test_no_spans(self) -> None:
        bbox = Rect(x0=100, y0=100, x1=112, y1=112)
        result = _find_nearest_text_line(bbox, [])
        assert result == []

    def test_too_far_from_lines(self) -> None:
        """Symbol far below all text lines → empty."""
        spans = [_span("s1", "Text", 100, 100, 200, 112)]
        bbox = Rect(x0=100, y0=200, x1=112, y1=212)
        result = _find_nearest_text_line(bbox, spans)
        assert result == []


# --- _compute_insertion_x ---


class TestComputeInsertionX:
    def test_start_of_text(self) -> None:
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        bbox = Rect(x0=98, y0=100, x1=106, y1=112)
        x = _compute_insertion_x(bbox, spans)
        assert x == 100.0  # Closest to span start

    def test_middle_of_text(self) -> None:
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        bbox = Rect(x0=120, y0=100, x1=130, y1=112)
        x = _compute_insertion_x(bbox, spans)
        # Symbol center at 125, chars at 100,110,120,130,140,150
        assert 120.0 <= x <= 130.0

    def test_end_of_text(self) -> None:
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        bbox = Rect(x0=145, y0=100, x1=157, y1=112)
        x = _compute_insertion_x(bbox, spans)
        assert x == 150.0  # End of span

    def test_empty_spans(self) -> None:
        bbox = Rect(x0=100, y0=100, x1=112, y1=112)
        x = _compute_insertion_x(bbox, [])
        # Falls back to symbol center
        assert x == 106.0


# --- resolve_symbols (integration) ---


class TestResolveSymbols:
    def test_mixed_anchor_types(self) -> None:
        spans = [
            _span("s1", "Some text here", 100, 100, 250, 112),
        ]
        matches = [
            # Inline: overlaps text
            _match("sym.shield", 140, 100, 152, 112),
            # Prefix: left of text
            _match("sym.bullet", 70, 100, 82, 112),
        ]
        inp = SymbolResolverInput(
            matches=matches,
            spans=spans,
            regions=[_BODY_REGION],
            page_id="p0001",
        )
        placements = resolve_symbols(inp)

        assert len(placements) == 2
        assert placements[0].anchor_kind == SymbolAnchorKind.INLINE
        assert placements[0].insertion_x is not None
        assert placements[1].anchor_kind == SymbolAnchorKind.PREFIX
        assert placements[1].insertion_x is None

    def test_empty_inputs(self) -> None:
        inp = SymbolResolverInput(
            matches=[],
            spans=[],
            regions=[],
            page_id="p0001",
        )
        assert resolve_symbols(inp) == []

    def test_no_regions_fallback(self) -> None:
        """Symbols near text but no regions still classify by line geometry."""
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        matches = [_match("sym.icon", 120, 100, 132, 112)]
        inp = SymbolResolverInput(
            matches=matches,
            spans=spans,
            regions=[],
            page_id="p0001",
        )
        placements = resolve_symbols(inp)
        assert len(placements) == 1
        assert placements[0].anchor_kind == SymbolAnchorKind.INLINE

    def test_non_inline_matches_skipped(self) -> None:
        m = SymbolMatch(
            symbol_id="sym.bg",
            bbox=Rect(x0=0, y0=0, x1=500, y1=700),
            score=0.8,
            inline=False,
        )
        inp = SymbolResolverInput(
            matches=[m],
            spans=[_span("s1", "Text", 100, 100, 200, 112)],
            regions=[_BODY_REGION],
            page_id="p0001",
        )
        assert resolve_symbols(inp) == []


# --- build_symbol_refs ---


class TestBuildSymbolRefs:
    def test_converts_placements(self) -> None:
        m = _match("sym.shield", 100, 100, 112, 112, score=0.95)
        placement = ResolvedSymbolPlacement(
            match=m,
            anchor_kind=SymbolAnchorKind.INLINE,
            confidence=0.95,
            evidence_ids=["e.img.001"],
        )
        refs = build_symbol_refs([placement])
        assert len(refs) == 1
        assert refs[0].symbol_id == "sym.shield"
        assert refs[0].anchor_kind == SymbolAnchorKind.INLINE
        assert refs[0].confidence == 0.95
        assert refs[0].evidence_ids == ["e.img.001"]
