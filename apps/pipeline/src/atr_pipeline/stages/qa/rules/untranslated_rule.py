"""QA rule: detect untranslated text blocks in the target (RU) IR."""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.page_ir_v1 import DividerBlock, PageIRV1, UnknownBlock
from atr_schemas.qa_record_v1 import QARecordV1

_LATIN_RE = re.compile(r"[A-Za-z]")

DEFAULT_MIN_CHARS = 20
DEFAULT_LATIN_RATIO = 0.5


def evaluate_untranslated(
    target_ir: PageIRV1,
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    latin_ratio: float = DEFAULT_LATIN_RATIO,
) -> list[QARecordV1]:
    """Flag target-IR blocks where Latin characters exceed *latin_ratio*.

    Only blocks with at least *min_chars* of text content are checked.
    Returns one QARecordV1 per offending block.
    """
    records: list[QARecordV1] = []

    for block in target_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        text = "".join(child.text for child in block.children if child.type == "text")
        if len(text) < min_chars:
            continue
        latin_count = len(_LATIN_RE.findall(text))
        ratio = latin_count / len(text)
        if ratio > latin_ratio:
            records.append(
                QARecordV1(
                    qa_id=f"qa.{target_ir.page_id}.untranslated.{block.block_id}",
                    layer=QALayer.TERMINOLOGY,
                    severity=Severity.ERROR,
                    code="UNTRANSLATED_TEXT",
                    document_id=target_ir.document_id,
                    page_id=target_ir.page_id,
                    entity_ref=block.block_id,
                    message=f"Block is {ratio:.0%} Latin ({latin_count}/{len(text)} chars)",
                )
            )

    return records
