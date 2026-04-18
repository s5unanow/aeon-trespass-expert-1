"""Tests for terminology enforcement in translation planner and validator."""

from atr_pipeline.stages.qa.waivers import apply_waivers
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.validator import (
    CODE_GLOSSARY_FORBIDDEN_TARGET,
    CODE_GLOSSARY_SURFACE_FORM_DRIFT,
    CODE_ICON_COUNT_MISMATCH,
    CODE_ICON_ORDER_MISMATCH,
    CODE_UNKNOWN_SEGMENT,
    validate_translation,
)
from atr_schemas.concept_registry_v1 import (
    ConceptRegistryV1,
    ConceptSource,
    ConceptTarget,
    ConceptV1,
)
from atr_schemas.enums import LanguageCode, QALayer, Severity
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.translation_result_v1 import (
    ConceptRealization,
    TranslatedSegment,
    TranslationResultV1,
)
from atr_schemas.waiver_v1 import WaiverV1


def _registry() -> ConceptRegistryV1:
    return ConceptRegistryV1(
        concepts=[
            ConceptV1(
                concept_id="concept.progress",
                kind="icon_term",
                source=ConceptSource(
                    lemma="Progress",
                    patterns=["Progress", "gain Progress"],
                ),
                target=ConceptTarget(
                    lemma="Прогресс",
                    allowed_surface_forms=["Прогресс", "Прогресса"],
                ),
                icon_binding="sym.progress",
                forbidden_targets=["Продвижение", "Развитие"],
            ),
            ConceptV1(
                concept_id="concept.stamina",
                kind="term",
                source=ConceptSource(lemma="Stamina"),
                target=ConceptTarget(
                    lemma="Выносливость",
                    allowed_surface_forms=["Выносливость", "Выносливости"],
                ),
                forbidden_targets=["Стамина"],
            ),
        ],
    )


def _page_ir() -> PageIRV1:
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


# --- Planner tests ---


def test_planner_injects_forbidden_targets() -> None:
    """Planner populates forbidden_targets from concept registry."""
    batch = build_translation_batch(_page_ir(), concept_registry=_registry())

    # blk_002 has icon sym.progress + text "Progress"
    seg2 = next(s for s in batch.segments if s.segment_id == "blk_002")
    assert "Продвижение" in seg2.forbidden_targets
    assert "Развитие" in seg2.forbidden_targets


def test_planner_detects_text_concepts() -> None:
    """Planner finds concept matches in text (not just icons)."""
    batch = build_translation_batch(_page_ir(), concept_registry=_registry())

    # blk_001 heading contains "Stamina" which matches concept.stamina
    seg1 = next(s for s in batch.segments if s.segment_id == "blk_001")
    assert "concept.stamina" in seg1.required_concepts
    assert "Стамина" in seg1.forbidden_targets


def test_planner_without_registry_still_works() -> None:
    """Planner works without a registry (backward compat)."""
    batch = build_translation_batch(_page_ir())

    seg2 = next(s for s in batch.segments if s.segment_id == "blk_002")
    # Icon-based concepts still detected
    assert "concept.progress" in seg2.required_concepts
    # But no forbidden targets from registry
    assert seg2.forbidden_targets == []


# --- Validator tests ---


def test_validator_catches_forbidden_term() -> None:
    """Validator flags forbidden terms in target text as QARecordV1."""
    batch = build_translation_batch(_page_ir(), concept_registry=_registry())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест Стамина", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[
                    TextInline(text="Получите 1 ", lang="ru"),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Продвижение.", lang="ru"),
                ],
                concept_realizations=[
                    ConceptRealization(
                        concept_id="concept.progress",
                        surface_form="Продвижение",
                    ),
                ],
            ),
        ],
    )

    records = validate_translation(
        batch,
        result,
        concept_registry=_registry(),
        document_id="test",
        page_id="p0001",
    )

    forbidden = [r for r in records if r.code == CODE_GLOSSARY_FORBIDDEN_TARGET]
    # "Стамина" in blk_001, "Продвижение" in blk_002
    assert len(forbidden) == 2
    for r in forbidden:
        assert r.layer == QALayer.TERMINOLOGY
        assert r.severity == Severity.ERROR
        assert r.page_id == "p0001"
        assert r.document_id == "test"
        assert r.entity_ref in {"blk_001", "blk_002"}


