"""PageIRV1 — canonical page content IR with typed blocks and inline nodes."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

from atr_schemas.common import ConfidenceMetrics, PageDimensions, ProvenanceRef, QAState, Rect
from atr_schemas.enums import LanguageCode

# --- Inline nodes (discriminated union on "type") ---


class TextInline(BaseModel):
    """Plain text inline node."""

    type: Literal["text"] = "text"
    text: str
    marks: list[str] = Field(default_factory=list)
    lang: LanguageCode | None = None
    source_word_ids: list[str] = Field(default_factory=list)


class IconInline(BaseModel):
    """Inline icon node, recovered from symbol catalog matching."""

    type: Literal["icon"] = "icon"
    symbol_id: str
    instance_id: str = ""
    bbox: Rect | None = None
    display_hint: dict[str, float | bool] = Field(default_factory=dict)
    source_asset_id: str = ""


class FigureRefInline(BaseModel):
    """Inline reference to a figure asset."""

    type: Literal["figure_ref"] = "figure_ref"
    asset_id: str
    label: str = ""


class XrefInline(BaseModel):
    """Cross-reference to another page or section."""

    type: Literal["xref"] = "xref"
    target_page_id: str = ""
    target_section_id: str = ""
    label: str = ""


class LineBreakInline(BaseModel):
    """Explicit line break."""

    type: Literal["line_break"] = "line_break"


class TermMarkInline(BaseModel):
    """Glossary term marker."""

    type: Literal["term_mark"] = "term_mark"
    concept_id: str
    surface_form: str = ""


def _get_inline_discriminator(v: dict[str, object] | BaseModel) -> str:
    if isinstance(v, dict):
        return str(v.get("type", ""))
    return str(getattr(v, "type", ""))


InlineNode = Annotated[
    Annotated[TextInline, Tag("text")]
    | Annotated[IconInline, Tag("icon")]
    | Annotated[FigureRefInline, Tag("figure_ref")]
    | Annotated[XrefInline, Tag("xref")]
    | Annotated[LineBreakInline, Tag("line_break")]
    | Annotated[TermMarkInline, Tag("term_mark")],
    Discriminator(_get_inline_discriminator),
]


# --- Block nodes (discriminated union on "type") ---


class SectionHint(BaseModel):
    """Section context for a page."""

    section_id: str = ""
    path: list[str] = Field(default_factory=list)


class StyleHint(BaseModel):
    """Font/spacing/classification hints for a block."""

    font_name: str = ""
    font_size: float = 0.0
    is_bold: bool = False
    is_italic: bool = False


class BlockAnnotations(BaseModel):
    """Annotations attached to a block."""

    concept_hits: list[str] = Field(default_factory=list)
    source_confidence: float = 1.0


class SourceRef(BaseModel):
    """Source evidence references for a block."""

    page_id: str = ""
    word_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class HeadingBlock(BaseModel):
    """Heading block."""

    type: Literal["heading"] = "heading"
    block_id: str
    bbox: Rect | None = None
    level: int = Field(ge=1, le=6, default=1)
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    style_hint: StyleHint | None = None
    source_ref: SourceRef | None = None
    annotations: BlockAnnotations | None = None


class ParagraphBlock(BaseModel):
    """Paragraph block."""

    type: Literal["paragraph"] = "paragraph"
    block_id: str
    bbox: Rect | None = None
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    style_hint: StyleHint | None = None
    source_ref: SourceRef | None = None
    annotations: BlockAnnotations | None = None


class ListBlock(BaseModel):
    """List container block."""

    type: Literal["list"] = "list"
    block_id: str
    bbox: Rect | None = None
    ordered: bool = False
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    source_ref: SourceRef | None = None


class ListItemBlock(BaseModel):
    """List item block."""

    type: Literal["list_item"] = "list_item"
    block_id: str
    bbox: Rect | None = None
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    source_ref: SourceRef | None = None


class TableBlock(BaseModel):
    """Table block."""

    type: Literal["table"] = "table"
    block_id: str
    bbox: Rect | None = None
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    source_ref: SourceRef | None = None


class CalloutBlock(BaseModel):
    """Callout/sidebar block."""

    type: Literal["callout"] = "callout"
    block_id: str
    bbox: Rect | None = None
    variant: str = ""
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    source_ref: SourceRef | None = None


class FigureBlock(BaseModel):
    """Figure block."""

    type: Literal["figure"] = "figure"
    block_id: str
    bbox: Rect | None = None
    asset_id: str = ""
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    source_ref: SourceRef | None = None


class CaptionBlock(BaseModel):
    """Caption block."""

    type: Literal["caption"] = "caption"
    block_id: str
    bbox: Rect | None = None
    children: list[InlineNode] = Field(default_factory=list)
    translatable: bool = True
    source_ref: SourceRef | None = None


class DividerBlock(BaseModel):
    """Divider/rule block."""

    type: Literal["divider"] = "divider"
    block_id: str
    bbox: Rect | None = None
    translatable: bool = False


class UnknownBlock(BaseModel):
    """Unknown block — allowed only pre-publish."""

    type: Literal["unknown"] = "unknown"
    block_id: str
    bbox: Rect | None = None
    raw_text: str = ""
    translatable: bool = False
    source_ref: SourceRef | None = None


def _get_block_discriminator(v: dict[str, object] | BaseModel) -> str:
    if isinstance(v, dict):
        return str(v.get("type", ""))
    return str(getattr(v, "type", ""))


Block = Annotated[
    Annotated[HeadingBlock, Tag("heading")]
    | Annotated[ParagraphBlock, Tag("paragraph")]
    | Annotated[ListBlock, Tag("list")]
    | Annotated[ListItemBlock, Tag("list_item")]
    | Annotated[TableBlock, Tag("table")]
    | Annotated[CalloutBlock, Tag("callout")]
    | Annotated[FigureBlock, Tag("figure")]
    | Annotated[CaptionBlock, Tag("caption")]
    | Annotated[DividerBlock, Tag("divider")]
    | Annotated[UnknownBlock, Tag("unknown")],
    Discriminator(_get_block_discriminator),
]


# --- PageIRV1 ---


class PageIRV1(BaseModel):
    """Canonical page content IR."""

    schema_version: str = Field(default="page_ir.v1", pattern=r"^page_ir\.v\d+$")
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    language: LanguageCode
    dimensions_pt: PageDimensions | None = None
    section_hint: SectionHint | None = None
    blocks: list[Block] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)
    confidence: ConfidenceMetrics | None = None
    qa_state: QAState | None = None
    provenance: ProvenanceRef | None = None
