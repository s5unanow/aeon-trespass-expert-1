"""QA rule registry — protocol, page context, and rule discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from atr_pipeline.stages.qa.rules.decorative_icon_rule import evaluate_decorative_icons
from atr_pipeline.stages.qa.rules.glued_text_rule import evaluate_glued_text
from atr_pipeline.stages.qa.rules.icon_count_rule import evaluate_icon_count
from atr_pipeline.stages.qa.rules.leaked_identifier_rule import evaluate_leaked_identifiers
from atr_schemas.enums import QALayer
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderPageV1


@dataclass(frozen=True)
class QAPageContext:
    """All artifacts available for QA evaluation on a single page."""

    source_ir: PageIRV1
    target_ir: PageIRV1
    render_page: RenderPageV1


class QARule(Protocol):
    """Protocol that every QA rule must satisfy."""

    @property
    def name(self) -> str: ...

    @property
    def layer(self) -> QALayer: ...

    def evaluate(self, ctx: QAPageContext) -> list[QARecordV1]: ...


class IconCountRule:
    """Icon count parity between source IR, target IR, and render."""

    @property
    def name(self) -> str:
        return "icon_count"

    @property
    def layer(self) -> QALayer:
        return QALayer.ICON_SYMBOL

    def evaluate(self, ctx: QAPageContext) -> list[QARecordV1]:
        return evaluate_icon_count(ctx.source_ir, ctx.target_ir, ctx.render_page)


class DecorativeIconRule:
    """Detect decorative icon leakage in rendered text."""

    @property
    def name(self) -> str:
        return "decorative_icon"

    @property
    def layer(self) -> QALayer:
        return QALayer.RENDER

    def evaluate(self, ctx: QAPageContext) -> list[QARecordV1]:
        return evaluate_decorative_icons(ctx.render_page)


class GluedTextRule:
    """Detect glued (unseparated) text in rendered output."""

    @property
    def name(self) -> str:
        return "glued_text"

    @property
    def layer(self) -> QALayer:
        return QALayer.EXTRACTION

    def evaluate(self, ctx: QAPageContext) -> list[QARecordV1]:
        return evaluate_glued_text(ctx.render_page)


class LeakedIdentifierRule:
    """Detect technical identifiers leaking into rendered text."""

    @property
    def name(self) -> str:
        return "leaked_identifier"

    @property
    def layer(self) -> QALayer:
        return QALayer.RENDER

    def evaluate(self, ctx: QAPageContext) -> list[QARecordV1]:
        return evaluate_leaked_identifiers(ctx.render_page)


def get_all_rules() -> list[QARule]:
    """Return all registered QA rules."""
    return [
        IconCountRule(),
        DecorativeIconRule(),
        GluedTextRule(),
        LeakedIdentifierRule(),
    ]
