"""Cross-stage block-type survival integration test.

Verifies that every block type in the PageIR Block union either:
- Produces a corresponding RenderBlock in build_render_page(), OR
- Is explicitly listed in INTENTIONALLY_DROPPED with a rationale.

This prevents new block types from being silently dropped when added
to the schema without updating the render stage.
"""

from __future__ import annotations

from typing import get_args

import pytest

from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    InlineNode,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TextInline,
    UnknownBlock,
)

# ---------------------------------------------------------------------------
# Block type → minimal constructor
# ---------------------------------------------------------------------------

_DUMMY_TEXT: list[InlineNode] = [TextInline(text="test", lang=LanguageCode.EN)]

_BLOCK_FACTORIES: dict[str, Block] = {
    "heading": HeadingBlock(block_id="p0001.b001", level=1, children=_DUMMY_TEXT),
    "paragraph": ParagraphBlock(block_id="p0001.b001", children=_DUMMY_TEXT),
    "list": ListBlock(block_id="p0001.b001", children=_DUMMY_TEXT),
    "list_item": ListItemBlock(block_id="p0001.b001", children=_DUMMY_TEXT),
    "table": TableBlock(block_id="p0001.b001", children=_DUMMY_TEXT),
    "callout": CalloutBlock(block_id="p0001.b001", children=_DUMMY_TEXT),
    "figure": FigureBlock(block_id="p0001.b001", asset_id="img0000"),
    "caption": CaptionBlock(block_id="p0001.b001", children=_DUMMY_TEXT),
    "divider": DividerBlock(block_id="p0001.b001"),
    "unknown": UnknownBlock(block_id="p0001.b001"),
}

# ---------------------------------------------------------------------------
# Intentionally dropped types (with rationale)
# ---------------------------------------------------------------------------

# Block types that build_render_page() intentionally does NOT convert to a
# RenderBlock.  Adding a type here is a conscious opt-out — each entry MUST
# include a short rationale explaining why it is safe to drop.
INTENTIONALLY_DROPPED: dict[str, str] = {
    "divider": "Decorative rule with no translatable content",
    "unknown": "Pre-publish placeholder that must be resolved before render",
    "list": "Container block — individual ListItemBlocks are rendered instead",
    "callout": "Render mapping not yet implemented (tracked for future work)",
    "caption": "Render mapping not yet implemented (tracked for future work)",
}

# ---------------------------------------------------------------------------
# Extract all block type tags from the Block discriminated union
# ---------------------------------------------------------------------------


def _block_type_tags() -> frozenset[str]:
    """Return the set of type-tag strings from the Block union."""
    outer_args = get_args(Block)
    # Block = Annotated[Union[Annotated[Cls, Tag], ...], Discriminator]
    union_type = outer_args[0]
    tags: set[str] = set()
    for annotated in get_args(union_type):
        cls = get_args(annotated)[0]
        tags.add(cls.model_fields["type"].default)
    return frozenset(tags)


ALL_BLOCK_TYPES: frozenset[str] = _block_type_tags()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBlockTypeSurvival:
    """Parameterized survival check for every PageIR block type."""

    def test_factories_cover_all_union_members(self) -> None:
        """_BLOCK_FACTORIES must have an entry for every Block union type."""
        missing = ALL_BLOCK_TYPES - _BLOCK_FACTORIES.keys()
        assert not missing, (
            f"Block union has types with no test factory: {missing}. "
            f"Add entries to _BLOCK_FACTORIES in this file."
        )

    def test_no_stale_factory_entries(self) -> None:
        """_BLOCK_FACTORIES must not have entries for removed block types."""
        extra = set(_BLOCK_FACTORIES.keys()) - ALL_BLOCK_TYPES
        assert not extra, (
            f"_BLOCK_FACTORIES has entries for types no longer in the Block union: "
            f"{extra}. Remove them."
        )

    def test_no_stale_dropped_entries(self) -> None:
        """INTENTIONALLY_DROPPED must not reference types outside the union."""
        extra = set(INTENTIONALLY_DROPPED.keys()) - ALL_BLOCK_TYPES
        assert not extra, (
            f"INTENTIONALLY_DROPPED references types not in Block union: {extra}. "
            f"Remove stale entries."
        )

    @pytest.mark.parametrize("block_type", sorted(_block_type_tags()))
    def test_block_survives_or_is_explicitly_dropped(self, block_type: str) -> None:
        """Each block type either produces a RenderBlock or is dropped."""
        block = _BLOCK_FACTORIES[block_type]
        ir = PageIRV1(
            document_id="test_survival",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[block],
            reading_order=["p0001.b001"],
        )
        render = build_render_page(ir)

        if block_type in INTENTIONALLY_DROPPED:
            assert len(render.blocks) == 0, (
                f"Block type {block_type!r} is in INTENTIONALLY_DROPPED but "
                f"produced a render block — remove it from INTENTIONALLY_DROPPED"
            )
        else:
            assert len(render.blocks) == 1, (
                f"Block type {block_type!r} produced no render block. Either:\n"
                f"  1. Add render handling in page_builder.py, OR\n"
                f"  2. Add {block_type!r} to INTENTIONALLY_DROPPED with a rationale"
            )
