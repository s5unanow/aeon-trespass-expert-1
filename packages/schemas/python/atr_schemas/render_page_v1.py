"""RenderPageV1 — frontend-ready page payload."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

# --- Render inline nodes ---


class RenderTextInline(BaseModel):
    kind: Literal["text"] = "text"
    text: str
    marks: list[str] = Field(default_factory=list)


class RenderIconInline(BaseModel):
    kind: Literal["icon"] = "icon"
    symbol_id: str
    alt: str = ""


class RenderFigureRefInline(BaseModel):
    kind: Literal["figure_ref"] = "figure_ref"
    asset_id: str
    label: str = ""


def _get_render_inline_discriminator(v: dict[str, object] | BaseModel) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", ""))
    return str(getattr(v, "kind", ""))


RenderInlineNode = Annotated[
    Annotated[RenderTextInline, Tag("text")]
    | Annotated[RenderIconInline, Tag("icon")]
    | Annotated[RenderFigureRefInline, Tag("figure_ref")],
    Discriminator(_get_render_inline_discriminator),
]


# --- Render blocks ---


class RenderHeadingBlock(BaseModel):
    kind: Literal["heading"] = "heading"
    id: str
    level: int = 1
    children: list[RenderInlineNode] = Field(default_factory=list)


class RenderParagraphBlock(BaseModel):
    kind: Literal["paragraph"] = "paragraph"
    id: str
    children: list[RenderInlineNode] = Field(default_factory=list)


class RenderFigureBlock(BaseModel):
    kind: Literal["figure"] = "figure"
    id: str
    asset_id: str = ""
    children: list[RenderInlineNode] = Field(default_factory=list)


class RenderCalloutBlock(BaseModel):
    kind: Literal["callout"] = "callout"
    id: str
    variant: str = ""
    children: list[RenderInlineNode] = Field(default_factory=list)


class RenderTableBlock(BaseModel):
    kind: Literal["table"] = "table"
    id: str
    children: list[RenderInlineNode] = Field(default_factory=list)


class RenderListItemBlock(BaseModel):
    kind: Literal["list_item"] = "list_item"
    id: str
    children: list[RenderInlineNode] = Field(default_factory=list)


class RenderDividerBlock(BaseModel):
    kind: Literal["divider"] = "divider"
    id: str


def _get_render_block_discriminator(v: dict[str, object] | BaseModel) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", ""))
    return str(getattr(v, "kind", ""))


RenderBlock = Annotated[
    Annotated[RenderHeadingBlock, Tag("heading")]
    | Annotated[RenderParagraphBlock, Tag("paragraph")]
    | Annotated[RenderFigureBlock, Tag("figure")]
    | Annotated[RenderCalloutBlock, Tag("callout")]
    | Annotated[RenderTableBlock, Tag("table")]
    | Annotated[RenderListItemBlock, Tag("list_item")]
    | Annotated[RenderDividerBlock, Tag("divider")],
    Discriminator(_get_render_block_discriminator),
]


# --- Supporting models ---


class RenderPageMeta(BaseModel):
    id: str
    title: str = ""
    section_path: list[str] = Field(default_factory=list)
    source_page_number: int = 0


class RenderNav(BaseModel):
    prev: str | None = None
    next: str | None = None
    parent_section: str = ""


class RenderFigure(BaseModel):
    src: str
    alt: str = ""
    caption: str = ""


class RenderSourceMap(BaseModel):
    page_id: str
    block_refs: list[str] = Field(default_factory=list)


class RenderBuildMeta(BaseModel):
    build_id: str = ""
    generated_at: str = ""


# --- RenderPageV1 ---


class RenderPageV1(BaseModel):
    """Frontend-ready page payload."""

    schema_version: str = Field(default="render_page.v1", pattern=r"^render_page\.v\d+$")
    document_version: str = ""
    page: RenderPageMeta
    nav: RenderNav = Field(default_factory=RenderNav)
    blocks: list[RenderBlock] = Field(default_factory=list)
    figures: dict[str, RenderFigure] = Field(default_factory=dict)
    glossary_mentions: list[str] = Field(default_factory=list)
    search: dict[str, str | list[str]] = Field(default_factory=dict)
    source_map: RenderSourceMap | None = None
    build_meta: RenderBuildMeta | None = None
