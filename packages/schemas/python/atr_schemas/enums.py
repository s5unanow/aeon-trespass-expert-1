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
