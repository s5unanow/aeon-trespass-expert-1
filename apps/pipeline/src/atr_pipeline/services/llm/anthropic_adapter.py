"""Anthropic provider adapter — structured-output translation via Messages API."""

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


class AnthropicAdapter:
    """Translate batches via the Anthropic Messages API.

    Uses tool-use with a single tool whose input schema matches the
    translation result schema, forcing structured JSON output.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "claude-sonnet-4-6",
        temperature: float = 0.0,
        concept_registry: ConceptRegistryV1 | None = None,
    ) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            msg = (
                "anthropic package is required for the Anthropic adapter. "
                "Install with: uv pip install 'atr-pipeline[llm]'"
            )
            raise ImportError(msg) from exc

        self._client = Anthropic(api_key=api_key or None)
        self._model = model
        self._temperature = temperature
        self._concept_registry = concept_registry

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate a batch of segments via Anthropic tool use."""
        model = model_profile or self._model

        system_prompt = build_system_prompt(
            batch,
            concept_registry=self._concept_registry,
        )
        user_message = build_user_message(batch)
        response_schema = build_response_schema()

        log.info(
            "Anthropic translate_batch: model=%s segments=%d",
            model,
            len(batch.segments),
        )

        # Use tool-use to force structured output
        tool = {
            "name": "submit_translation",
            "description": (
                "Submit the translated segments. Call this tool with the "
                "complete translation result."
            ),
            "input_schema": response_schema,
        }

        # Build few-shot examples as conversation turns
        examples = build_few_shot_examples()
        messages: list[dict[str, str]] = []
        for ex in examples:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": user_message})

        response = self._client.messages.create(  # type: ignore[call-overload,unused-ignore]
            model=model,
            max_tokens=8192,
            temperature=self._temperature,
            system=system_prompt,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "tool", "name": "submit_translation"},
        )

        # Extract tool-use input from response
        tool_input: dict[str, object] | None = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_translation":
                tool_input = block.input
                break

        if tool_input is None:
            msg = "Anthropic response did not contain expected tool use"
            raise RuntimeError(msg)

        result = TranslationResultV1.model_validate(tool_input)
        raw_json = json.dumps(tool_input, ensure_ascii=False, separators=(",", ":"))

        meta = TranslationResponseMeta(
            provider="anthropic",
            model=model,
            raw_response=raw_json,
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )

        log.info(
            "Anthropic translate_batch complete: segments=%d",
            len(result.segments),
        )
        return TranslationResponse(result=result, meta=meta)
