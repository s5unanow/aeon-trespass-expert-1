"""OpenAI provider adapter — placeholder for real integration.

This adapter will use OpenAI's Responses API with structured outputs
for translation. Currently a stub that raises NotImplementedError.
"""

from __future__ import annotations

from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


class OpenAIAdapter:
    """OpenAI translation adapter (placeholder)."""

    def __init__(self, *, api_key: str = "", model: str = "gpt-4o") -> None:
        self._api_key = api_key
        self._model = model

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResultV1:
        msg = (
            "OpenAI adapter is a placeholder. "
            "Set translation.provider = 'mock' in config for testing."
        )
        raise NotImplementedError(msg)
