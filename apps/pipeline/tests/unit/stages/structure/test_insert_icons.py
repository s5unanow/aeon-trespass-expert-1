"""Tests for position-aware icon insertion in the real block builder."""

from atr_pipeline.stages.structure.real_block_builder import _insert_icons
from atr_schemas.common import Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.page_ir_v1 import IconInline, TextInline
from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1


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


def _symbols(
    page_id: str,
    matches: list[SymbolMatch],
) -> SymbolMatchSetV1:
    return SymbolMatchSetV1(
        document_id="test",
        page_id=page_id,
        matches=matches,
    )


def _match(
    symbol_id: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    inline: bool = True,
    score: float = 0.9,
) -> SymbolMatch:
    return SymbolMatch(
        symbol_id=symbol_id,
        instance_id=f"{symbol_id}.001",
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        score=score,
        inline=inline,
    )


class TestInsertIconsPositioning:
    """Icon insertion places icons at correct x-positions, not appended."""

    def test_icon_before_text(self) -> None:
        """Icon whose x is before text start appears first."""
        spans = [_span("s1", "Hello world", 100, 100, 210, 112)]
        inlines = [TextInline(text="Hello world", lang=LanguageCode.EN)]
        symbols = _symbols(
            "p0001",
            [_match("sym.arrow", 80, 100, 92, 112)],
        )

        result = _insert_icons(inlines, spans, symbols, "p0001")

        assert len(result) == 2
        assert isinstance(result[0], IconInline)
        assert result[0].symbol_id == "sym.arrow"
        assert isinstance(result[1], TextInline)

    def test_icon_after_text(self) -> None:
        """Icon whose x is past all text appears last."""
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        inlines = [TextInline(text="Hello", lang=LanguageCode.EN)]
        symbols = _symbols(
            "p0001",
            [_match("sym.end", 200, 100, 212, 112)],
        )

        result = _insert_icons(inlines, spans, symbols, "p0001")

        assert len(result) == 2
        assert isinstance(result[0], TextInline)
        assert isinstance(result[1], IconInline)
        assert result[1].symbol_id == "sym.end"

    def test_icon_between_text_inlines(self) -> None:
        """Icon x-position between two text inlines lands in the middle."""
        # Two spans: "Hello " at x=100..160, "world" at x=160..210
        spans = [
            _span("s1", "Hello ", 100, 100, 160, 112),
            _span("s2", "world", 160, 100, 210, 112),
        ]
        inlines = [
            TextInline(text="Hello ", lang=LanguageCode.EN),
            TextInline(text="world", lang=LanguageCode.EN),
        ]
        # Icon at x=155, between the two spans
        symbols = _symbols(
            "p0001",
            [_match("sym.mid", 155, 100, 167, 112)],
        )

        result = _insert_icons(inlines, spans, symbols, "p0001")

        assert len(result) == 3
        assert isinstance(result[0], TextInline)
        assert result[0].text == "Hello "
        assert isinstance(result[1], IconInline)
        assert result[1].symbol_id == "sym.mid"
        assert isinstance(result[2], TextInline)
        assert result[2].text == "world"

    def test_multiple_icons_ordered_by_x(self) -> None:
        """Multiple icons are inserted in left-to-right x order."""
        spans = [_span("s1", "A long sentence here", 100, 100, 300, 112)]
        inlines = [TextInline(text="A long sentence here", lang=LanguageCode.EN)]
        symbols = _symbols(
            "p0001",
            [
                _match("sym.second", 250, 100, 262, 112),
                _match("sym.first", 80, 100, 92, 112),
            ],
        )

        result = _insert_icons(inlines, spans, symbols, "p0001")

        icons = [n for n in result if isinstance(n, IconInline)]
        assert len(icons) == 2
        assert icons[0].symbol_id == "sym.first"
        assert icons[1].symbol_id == "sym.second"

    def test_no_matches_returns_inlines(self) -> None:
        """No symbol matches → text inlines returned unchanged."""
        spans = [_span("s1", "Hello", 100, 100, 150, 112)]
        inlines = [TextInline(text="Hello", lang=LanguageCode.EN)]
        symbols = _symbols("p0001", [])

        result = _insert_icons(inlines, spans, symbols, "p0001")

        assert len(result) == 1
        assert isinstance(result[0], TextInline)

    def test_non_inline_matches_filtered(self) -> None:
        """Matches with inline=False are excluded."""
        spans = [_span("s1", "Text", 100, 100, 150, 112)]
        inlines = [TextInline(text="Text", lang=LanguageCode.EN)]
        symbols = _symbols(
            "p0001",
            [_match("sym.block", 120, 100, 132, 112, inline=False)],
        )

        result = _insert_icons(inlines, spans, symbols, "p0001")

        assert len(result) == 1
        assert isinstance(result[0], TextInline)

    def test_out_of_y_range_filtered(self) -> None:
        """Matches outside the vertical span region are excluded."""
        spans = [_span("s1", "Text", 100, 100, 150, 112)]
        inlines = [TextInline(text="Text", lang=LanguageCode.EN)]
        symbols = _symbols(
            "p0001",
            [_match("sym.far", 120, 300, 132, 312)],
        )

        result = _insert_icons(inlines, spans, symbols, "p0001")

        assert len(result) == 1
        assert isinstance(result[0], TextInline)

    def test_icon_carries_source_asset_id(self) -> None:
        """IconInline preserves source_asset_id from the SymbolMatch."""
        m = _match("sym.icon", 80, 100, 92, 112)
        m.source_asset_id = "asset_123"
        spans = [_span("s1", "Text", 100, 100, 150, 112)]
        inlines = [TextInline(text="Text", lang=LanguageCode.EN)]
        symbols = _symbols("p0001", [m])

        result = _insert_icons(inlines, spans, symbols, "p0001")

        icons = [n for n in result if isinstance(n, IconInline)]
        assert len(icons) == 1
        assert icons[0].source_asset_id == "asset_123"
