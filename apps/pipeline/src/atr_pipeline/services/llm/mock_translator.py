"""Mock translator — deterministic fixture-backed translation for testing."""

from __future__ import annotations

from atr_schemas.page_ir_v1 import TextInline
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

    def translate_batch(self, batch: TranslationBatchV1) -> TranslationResultV1:
        """Translate segments using hard-coded fixture data."""
        translated: list[TranslatedSegment] = []

        for segment in batch.segments:
            target_inline = []
            concept_realizations = []

            if segment.block_type == "heading":
                # Translate heading text
                source_text = " ".join(
                    c.text for c in segment.source_inline if c.type == "text"  # type: ignore[union-attr]
                )
                target_inline = [
                    TextInline(text="Проверка атаки", lang="ru")  # type: ignore[arg-type]
                    if source_text == "Attack Test"
                    else TextInline(text=source_text, lang="ru"),  # type: ignore[arg-type]
                ]
            elif segment.block_type == "paragraph":
                # Translate paragraph, preserving icon nodes
                for node in segment.source_inline:
                    if node.type == "icon":
                        target_inline.append(node)
                        concept_realizations.append(
                            ConceptRealization(
                                concept_id=f"concept.{node.symbol_id.removeprefix('sym.')}",  # type: ignore[union-attr]
                                surface_form="Прогресс",
                            )
                        )
                    elif node.type == "text":
                        text = node.text  # type: ignore[union-attr]
                        # Simple mock translations
                        text = text.replace("Gain 1 ", "Получите 1 ")
                        text = text.replace(" Progress.", " Прогресс.")
                        target_inline.append(TextInline(text=text, lang="ru"))  # type: ignore[arg-type]
                    else:
                        target_inline.append(node)

            translated.append(
                TranslatedSegment(
                    segment_id=segment.segment_id,
                    target_inline=target_inline,
                    concept_realizations=concept_realizations,
                )
            )

        return TranslationResultV1(
            batch_id=batch.batch_id,
            segments=translated,
        )
