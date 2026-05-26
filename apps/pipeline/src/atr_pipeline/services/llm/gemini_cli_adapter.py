"""Gemini CLI provider adapter — translation via local ``gemini`` command."""

from __future__ import annotations

import json
import logging
import subprocess

from atr_pipeline.services.llm.base import TranslationResponse, TranslationResponseMeta
from atr_pipeline.services.llm.cli_result import extract_translation_result
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

_DEFAULT_TIMEOUT_SECONDS = 300


def _extract_result(raw: str) -> dict[str, object]:
    """Parse CLI output into a translation result dict.

    Handles direct JSON, markdown-fenced JSON, and response envelopes.
    """
    return extract_translation_result(raw, provider_label="Gemini CLI")


class GeminiCLIAdapter:
    """Translate batches via the local Gemini CLI.

    Shells out to ``gemini -p "<prompt>" --model <model>`` instead of
    calling the Google GenAI API directly.  This uses the flat-rate CLI
    subscription instead of per-token billing.
    """

    def __init__(
        self,
        *,
        model: str = "gemini-2.5-flash",
        concept_registry: ConceptRegistryV1 | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._concept_registry = concept_registry
        self._timeout = timeout_seconds

    def _build_prompt(self, batch: TranslationBatchV1) -> str:
        """Combine system prompt, schema, examples, and user message."""
        system_prompt = build_system_prompt(
            batch,
            concept_registry=self._concept_registry,
        )
        user_message = build_user_message(batch)
        response_schema = build_response_schema()
        examples = build_few_shot_examples()

        parts = [
            system_prompt,
            "\n\nYou MUST respond with valid JSON matching this schema:\n",
            json.dumps(response_schema, indent=2),
            "\n\n",
        ]

        for i, ex in enumerate(examples, 1):
            parts.append(
                f"--- Example {i} ---\nInput:\n{ex['user']}\n\nOutput:\n{ex['assistant']}\n\n"
            )

        parts.append(f"--- Your task ---\nInput:\n{user_message}\n\nOutput:\n")
        return "".join(parts)

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate a batch of segments via the Gemini CLI."""
        model = model_profile or self._model
        prompt = self._build_prompt(batch)

        log.info(
            "Gemini CLI translate_batch: model=%s segments=%d",
            model,
            len(batch.segments),
        )

        try:
            proc = subprocess.run(
                ["gemini", "-p", prompt, "--model", model],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"Gemini CLI timed out after {self._timeout}s"
            raise RuntimeError(msg) from exc
        except FileNotFoundError as exc:
            msg = "gemini CLI not found on PATH — is it installed?"
            raise RuntimeError(msg) from exc

        if proc.returncode != 0:
            stderr = proc.stderr[:500] if proc.stderr else "(no stderr)"
            msg = f"Gemini CLI exited with code {proc.returncode}: {stderr}"
            raise RuntimeError(msg)

        raw = proc.stdout
        if not raw or not raw.strip():
            msg = "Gemini CLI returned empty output"
            raise RuntimeError(msg)

        data = _extract_result(raw)
        result = TranslationResultV1.model_validate(data)

        if result.batch_id != batch.batch_id:
            msg = (
                f"Gemini CLI returned batch_id={result.batch_id!r} but expected {batch.batch_id!r}"
            )
            raise RuntimeError(msg)

        meta = TranslationResponseMeta(
            provider="gemini-cli",
            model=model,
            raw_response=raw,
        )

        log.info(
            "Gemini CLI translate_batch complete: segments=%d",
            len(result.segments),
        )
        return TranslationResponse(result=result, meta=meta)
