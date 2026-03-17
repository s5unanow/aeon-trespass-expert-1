"""Google Gemini provider adapter — structured-output translation via Generative AI API."""

from __future__ import annotations

import json
import logging

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


class GeminiAdapter:
    """Translate batches via the Google Generative AI API.

    Uses ``response_mime_type="application/json"`` with a ``response_schema``
    to guarantee structured output conforming to the translation result schema.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        temperature: float = 0.0,
        concept_registry: ConceptRegistryV1 | None = None,
    ) -> None:
        try:
            from google import genai  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:
            msg = (
                "google-genai package is required for the Gemini adapter. "
                "Install with: uv pip install 'atr-pipeline[llm]'"
            )
            raise ImportError(msg) from exc

        self._client = genai.Client(api_key=api_key or None)
        self._model = model
        self._temperature = temperature
        self._concept_registry = concept_registry

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResultV1:
        """Translate a batch of segments via Gemini structured outputs."""
        from google.genai import types  # type: ignore[import-not-found,unused-ignore]

        model = model_profile or self._model

        system_prompt = build_system_prompt(
            batch, concept_registry=self._concept_registry,
        )
        user_message = build_user_message(batch)
        response_schema = build_response_schema()

        # Build few-shot examples as conversation turns
        examples = build_few_shot_examples()
        messages: list[types.Content] = []
        for ex in examples:
            messages.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=ex["user"])],
                ),
            )
            messages.append(
                types.Content(
                    role="model",
                    parts=[types.Part(text=ex["assistant"])],
                ),
            )

        # Add the actual request
        messages.append(
            types.Content(
                role="user",
                parts=[types.Part(text=user_message)],
            ),
        )

        log.info(
            "Gemini translate_batch: model=%s segments=%d",
            model, len(batch.segments),
        )

        response = self._client.models.generate_content(
            model=model,
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self._temperature,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )

        raw = response.text
        if raw is None:
            msg = "Gemini returned empty response"
            raise RuntimeError(msg)

        data = json.loads(raw)
        result = TranslationResultV1.model_validate(data)

        log.info(
            "Gemini translate_batch complete: segments=%d",
            len(result.segments),
        )
        return result
