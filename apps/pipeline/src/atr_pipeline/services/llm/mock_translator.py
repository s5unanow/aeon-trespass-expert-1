"""Mock translator — deterministic fixture-backed translation for testing."""

from __future__ import annotations

from atr_pipeline.services.llm.base import TranslationResponse, TranslationResponseMeta
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import IconInline, InlineNode, TextInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import (
    ConceptRealization,
    TranslatedSegment,
    TranslationResultV1,
)

# Hard-coded translations for the walking skeleton
_MOCK_TRANSLATIONS: dict[str, list[dict[str, str]]] = {
    "Attack Test": [{"type": "text", "text": "Проверка атаки", "lang": "ru"}],
}


class MockTranslator:
    """Deterministic mock translator for the walking skeleton."""

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate segments using hard-coded fixture data."""
        translated: list[TranslatedSegment] = []

        for segment in batch.segments:
            target_inline: list[InlineNode] = []
            concept_realizations: list[ConceptRealization] = []

            if segment.block_type == "heading":
                # Translate heading text
                source_text = " ".join(
                    c.text for c in segment.source_inline if c.type == "text" and hasattr(c, "text")
                )
                target_inline = [
                    TextInline(text="Проверка атаки", lang=LanguageCode.RU)
                    if source_text == "Attack Test"
                    else TextInline(text=source_text, lang=LanguageCode.RU),
                ]
            elif segment.block_type == "paragraph":
                # Translate paragraph, preserving icon nodes
                for node in segment.source_inline:
                    if isinstance(node, IconInline):
                        target_inline.append(node)
                        concept_realizations.append(
                            ConceptRealization(
                                concept_id=f"concept.{node.symbol_id.removeprefix('sym.')}",
                                surface_form="Прогресс",
                            )
                        )
                    elif node.type == "text" and hasattr(node, "text"):
                        text = node.text
                        # Simple mock translations
                        text = text.replace("Gain 1 ", "Получите 1 ")
                        text = text.replace(" Progress.", " Прогресс.")
                        target_inline.append(TextInline(text=text, lang=LanguageCode.RU))
                    else:
                        target_inline.append(node)

            translated.append(
                TranslatedSegment(
                    segment_id=segment.segment_id,
                    target_inline=target_inline,
                    concept_realizations=concept_realizations,
                )
            )

        result = TranslationResultV1(
            batch_id=batch.batch_id,
            segments=translated,
        )
        meta = TranslationResponseMeta(
            provider="mock",
            model="mock-v1",
            raw_response=result.model_dump_json(),
        )
        return TranslationResponse(result=result, meta=meta)
