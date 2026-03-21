"""Unit tests for the inline icon placer."""

from atr_pipeline.services.assets.inline_placer import place_icons_in_inlines
from atr_pipeline.services.assets.resolver import ResolvedSymbolPlacement
from atr_schemas.common import Rect
from atr_schemas.enums import LanguageCode, SymbolAnchorKind
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.page_ir_v1 import IconInline, TextInline
from atr_schemas.symbol_match_set_v1 import SymbolMatch


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


def _placement(
    symbol_id: str,
    anchor: SymbolAnchorKind,
    bbox: Rect,
    *,
    insertion_x: float | None = None,
    score: float = 0.9,
) -> ResolvedSymbolPlacement:
    return ResolvedSymbolPlacement(
        match=_match(symbol_id, bbox.x0, bbox.y0, bbox.x1, bbox.y1, score=score),
        anchor_kind=anchor,
        insertion_x=insertion_x,
        confidence=score,
    )


class TestPlaceIconsInInlines:
    def test_inline_at_correct_position(self) -> None:
        """INLINE icon inserted within text, not at end."""
        spans = [_span("s1", "Hello world", 100, 100, 210, 112)]
        text_inlines = [TextInline(text="Hello world", lang=LanguageCode.EN)]
        placements = [
            _placement(
                "sym.icon",
                SymbolAnchorKind.INLINE,
                Rect(x0=140, y0=100, x1=152, y1=112),
                insertion_x=140.0,
            ),
        ]

        result = place_icons_in_inlines(text_inlines, placements, spans)

        # Icon should be present and not be the last element
        icons = [n for n in result if isinstance(n, IconInline)]
        assert len(icons) == 1
        assert icons[0].symbol_id == "sym.icon"
        assert icons[0].anchor_kind == SymbolAnchorKind.INLINE

    def test_prefix_prepended(self) -> None:
        """PREFIX icon appears before all text."""
        spans = [_span("s1", "Item text", 100, 100, 190, 112)]
        text_inlines = [TextInline(text="Item text", lang=LanguageCode.EN)]
        placements = [
            _placement("sym.bullet", SymbolAnchorKind.PREFIX, Rect(x0=70, y0=100, x1=82, y1=112)),
        ]

        result = place_icons_in_inlines(text_inlines, placements, spans)

        assert len(result) == 2
        assert isinstance(result[0], IconInline)
        assert result[0].symbol_id == "sym.bullet"
        assert result[0].anchor_kind == SymbolAnchorKind.PREFIX
        assert isinstance(result[1], TextInline)

    def test_multiple_icons_ordered(self) -> None:
        """Multiple INLINE icons are inserted in x-order."""
        spans = [_span("s1", "A long sentence here", 100, 100, 300, 112)]
        text_inlines = [TextInline(text="A long sentence here", lang=LanguageCode.EN)]
        placements = [
            _placement(
                "sym.second",
                SymbolAnchorKind.INLINE,
                Rect(x0=200, y0=100, x1=212, y1=112),
                insertion_x=200.0,
            ),
            _placement(
                "sym.first",
                SymbolAnchorKind.INLINE,
                Rect(x0=130, y0=100, x1=142, y1=112),
                insertion_x=130.0,
            ),
        ]

        result = place_icons_in_inlines(text_inlines, placements, spans)

        icons = [n for n in result if isinstance(n, IconInline)]
        assert len(icons) == 2
        # First icon should be sym.first (lower insertion_x)
        assert icons[0].symbol_id == "sym.first"
        assert icons[1].symbol_id == "sym.second"

    def test_no_placements_passthrough(self) -> None:
        """No placements → text inlines returned unchanged."""
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        text_inlines = [TextInline(text="Hello", lang=LanguageCode.EN)]

        result = place_icons_in_inlines(text_inlines, [], spans)

        assert len(result) == 1
        assert isinstance(result[0], TextInline)
        assert result[0].text == "Hello"

    def test_block_attached_filtered_out(self) -> None:
        """BLOCK_ATTACHED placements are not inserted into inlines."""
        spans = [_span("s1", "Text", 100, 100, 150, 112)]
        text_inlines = [TextInline(text="Text", lang=LanguageCode.EN)]
        placements = [
            _placement(
                "sym.attached",
                SymbolAnchorKind.BLOCK_ATTACHED,
                Rect(x0=200, y0=100, x1=212, y1=112),
            ),
        ]

        result = place_icons_in_inlines(text_inlines, placements, spans)

        assert len(result) == 1
        assert isinstance(result[0], TextInline)

    def test_icon_confidence_and_anchor_set(self) -> None:
        """IconInline carries anchor_kind and confidence from placement."""
        spans = [_span("s1", "Text", 100, 100, 150, 112)]
        text_inlines = [TextInline(text="Text", lang=LanguageCode.EN)]
        placements = [
            _placement(
                "sym.icon",
                SymbolAnchorKind.INLINE,
                Rect(x0=120, y0=100, x1=132, y1=112),
                insertion_x=120.0,
                score=0.87,
            ),
        ]

        result = place_icons_in_inlines(text_inlines, placements, spans)

        icons = [n for n in result if isinstance(n, IconInline)]
        assert len(icons) == 1
        assert icons[0].anchor_kind == SymbolAnchorKind.INLINE
        assert icons[0].confidence == 0.87

    def test_out_of_y_range_filtered(self) -> None:
        """Placements outside the block y-range are ignored."""
        spans = [_span("s1", "Text", 100, 100, 150, 112)]
        text_inlines = [TextInline(text="Text", lang=LanguageCode.EN)]
        placements = [
            _placement(
                "sym.far",
                SymbolAnchorKind.INLINE,
                Rect(x0=120, y0=300, x1=132, y1=312),  # y far below
                insertion_x=120.0,
            ),
        ]

        result = place_icons_in_inlines(text_inlines, placements, spans)

        assert len(result) == 1
        assert isinstance(result[0], TextInline)
