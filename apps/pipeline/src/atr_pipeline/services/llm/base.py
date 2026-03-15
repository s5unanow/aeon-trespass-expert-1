"""Base LLM provider adapter protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


@runtime_checkable
class TranslatorAdapter(Protocol):
    """Protocol for translation provider adapters.

    Implementations: MockTranslator, OpenAIAdapter, AnthropicAdapter.
    """

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResultV1: ...
