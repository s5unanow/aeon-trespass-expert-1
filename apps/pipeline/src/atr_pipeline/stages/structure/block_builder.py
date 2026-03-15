"""Build PageIRV1 from native evidence and symbol matches for simple pages."""

from __future__ import annotations

from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1


def build_page_ir_simple(
    native: NativePageV1,
    symbols: SymbolMatchSetV1,
) -> PageIRV1:
    """Build a simple-page PageIRV1 from native evidence and symbol matches.

    Strategy for the walking skeleton:
    - Words with large font size become heading blocks.
    - Remaining words become paragraph blocks.
    - Symbol matches are inserted as inline icon nodes at their bbox position.
    """
    # Separate heading words from body words by font size
    # In the walking skeleton, the heading uses fontsize=18 and body uses 11
    heading_words: list[str] = []
    body_words_before_icon: list[str] = []
    body_words_after_icon: list[str] = []

    # Find the icon position to split text around it
    icon_match = None
    if symbols.matches:
        icon_match = symbols.matches[0]

    for w in native.words:
        # Heuristic: heading words have larger y position < 100 (near top)
        # and body words have y > 100
        if w.bbox.y0 < 100:
            heading_words.append(w.text)
        elif icon_match and w.bbox.x0 < icon_match.bbox.x0:
            body_words_before_icon.append(w.text)
        else:
            body_words_after_icon.append(w.text)

    blocks = []
    block_ids = []

    # Heading block
    if heading_words:
        block_id = f"{native.page_id}.b001"
        blocks.append(
            HeadingBlock(
                block_id=block_id,
                level=2,
                children=[
                    TextInline(text=" ".join(heading_words), lang=LanguageCode.EN),
                ],
            )
        )
        block_ids.append(block_id)

    # Paragraph block with inline icon
    if body_words_before_icon or body_words_after_icon or icon_match:
        block_id = f"{native.page_id}.b002"
        children: list[TextInline | IconInline] = []

        if body_words_before_icon:
            children.append(
                TextInline(text=" ".join(body_words_before_icon) + " ", lang=LanguageCode.EN)
            )

        if icon_match:
            children.append(
                IconInline(
                    symbol_id=icon_match.symbol_id,
                    instance_id=icon_match.instance_id,
                )
            )

        if body_words_after_icon:
            text = " ".join(body_words_after_icon)
            # Ensure space before if icon exists
            if icon_match:
                text = " " + text
            children.append(TextInline(text=text, lang=LanguageCode.EN))

        blocks.append(
            ParagraphBlock(
                block_id=block_id,
                children=children,  # type: ignore[arg-type]
            )
        )
        block_ids.append(block_id)

    return PageIRV1(
        document_id=native.document_id,
        page_id=native.page_id,
        page_number=native.page_number,
        language=LanguageCode.EN,
        dimensions_pt=native.dimensions_pt,
        blocks=blocks,  # type: ignore[arg-type]
        reading_order=block_ids,
    )
