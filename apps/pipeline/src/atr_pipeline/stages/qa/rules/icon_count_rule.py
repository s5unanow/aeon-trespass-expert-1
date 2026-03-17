"""QA rule: icon count parity between source IR, target IR, and render page."""

from __future__ import annotations

from atr_schemas.enums import QALayer, Severity
from atr_schemas.page_ir_v1 import DividerBlock, PageIRV1, UnknownBlock
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1


def _count_icons_ir(page_ir: PageIRV1) -> int:
    """Count inline icon nodes in a PageIRV1."""
    count = 0
    for block in page_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        for child in block.children:
            if child.type == "icon":
                count += 1
    return count


def _count_icons_render(render: RenderPageV1) -> int:
    """Count inline icon nodes in a RenderPageV1."""
    count = 0
    for block in render.blocks:
        if isinstance(block, RenderDividerBlock):
            continue
        for child in block.children:
            if child.kind == "icon":
                count += 1
    return count


def evaluate_icon_count(
    source_ir: PageIRV1,
    target_ir: PageIRV1,
    render_page: RenderPageV1,
) -> list[QARecordV1]:
    """Check that icon counts match across source, target, and render.

    Returns a list of QA records (empty if passing).
    """
    records: list[QARecordV1] = []

    source_count = _count_icons_ir(source_ir)
    target_count = _count_icons_ir(target_ir)
    render_count = _count_icons_render(render_page)

    if source_count != target_count:
        records.append(
            QARecordV1(
                qa_id=f"qa.{source_ir.page_id}.icon.src_tgt_mismatch",
                layer=QALayer.ICON_SYMBOL,
                severity=Severity.ERROR,
                code="ICON_COUNT_SRC_TGT_MISMATCH",
                document_id=source_ir.document_id,
                page_id=source_ir.page_id,
                message=(
                    f"Source IR has {source_count} icons but "
                    f"target IR has {target_count}."
                ),
                expected={"count": source_count},
                actual={"count": target_count},
            )
        )

    if target_count != render_count:
        records.append(
            QARecordV1(
                qa_id=f"qa.{source_ir.page_id}.icon.tgt_render_mismatch",
                layer=QALayer.ICON_SYMBOL,
                severity=Severity.ERROR,
                code="ICON_COUNT_TGT_RENDER_MISMATCH",
                document_id=source_ir.document_id,
                page_id=source_ir.page_id,
                message=(
                    f"Target IR has {target_count} icons but "
                    f"render page has {render_count}."
                ),
                expected={"count": target_count},
                actual={"count": render_count},
            )
        )

    return records