def test_validator_checks_surface_forms() -> None:
    """Validator flags concept realizations with disallowed surface forms."""
    batch = build_translation_batch(_page_ir(), concept_registry=_registry())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест Выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[
                    TextInline(text="Получите 1 ", lang="ru"),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Прогрессик.", lang="ru"),
                ],
                concept_realizations=[
                    ConceptRealization(
                        concept_id="concept.progress",
                        surface_form="Прогрессик",  # NOT in allowed forms
                    ),
                ],
            ),
        ],
    )

    records = validate_translation(
        batch,
        result,
        concept_registry=_registry(),
        document_id="test",
        page_id="p0001",
    )

    drifts = [r for r in records if r.code == CODE_GLOSSARY_SURFACE_FORM_DRIFT]
    assert len(drifts) == 1
    drift = drifts[0]
    assert drift.severity == Severity.WARNING  # default non_preferred_allowed
    assert drift.entity_ref == "blk_002"
    assert drift.actual == {
        "concept_id": "concept.progress",
        "surface_form": "Прогрессик",
    }
    assert drift.expected is not None
    assert "Прогресс" in drift.expected["allowed_surface_forms"]


def test_validator_passes_clean_translation() -> None:
    """Validator returns no records for a correct translation."""
    batch = build_translation_batch(_page_ir(), concept_registry=_registry())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест Выносливости", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[
                    TextInline(text="Получите 1 ", lang="ru"),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Прогресс.", lang="ru"),
                ],
                concept_realizations=[
                    ConceptRealization(
                        concept_id="concept.progress",
                        surface_form="Прогресс",
                    ),
                ],
            ),
        ],
    )

    records = validate_translation(
        batch,
        result,
        concept_registry=_registry(),
        document_id="test",
        page_id="p0001",
    )
    assert records == []


def test_validator_flags_icon_count_mismatch() -> None:
    """Validator flags translations that drop icons."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                # Missing the icon entirely
                target_inline=[TextInline(text="Получите 1 Прогресс.", lang="ru")],
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    count_mismatch = [r for r in records if r.code == CODE_ICON_COUNT_MISMATCH]
    assert len(count_mismatch) == 1
    r = count_mismatch[0]
    assert r.severity == Severity.ERROR
    assert r.expected == {"count": 1}
    assert r.actual == {"count": 0}


def test_validator_flags_icon_order_mismatch() -> None:
    """Validator flags translations that reorder / swap icons."""
    page_ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="blk_001",
                children=[
                    IconInline(symbol_id="sym.a"),
                    TextInline(text=" then "),
                    IconInline(symbol_id="sym.b"),
                ],
            ),
        ],
        reading_order=["blk_001"],
    )
    batch = build_translation_batch(page_ir)
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[
                    IconInline(symbol_id="sym.b"),
                    TextInline(text=" затем ", lang="ru"),
                    IconInline(symbol_id="sym.a"),
                ],
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    order_mismatch = [r for r in records if r.code == CODE_ICON_ORDER_MISMATCH]
    assert len(order_mismatch) == 1
    r = order_mismatch[0]
    assert r.expected == {"symbol_ids": ["sym.a", "sym.b"]}
    assert r.actual == {"symbol_ids": ["sym.b", "sym.a"]}


def test_validator_flags_unknown_segment() -> None:
    """Result segments with no matching source produce an UNKNOWN_SEGMENT record."""
    batch = build_translation_batch(_page_ir())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_mystery",
                target_inline=[TextInline(text="ничего", lang="ru")],
            ),
        ],
    )

    records = validate_translation(batch, result, document_id="test", page_id="p0001")
    unknown = [r for r in records if r.code == CODE_UNKNOWN_SEGMENT]
    assert len(unknown) == 1
    assert unknown[0].entity_ref == "blk_mystery"


def test_validator_findings_are_waivable() -> None:
    """A waiver targeting a translation code silences the matching record."""
    batch = build_translation_batch(_page_ir(), concept_registry=_registry())
    result = TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id="blk_001",
                target_inline=[TextInline(text="Тест Стамина", lang="ru")],
            ),
            TranslatedSegment(
                segment_id="blk_002",
                target_inline=[
                    TextInline(text="Получите 1 ", lang="ru"),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Прогресс.", lang="ru"),
                ],
                concept_realizations=[
                    ConceptRealization(
                        concept_id="concept.progress",
                        surface_form="Прогресс",
                    ),
                ],
            ),
        ],
    )

    records = validate_translation(
        batch,
        result,
        concept_registry=_registry(),
        document_id="test",
        page_id="p0001",
    )
    assert any(r.code == CODE_GLOSSARY_FORBIDDEN_TARGET for r in records)

    waivers = [
        WaiverV1(
            waiver_id="w.forbidden_stamina",
            code=CODE_GLOSSARY_FORBIDDEN_TARGET,
            page_id="p0001",
            reason="Approved transliteration for glossary appendix.",
            approved_by="reviewer",
        ),
    ]
    waived = apply_waivers(records, waivers)
    forbidden = [r for r in waived if r.code == CODE_GLOSSARY_FORBIDDEN_TARGET]
    assert forbidden, "Forbidden-target record should still be present, just waived"
    assert all(r.waived for r in forbidden)
    assert all(r.waiver_ref == "w.forbidden_stamina" for r in forbidden)
