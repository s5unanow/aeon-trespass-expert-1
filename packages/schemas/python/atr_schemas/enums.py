"""Shared enums used across ATR schemas."""

from enum import StrEnum


class LanguageCode(StrEnum):
    EN = "en"
    RU = "ru"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_ROW = "table_row"
    CALLOUT = "callout"
    FIGURE = "figure"
    CAPTION = "caption"
    RULE_QUOTE = "rule_quote"
    DIVIDER = "divider"
    UNKNOWN = "unknown"


class InlineType(StrEnum):
    TEXT = "text"
    ICON = "icon"
    FIGURE_REF = "figure_ref"
    XREF = "xref"
    LINE_BREAK = "line_break"
    TERM_MARK = "term_mark"


class AssetKind(StrEnum):
    FIGURE_IMAGE = "figure_image"
    INLINE_SYMBOL = "inline_symbol"
    DECORATIVE = "decorative"
    PAGE_CROP = "page_crop"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class QALayer(StrEnum):
    EXTRACTION = "extraction"
    STRUCTURE = "structure"
    TERMINOLOGY = "terminology"
    ICON_SYMBOL = "icon_symbol"
    ASSET_LINK = "asset_link"
    RENDER = "render"
    VISUAL = "visual"
    ACCESSIBILITY = "accessibility"


class StageScope(StrEnum):
    DOCUMENT = "document"
    PAGE = "page"
    ASSET = "asset"
    BATCH = "batch"


class RegionKind(StrEnum):
    """Semantic region classification."""

    BODY = "body"
    SIDEBAR = "sidebar"
    HEADER = "header"
    FOOTER = "footer"
    FIGURE_AREA = "figure_area"
    TABLE_AREA = "table_area"
    CALLOUT_AREA = "callout_area"
    MARGIN_NOTE = "margin_note"
    FULL_WIDTH = "full_width"
    UNKNOWN = "unknown"


class SymbolAnchorKind(StrEnum):
    """How a symbol attaches to its context."""

    INLINE = "inline"
    PREFIX = "prefix"
    CELL_LOCAL = "cell_local"
    BLOCK_ATTACHED = "block_attached"
    REGION_ANNOTATION = "region_annotation"


class AnchorEdgeKind(StrEnum):
    """Type of anchor/parent relationship between resolved entities."""

    CAPTION_TO_FIGURE = "caption_to_figure"
    BLOCK_TO_CALLOUT = "block_to_callout"
    SYMBOL_TO_BLOCK = "symbol_to_block"
    BLOCK_TO_REGION = "block_to_region"
    ASIDE_TO_MAIN = "aside_to_main"


class PatchTargetKind(StrEnum):
    """Which artifact schema a patch set targets."""

    PAGE_IR = "page_ir"
    RESOLVED_PAGE = "resolved_page"
    LAYOUT_PAGE = "layout_page"
    PAGE_EVIDENCE = "page_evidence"


class PatchScope(StrEnum):
    """Classification of what a patch operation corrects."""

    TEXT = "text"
    BLOCK_STRUCTURE = "block_structure"
    READING_ORDER = "reading_order"
    REGION_ASSIGNMENT = "region_assignment"
    ASSET_LINK = "asset_link"
    SYMBOL_RESOLUTION = "symbol_resolution"
    CONFIDENCE_OVERRIDE = "confidence_override"
    FALLBACK_RESOLUTION = "fallback_resolution"


class AssetSourceKind(StrEnum):
    """How the asset was originally captured."""

    EMBEDDED_RASTER = "embedded_raster"
    VECTOR_CLUSTER = "vector_cluster"
    RENDERED_CROP = "rendered_crop"


class OccurrenceContext(StrEnum):
    """Where an asset occurrence sits relative to its surrounding content."""

    INLINE = "inline"
    LINE_PREFIX = "line_prefix"
    CELL_LOCAL = "cell_local"
    BLOCK_ATTACHED = "block_attached"
    DECORATION = "decoration"
    REGION_FLOAT = "region_float"
