# ruff: noqa: RUF001  — Cyrillic expected strings are intentional.
"""S5U-776 — narrative prose translates as full grouped sections."""

from __future__ import annotations

from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.rematerialize import rematerialize_ru_blocks
from atr_pipeline.stages.translation.stage import (
    _expand_grouped_translation_batch,
    _expand_grouped_translation_result,
)
from atr_pipeline.stages.translation.validator import (
    CODE_GLOSSARY_SURFACE_FORM_DRIFT,
    CODE_GROUP_BOUNDARY_MISMATCH,
    validate_translation,
)
from atr_schemas.concept_registry_v1 import (
    ConceptRegistryV1,
    ConceptSource,
    ConceptTarget,
    ConceptV1,
)
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    LineBreakInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
    XrefInline,
)
from atr_schemas.translation_result_v1 import (
    ConceptRealization,
    TranslatedSegment,
    TranslationResultV1,
)


def _story_ir() -> PageIRV1:
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(block_id="h1", children=[TextInline(text="So it begins")]),
            ParagraphBlock(
                block_id="p1",
                children=[TextInline(text="The Argo cuts through the evening waves.")],
            ),
            ParagraphBlock(block_id="p2", children=[TextInline(text="But only a few.")]),
        ],
        reading_order=["h1", "p1", "p2"],
    )


def test_planner_groups_contiguous_narrative_blocks() -> None:
    batch = build_translation_batch(_story_ir())

    assert len(batch.segments) == 1
    group = batch.segments[0]
    assert group.block_type == "narrative_group"
    assert group.context.section_path == ["h1", "p1", "p2"]

    markers = [n for n in group.source_inline if isinstance(n, XrefInline)]
    assert [m.target_section_id for m in markers] == [
        "translation-block:h1",
        "translation-block:p1",
        "translation-block:p2",
    ]


def test_grouped_translation_splits_back_to_original_blocks() -> None:
    en_ir = _story_ir()
    batch = build_translation_batch(en_ir)
    group_id = batch.segments[0].segment_id
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=group_id,
                target_inline=[
                    XrefInline(target_section_id="translation-block:h1", label="heading"),
                    TextInline(text="Так берет свое начало это сказание.", lang=LanguageCode.RU),
                    XrefInline(target_section_id="translation-block:p1", label="paragraph"),
                    TextInline(text="«Арго» рассекает вечерние волны.", lang=LanguageCode.RU),
                    XrefInline(target_section_id="translation-block:p2", label="paragraph"),
                    TextInline(text="Но зажглись лишь немногие из них.", lang=LanguageCode.RU),
                ],
            )
        ],
    )

    expanded_batch = _expand_grouped_translation_batch(batch)
    expanded_result = _expand_grouped_translation_result(batch, result)
    ru_blocks = rematerialize_ru_blocks(en_ir, expanded_batch, expanded_result)

    by_id = {block.block_id: block for block in ru_blocks}
    assert [n.text for n in by_id["h1"].children if hasattr(n, "text")] == [
        "Так берет свое начало это сказание."
    ]
    assert [n.text for n in by_id["p1"].children if hasattr(n, "text")] == [
        "«Арго» рассекает вечерние волны."
    ]
    assert [n.text for n in by_id["p2"].children if hasattr(n, "text")] == [
        "Но зажглись лишь немногие из них."
    ]
    assert all(not isinstance(n, XrefInline) for block in ru_blocks for n in block.children)


def test_grouped_translation_strips_boundary_line_breaks() -> None:
    en_ir = _story_ir()
    batch = build_translation_batch(en_ir)
    group_id = batch.segments[0].segment_id
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=group_id,
                target_inline=[
                    XrefInline(target_section_id="translation-block:h1", label="heading"),
                    TextInline(text="Так берет свое начало это сказание.", lang=LanguageCode.RU),
                    LineBreakInline(),
                    LineBreakInline(),
                    XrefInline(target_section_id="translation-block:p1", label="paragraph"),
                    LineBreakInline(),
                    TextInline(text="«Арго» рассекает вечерние волны.", lang=LanguageCode.RU),
                    LineBreakInline(),
                ],
            )
        ],
    )

    expanded = _expand_grouped_translation_result(batch, result)
    by_id = {segment.segment_id: segment for segment in expanded.segments}

    assert all(not isinstance(n, LineBreakInline) for n in by_id["h1"].target_inline)
    assert all(not isinstance(n, LineBreakInline) for n in by_id["p1"].target_inline)


def test_validator_flags_missing_group_marker() -> None:
    batch = build_translation_batch(_story_ir())
    group_id = batch.segments[0].segment_id
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=group_id,
                target_inline=[
                    XrefInline(target_section_id="translation-block:h1", label="heading"),
                    TextInline(text="Так берет свое начало это сказание.", lang=LanguageCode.RU),
                    XrefInline(target_section_id="translation-block:p2", label="paragraph"),
                    TextInline(text="Но зажглись лишь немногие из них.", lang=LanguageCode.RU),
                ],
            )
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")

    assert any(r.code == CODE_GROUP_BOUNDARY_MISMATCH and "missing" in r.message for r in records)


def test_validator_flags_reordered_group_markers_and_prefix_text() -> None:
    batch = build_translation_batch(_story_ir())
    group_id = batch.segments[0].segment_id
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=group_id,
                target_inline=[
                    TextInline(text="Лишний текст.", lang=LanguageCode.RU),
                    XrefInline(target_section_id="translation-block:p1", label="paragraph"),
                    XrefInline(target_section_id="translation-block:h1", label="heading"),
                    XrefInline(target_section_id="translation-block:p2", label="paragraph"),
                ],
            )
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")

    boundary = [r for r in records if r.code == CODE_GROUP_BOUNDARY_MISMATCH]
    assert len(boundary) == 1
    assert "order" in boundary[0].message
    assert "text_before_first_marker" in boundary[0].message


def test_grouped_concept_realizations_are_still_validated() -> None:
    registry = ConceptRegistryV1(
        concepts=[
            ConceptV1(
                concept_id="concept.truth",
                kind="term",
                source=ConceptSource(lemma="Truth"),
                target=ConceptTarget(
                    lemma="Истина",
                    allowed_surface_forms=["Истина", "Истины"],
                ),
            )
        ]
    )
    en_ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(block_id="h1", children=[TextInline(text="Truth")]),
            ParagraphBlock(block_id="p1", children=[TextInline(text="Only the Truth matters.")]),
        ],
        reading_order=["h1", "p1"],
    )
    batch = build_translation_batch(en_ir, concept_registry=registry)
    group_id = batch.segments[0].segment_id
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=group_id,
                target_inline=[
                    XrefInline(target_section_id="translation-block:h1", label="heading"),
                    TextInline(text="Правда", lang=LanguageCode.RU),
                    XrefInline(target_section_id="translation-block:p1", label="paragraph"),
                    TextInline(text="Важна лишь Правда.", lang=LanguageCode.RU),
                ],
                concept_realizations=[
                    ConceptRealization(concept_id="concept.truth", surface_form="Правда")
                ],
            )
        ],
    )

    records = validate_translation(
        batch,
        result,
        concept_registry=registry,
        document_id="test",
        page_id="p0001",
    )

    assert any(r.code == CODE_GLOSSARY_SURFACE_FORM_DRIFT for r in records)
