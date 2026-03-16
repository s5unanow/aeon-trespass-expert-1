"""Tests for terminology enforcement in translation planner and validator."""

from atr_schemas.concept_registry_v1 import (
    ConceptRegistryV1,
    ConceptSource,
    ConceptTarget,
    ConceptV1,
    ValidationPolicy,
)
from atr_schemas.enums import LanguageCode
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

from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.validator import validate_translation


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
    """Validator flags forbidden terms in target text."""
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

    errors = validate_translation(batch, result, concept_registry=_registry())

    # Should flag forbidden "Стамина" in blk_001 and "Продвижение" in blk_002
    forbidden_errors = [e for e in errors if "Forbidden" in e or "orbidden" in e]
    assert len(forbidden_errors) >= 2


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

    errors = validate_translation(batch, result, concept_registry=_registry())

    surface_errors = [e for e in errors if "surface form" in e]
    assert len(surface_errors) == 1
    assert "Прогрессик" in surface_errors[0]


def test_validator_passes_clean_translation() -> None:
    """Validator returns no errors for a correct translation."""
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

    errors = validate_translation(batch, result, concept_registry=_registry())
    assert errors == []
