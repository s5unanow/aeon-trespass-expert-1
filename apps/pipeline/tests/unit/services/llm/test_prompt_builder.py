"""Tests for LLM prompt construction."""

import json

from atr_pipeline.services.llm.prompt_builder import (
    build_response_schema,
    build_system_prompt,
    build_user_message,
)
from atr_schemas.concept_registry_v1 import (
    ConceptRegistryV1,
    ConceptSource,
    ConceptTarget,
    ConceptV1,
)
from atr_schemas.page_ir_v1 import IconInline, TextInline
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)


def _sample_batch() -> TranslationBatchV1:
    return TranslationBatchV1(
        batch_id="tr.p0001.01",
        source_lang="en",
        target_lang="ru",
        segments=[
            TranslationSegment(
                segment_id="blk_001",
                block_type="heading",
                source_inline=[TextInline(text="Attack Test")],
                context=SegmentContext(page_id="p0001"),
            ),
            TranslationSegment(
                segment_id="blk_002",
                block_type="paragraph",
                source_inline=[
                    TextInline(text="Gain 1 "),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Progress."),
                ],
                locked_nodes=["sym.progress"],
                required_concepts=["concept.progress"],
                context=SegmentContext(
                    page_id="p0001", prev_heading="Attack Test"
                ),
            ),
        ],
    )


def _sample_registry() -> ConceptRegistryV1:
    return ConceptRegistryV1(
        concepts=[
            ConceptV1(
                concept_id="concept.progress",
                kind="icon_term",
                source=ConceptSource(lemma="Progress"),
                target=ConceptTarget(
                    lemma="Прогресс",
                    allowed_surface_forms=["Прогресс", "Прогресса"],
                ),
                icon_binding="sym.progress",
                forbidden_targets=["Продвижение"],
            ),
        ],
    )


def test_system_prompt_contains_terminology() -> None:
    batch = _sample_batch()
    registry = _sample_registry()
    prompt = build_system_prompt(batch, concept_registry=registry)

    assert "Прогресс" in prompt
    assert "Продвижение" in prompt
    assert "FORBIDDEN" in prompt
    assert "sym.progress" in prompt


def test_system_prompt_without_registry() -> None:
    batch = _sample_batch()
    prompt = build_system_prompt(batch)

    assert "TERMINOLOGY" not in prompt
    assert "icon" in prompt.lower()


def test_user_message_is_valid_json() -> None:
    batch = _sample_batch()
    msg = build_user_message(batch)
    data = json.loads(msg)

    assert data["batch_id"] == "tr.p0001.01"
    assert len(data["segments"]) == 2
    assert data["segments"][1]["locked_nodes"] == ["sym.progress"]


def test_response_schema_structure() -> None:
    schema = build_response_schema()

    assert schema["type"] == "object"
    assert "batch_id" in schema["properties"]
    assert "segments" in schema["properties"]
    seg_items = schema["properties"]["segments"]["items"]
    assert "target_inline" in seg_items["properties"]
    assert "concept_realizations" in seg_items["properties"]


def test_factory_creates_mock() -> None:
    from atr_pipeline.config.models import TranslationConfig
    from atr_pipeline.services.llm.factory import create_translator
    from atr_pipeline.services.llm.mock_translator import MockTranslator

    config = TranslationConfig(provider="mock")
    adapter = create_translator(config)
    assert isinstance(adapter, MockTranslator)


def test_factory_rejects_unknown_provider() -> None:
    import pytest

    from atr_pipeline.config.models import TranslationConfig
    from atr_pipeline.services.llm.factory import create_translator

    config = TranslationConfig(provider="nonexistent")
    with pytest.raises(ValueError, match="Unknown translation provider"):
        create_translator(config)
