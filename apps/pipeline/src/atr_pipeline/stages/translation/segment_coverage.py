"""S5U-871 — missing / duplicate translation-segment coverage check.

The translation response contract validates the *shape* of what comes back and
rejects unknown segments (``CODE_UNKNOWN_SEGMENT``), but it does not verify the
response covers the *exact requested set*. This module computes the symmetric
difference between requested and returned (block-addressable) segment ids and
emits blocking ``Severity.ERROR`` findings for segments the response dropped or
duplicated, so a silently-skipped block in the re-materializer blocks publish.
"""

from __future__ import annotations

from collections import Counter

from atr_pipeline.stages.translation.grouping import split_group_source_segments
from atr_pipeline.stages.translation.record_builder import (
    RecordContext,
    make_record,
    normalize_segment_id,
    qa_id,
)
from atr_schemas.enums import Severity
from atr_schemas.page_ir_v1 import TextInline
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1

CODE_MISSING_SEGMENT = "TRANSLATION_MISSING_SEGMENT"
CODE_DUPLICATE_SEGMENT = "TRANSLATION_DUPLICATE_SEGMENT"
# Re-declared here (also defined in ``validator``) to avoid an import cycle;
# kept in sync via ``test_segment_coverage_s5u871`` and the validator's own
# group-boundary tests.
CODE_GROUP_BOUNDARY_MISMATCH = "TRANSLATION_GROUP_BOUNDARY_MISMATCH"


def segment_has_content(translated: TranslatedSegment) -> bool:
    """True when a returned segment carries renderable target content.

    S5U-871 decision: a segment that is *present* in the response but whose
    ``target_inline`` is empty (or contains only whitespace-only text nodes)
    counts as **missing** — the translation was effectively dropped, which is
    the exact silent-skip the ``stage.py`` re-materializer would otherwise let
    through. Any non-text inline (icon, xref, figure ref, line break, …) is
    treated as content: an icon-only RU block is a legitimate translation.
    """
    for node in translated.target_inline:
        if isinstance(node, TextInline):
            if node.text.strip():
                return True
            continue
        return True
    return False


def groups_with_boundary_findings(
    batch: TranslationBatchV1,
    records: list[QARecordV1],
) -> set[str]:
    """Block ids belonging to narrative groups already flagged for boundary drift.

    The group-boundary check (``CODE_GROUP_BOUNDARY_MISMATCH``) is the
    authoritative signal for missing/extra/duplicate block *markers* inside a
    narrative group. Excluding those block ids from the coverage check keeps a
    single dropped marker from being reported twice (once as boundary drift,
    once as a missing segment).
    """
    flagged_group_ids = {
        r.entity_ref for r in records if r.code == CODE_GROUP_BOUNDARY_MISMATCH and r.entity_ref
    }
    if not flagged_group_ids:
        return set()
    covered: set[str] = set()
    for segment in batch.segments:
        if segment.block_type != "narrative_group" or segment.segment_id not in flagged_group_ids:
            continue
        for block in split_group_source_segments(segment):
            covered.add(normalize_segment_id(block.segment_id))
    return covered


def _emit_missing(
    expanded_batch: TranslationBatchV1,
    *,
    returned_counts: Counter[str],
    returned_with_content: set[str],
    excluded_ids: set[str],
    rec_ctx: RecordContext,
    records: list[QARecordV1],
) -> None:
    """Append a MISSING record for each requested segment with no content."""
    for source in expanded_batch.segments:
        norm = normalize_segment_id(source.segment_id)
        if norm in excluded_ids or norm in returned_with_content:
            continue
        absent = returned_counts[norm] == 0
        message = (
            f"Missing segment: {norm} (requested but absent from response)"
            if absent
            else f"Missing segment: {norm} (present but blank target_inline)"
        )
        records.append(
            make_record(
                rec_ctx,
                qa_id=qa_id(rec_ctx.page_id, norm, "missing_segment"),
                code=CODE_MISSING_SEGMENT,
                severity=Severity.ERROR,
                entity_ref=norm,
                message=message,
                values=(
                    {"segment_id": norm, "present": not absent},
                    {"segment_id": norm, "has_content": False},
                ),
            )
        )


def _emit_duplicates(
    *,
    returned_counts: Counter[str],
    requested_ids: set[str],
    excluded_ids: set[str],
    rec_ctx: RecordContext,
    records: list[QARecordV1],
) -> None:
    """Append a DUPLICATE record for each requested segment returned >1 time."""
    for norm, count in returned_counts.items():
        if count <= 1 or norm in excluded_ids or norm not in requested_ids:
            continue
        records.append(
            make_record(
                rec_ctx,
                qa_id=qa_id(rec_ctx.page_id, norm, "duplicate_segment"),
                code=CODE_DUPLICATE_SEGMENT,
                severity=Severity.ERROR,
                entity_ref=norm,
                message=f"Duplicate segment: {norm} returned {count} times",
                values=(
                    {"segment_id": norm, "count": 1},
                    {"segment_id": norm, "count": count},
                ),
            )
        )


def check_segment_coverage(
    expanded_batch: TranslationBatchV1,
    expanded_result: TranslationResultV1,
    *,
    excluded_ids: set[str],
    rec_ctx: RecordContext,
    records: list[QARecordV1],
) -> None:
    """Emit blocking records for segments the response failed to cover exactly.

    Computes the symmetric difference between the requested (block-addressable)
    segment ids and the returned ids:

    * **Missing** — requested but absent, or present-but-blank
      (``segment_has_content`` is false). Blocks publish.
    * **Duplicate** — a returned ``segment_id`` appears more than once.

    Extra returned ids (returned but never requested) are already handled by
    ``CODE_UNKNOWN_SEGMENT`` in the validator's main loop.
    """
    returned_counts: Counter[str] = Counter()
    returned_with_content: set[str] = set()
    for translated in expanded_result.segments:
        norm = normalize_segment_id(translated.segment_id)
        returned_counts[norm] += 1
        if segment_has_content(translated):
            returned_with_content.add(norm)

    _emit_missing(
        expanded_batch,
        returned_counts=returned_counts,
        returned_with_content=returned_with_content,
        excluded_ids=excluded_ids,
        rec_ctx=rec_ctx,
        records=records,
    )
    requested_ids = {normalize_segment_id(s.segment_id) for s in expanded_batch.segments}
    _emit_duplicates(
        returned_counts=returned_counts,
        requested_ids=requested_ids,
        excluded_ids=excluded_ids,
        rec_ctx=rec_ctx,
        records=records,
    )
