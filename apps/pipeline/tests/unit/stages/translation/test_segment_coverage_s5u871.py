"""S5U-871 — missing / duplicate translation-segment coverage detection.

The translation response contract validates the *shape* of what comes back and
rejects unknown segments, but pre-S5U-871 it did not verify the response
covered the *exact requested set*. A batch sending N segments whose response
returned M < N silently dropped the untranslated blocks with no QA signal.

These tests pin the symmetric-difference check: missing (requested but absent),
present-but-blank (counts as missing — see ``validator._segment_has_content``),
and duplicate (returned more than once) segments each produce a blocking
``Severity.ERROR`` finding naming the segment_id; a complete response produces
no new findings.
"""

from __future__ import annotations

from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.validator import (
    CODE_DUPLICATE_SEGMENT,
    CODE_MISSING_SEGMENT,
    CODE_UNKNOWN_SEGMENT,
    validate_translation,
)
from atr_schemas.enums import LanguageCode, QALayer, Severity
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1


def _page_ir() -> PageIRV1:
    """Two independent translatable blocks (no narrative grouping)."""
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id="blk_001",
                children=[TextInline(text="Stamina Test")],
            ),
            ParagraphBlock(
                block_id="blk_002",
                children=[
                    TextInline(text="Gain 1 "),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Progress."),
                ],
            ),
        ],
        reading_order=["blk_001", "blk_002"],
    )


def _complete_result(batch_id: str) -> TranslationResultV1:
    return TranslationResultV1(
        batch_id=batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[
                    TextInline(text="Получите 1 ", lang="ru"),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Прогресс.", lang="ru"),
                ],
            ),
        ],
    )


def test_missing_segment_produces_blocking_finding() -> None:
    """A response omitting a requested segment yields a blocking MISSING record."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            # blk_002 dropped entirely.
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    missing = [r for r in records if r.code == CODE_MISSING_SEGMENT]
    assert len(missing) == 1
    rec = missing[0]
    assert rec.entity_ref == "blk_002"
    assert "blk_002" in rec.message
    assert rec.severity == Severity.ERROR  # in block_publish_on default set
    assert rec.layer == QALayer.TERMINOLOGY
    assert rec.page_id == "p0001"
    assert rec.document_id == "test"


def test_blank_target_inline_counts_as_missing() -> None:
    """A present-but-blank segment counts as missing (documented decision)."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[TextInline(text="   ", lang="ru")],  # whitespace-only
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    missing = [r for r in records if r.code == CODE_MISSING_SEGMENT]
    assert len(missing) == 1
    assert missing[0].entity_ref == "blk_002"
    assert "blank" in missing[0].message.lower()


def test_empty_target_inline_list_counts_as_missing() -> None:
    """An empty target_inline list also counts as missing."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            TranslatedSegment(segment_id="blk_002", target_inline=[]),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    missing = [r for r in records if r.code == CODE_MISSING_SEGMENT]
    assert len(missing) == 1
    assert missing[0].entity_ref == "blk_002"


def test_blank_target_with_icon_is_not_missing() -> None:
    """A segment whose only content is an icon is NOT blank — icons are content."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[IconInline(symbol_id="sym.progress")],
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    assert [r for r in records if r.code == CODE_MISSING_SEGMENT] == []


def test_duplicate_segment_produces_finding() -> None:
    """A response repeating a segment_id yields a blocking DUPLICATE record."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[TextInline(text="Первый перевод", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",  # duplicate
                target_inline=[TextInline(text="Второй перевод", lang="ru")],
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    dupes = [r for r in records if r.code == CODE_DUPLICATE_SEGMENT]
    assert len(dupes) == 1
    rec = dupes[0]
    assert rec.entity_ref == "blk_002"
    assert "blk_002" in rec.message
    assert rec.severity == Severity.ERROR
    assert rec.actual == {"segment_id": "blk_002", "count": 2}


def test_complete_response_has_no_coverage_findings() -> None:
    """A complete response produces no MISSING / DUPLICATE findings (no FPs)."""
    batch = build_translation_batch(_page_ir())
    result = _complete_result(batch.batch_id)

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    assert [r for r in records if r.code == CODE_MISSING_SEGMENT] == []
    assert [r for r in records if r.code == CODE_DUPLICATE_SEGMENT] == []


def test_segment_id_matching_tolerates_surrounding_whitespace() -> None:
    """Returned segment_id with surrounding whitespace still matches (normalized)."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="  blk_001  ",  # whitespace variance
                target_inline=[TextInline(text="Тест выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[
                    TextInline(text="Получите 1 ", lang="ru"),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Прогресс.", lang="ru"),
                ],
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    assert [r for r in records if r.code == CODE_MISSING_SEGMENT] == []
    # The whitespace-padded id must not be misread as an unknown segment.
    assert [r for r in records if r.code == CODE_UNKNOWN_SEGMENT] == []


def test_missing_runs_at_top_level_not_within_narrative_group() -> None:
    """Narrative-group block-marker drift stays under group-boundary handling.

    A complete narrative-group response (all blocks present via markers) must
    not trip the top-level missing/duplicate coverage check, which operates on
    the response's top-level segment IDs.
    """
    page_ir = PageIRV1(
        document_id="test",
        page_id="p0002",
        page_number=2,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(block_id="blk_001", children=[TextInline(text="First.")]),
            ParagraphBlock(block_id="blk_002", children=[TextInline(text="Second.")]),
        ],
        reading_order=["blk_001", "blk_002"],
    )
    batch = build_translation_batch(page_ir)
    # The planner groups two contiguous paragraphs into one narrative-group
    # segment whose id is "group.p0002.001".
    group_id = batch.segments[0].segment_id
    assert group_id.startswith("group.")
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=group_id,
                target_inline=[
                    # Block markers preserved so split-back stays intact.
                    *_group_markers_for(batch),
                ],
            ),
        ],
    )
    records = validate_translation(batch, result, document_id="test", page_id="p0002")
    # The group segment was returned, so no top-level missing/duplicate.
    assert [r for r in records if r.code == CODE_MISSING_SEGMENT] == []
    assert [r for r in records if r.code == CODE_DUPLICATE_SEGMENT] == []


def _group_markers_for(batch: object) -> list[object]:
    """Reconstruct the source narrative-group inline (markers + text) verbatim.

    Echoing the source inline back is the canonical 'model copied the markers'
    happy path; it keeps the group-boundary check satisfied.
    """
    segments = batch.segments  # type: ignore[attr-defined]
    return list(segments[0].source_inline)
