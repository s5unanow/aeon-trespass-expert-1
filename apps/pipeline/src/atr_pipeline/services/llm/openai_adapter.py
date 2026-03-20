"""OpenAI provider adapter — structured-output translation via Chat Completions."""

from __future__ import annotations

import json
import logging

from atr_pipeline.services.llm.base import TranslationResponse, TranslationResponseMeta
from atr_pipeline.services.llm.prompt_builder import (
    build_few_shot_examples,
    build_response_schema,
    build_system_prompt,
    build_user_message,
)
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1

log = logging.getLogger(__name__)


class OpenAIAdapter:
    """Translate batches via the OpenAI Chat Completions API.

    Uses ``response_format={"type": "json_schema", ...}`` (structured
    outputs) so the response is guaranteed to conform to the translation
    result schema.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "gpt-4o",
        temperature: float = 0.0,
        concept_registry: ConceptRegistryV1 | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            msg = (
                "openai package is required for the OpenAI adapter. "
                "Install with: uv pip install 'atr-pipeline[llm]'"
            )
            raise ImportError(msg) from exc

        self._client = OpenAI(api_key=api_key or None)
        self._model = model
        self._temperature = temperature
        self._concept_registry = concept_registry

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate a batch of segments via OpenAI structured outputs."""
        model = model_profile or self._model

        system_prompt = build_system_prompt(
            batch,
            concept_registry=self._concept_registry,
        )
        user_message = build_user_message(batch)
        response_schema = build_response_schema()

        # Build few-shot examples as conversation turns
        examples = build_few_shot_examples()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for ex in examples:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": user_message})

        log.info(
            "OpenAI translate_batch: model=%s segments=%d",
            model,
            len(batch.segments),
        )

        response = self._client.chat.completions.create(  # type: ignore[call-overload,unused-ignore]
            model=model,
            temperature=self._temperature,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "translation_result",
                    "strict": True,
                    "schema": response_schema,
                },
            },
        )

        raw = response.choices[0].message.content
        if raw is None:
            msg = "OpenAI returned empty response"
            raise RuntimeError(msg)

        data = json.loads(raw)
        result = TranslationResultV1.model_validate(data)

        usage = response.usage
        meta = TranslationResponseMeta(
            provider="openai",
            model=model,
            raw_response=raw,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )

        log.info(
            "OpenAI translate_batch complete: segments=%d",
            len(result.segments),
        )
        return TranslationResponse(result=result, meta=meta)
