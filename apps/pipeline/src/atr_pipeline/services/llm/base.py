"""Base LLM provider adapter protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


@dataclass
class TranslationResponseMeta:
    """Metadata captured from a translation LLM call for auditability."""

    provider: str = ""
    model: str = ""
    raw_response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class TranslationResponse:
    """Bundle of translated result and response metadata."""

    result: TranslationResultV1
    meta: TranslationResponseMeta


@runtime_checkable
class TranslatorAdapter(Protocol):
    """Protocol for translation provider adapters.

    Implementations: MockTranslator, OpenAIAdapter, AnthropicAdapter, GeminiAdapter.
    """

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse: ...
