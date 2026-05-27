# ruff: noqa: RUF001  — Cyrillic prompt examples are intentional.
"""Tests for LLM prompt construction."""

import json
from collections.abc import Mapping
from typing import cast

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
                context=SegmentContext(page_id="p0001", prev_heading="Attack Test"),
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
    assert "STYLE MEMORY" in prompt
    assert "Но зажглись лишь немногие из них" in prompt
    assert "Перейдите к 0068" in prompt
    assert "с великим трепетом" in prompt
    assert "обошло древний мегаполис" in prompt
    assert "убожество великолепия" in prompt
    assert "См. 0068" in prompt
    assert "передовой отряд" in prompt
    assert "ignore English syntax" in prompt
    assert "Минойц" not in prompt


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
    assert data["segments"][0]["source_context"]["next_segment_text"] == "Gain 1  Progress."
    assert data["segments"][1]["source_context"]["prev_segment_text"] == "Attack Test"
    assert data["segments"][0]["short_fragment_requires_context"] is True


def test_user_message_marks_narrative_group_contract() -> None:
    from atr_pipeline.stages.translation.planner import build_translation_batch
    from atr_schemas.enums import LanguageCode
    from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1, ParagraphBlock

    batch = build_translation_batch(
        PageIRV1(
            document_id="test",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[
                HeadingBlock(block_id="h1", children=[TextInline(text="So it begins")]),
                ParagraphBlock(block_id="p1", children=[TextInline(text="But only a few.")]),
            ],
            reading_order=["h1", "p1"],
        )
    )

    data = json.loads(build_user_message(batch))
    segment = data["segments"][0]

    assert segment["translation_unit"] == "full_section"
    assert "[h1]" in segment["section_source_text"]
    assert "[p1]" in segment["section_source_text"]
    assert "translation-block:" in segment["block_boundary_contract"]
    assert any(
        node["type"] == "xref" and node["target_section_id"] == "translation-block:h1"
        for node in segment["source_inline"]
    )


def test_response_schema_structure() -> None:
    schema = build_response_schema()
    properties = cast(Mapping[str, object], schema["properties"])

    assert schema["type"] == "object"
    assert "batch_id" in properties
    assert "segments" in properties
    segments = cast(Mapping[str, object], properties["segments"])
    seg_items = cast(Mapping[str, object], segments["items"])
    seg_properties = cast(Mapping[str, object], seg_items["properties"])
    assert "target_inline" in seg_properties
    assert "concept_realizations" in seg_properties


def test_factory_creates_mock() -> None:
    from atr_pipeline.config.models import TranslationConfig
    from atr_pipeline.services.llm.factory import create_translator
    from atr_pipeline.services.llm.mock_translator import MockTranslator

    config = TranslationConfig(provider="mock")
    adapter = create_translator(config)
    assert isinstance(adapter, MockTranslator)


def test_factory_rejects_unknown_provider() -> None:
    """Unknown providers are rejected by the config validator (S5U-746)."""
    import pytest

    from atr_pipeline.config.models import TranslationConfig

    with pytest.raises(ValueError, match="Unknown translation provider"):
        TranslationConfig(provider="nonexistent")
