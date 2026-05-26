"""AGY CLI provider adapter — translation via local ``agy --print``.

AGY CLI v1 exposes a non-interactive ``--print`` mode and ``--print-timeout``.
It does not currently expose a model/effort selector in ``agy --help``. The
adapter therefore records the requested model profile in metadata and embeds it
in the prompt; actual model selection remains controlled by the user's
Antigravity CLI/session configuration until the CLI grows a stable flag.
"""

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

_DEFAULT_TIMEOUT_SECONDS = 900
_CLI_ERROR_PREFIXES = ("error:", "fatal:")


def _seconds_to_agy_duration(seconds: int) -> str:
    """Format seconds as an AGY/Go-style duration string."""
    return f"{seconds}s"


def _looks_like_agy_error(text: str) -> bool:
    """AGY can report internal failures on stdout while exiting 0."""
    normalized = text.strip().lower()
    return normalized.startswith(_CLI_ERROR_PREFIXES) or "timed out waiting" in normalized


class AgyCLIAdapter:
    """Translate batches via the local Antigravity ``agy`` CLI."""

    def __init__(
        self,
        *,
        model: str = "gemini-pro",
        concept_registry: ConceptRegistryV1 | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        reasoning_effort: str = "high",
        executable: str | None = None,
    ) -> None:
        if not model:
            msg = "AGY CLI adapter requires a non-empty desired model profile."
            raise ValueError(msg)
        if timeout_seconds <= 0:
            msg = "AGY CLI timeout_seconds must be positive."
            raise ValueError(msg)

        self._model = model
        self._concept_registry = concept_registry
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._executable = executable or "agy"

    def _build_prompt(self, batch: TranslationBatchV1, *, model: str | None = None) -> str:
        """Combine system prompt, schema, examples, and user message."""
        desired_model = model or self._model
        system_prompt = build_system_prompt(
            batch,
            concept_registry=self._concept_registry,
        )
        user_message = build_user_message(batch)
        response_schema = build_response_schema()
        examples = build_few_shot_examples()

        parts = [
            "AGY model profile requested by the pipeline: ",
            f"{desired_model} with {self._reasoning_effort} effort. ",
            "Use that profile if your current Antigravity CLI session supports it.\n\n",
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

    def _build_argv(self, prompt: str) -> list[str]:
        """Construct the current AGY v1 non-interactive argv."""
        return [
            self._executable,
            "--print-timeout",
            _seconds_to_agy_duration(self._timeout),
            "--print",
            prompt,
        ]

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate a batch of segments via ``agy --print``."""
        model = model_profile or self._model
        prompt = self._build_prompt(batch, model=model)

        log.info(
            "AGY CLI translate_batch: model_profile=%s effort=%s segments=%d",
            model,
            self._reasoning_effort,
            len(batch.segments),
        )

        try:
            proc = subprocess.run(
                self._build_argv(prompt),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"AGY CLI timed out after {self._timeout}s"
            raise RuntimeError(msg) from exc
        except FileNotFoundError as exc:
            msg = f"AGY CLI not found (executable={self._executable!r})"
            raise RuntimeError(msg) from exc

        if proc.returncode != 0:
            stderr = proc.stderr[:500] if proc.stderr else "(no stderr)"
            msg = f"AGY CLI exited with code {proc.returncode}: {stderr}"
            raise RuntimeError(msg)

        raw = proc.stdout
        if not raw or not raw.strip():
            msg = "AGY CLI returned empty output"
            raise RuntimeError(msg)
        if _looks_like_agy_error(raw) or (proc.stderr and _looks_like_agy_error(proc.stderr)):
            msg = f"AGY CLI reported an error: {(raw or proc.stderr).strip()[:500]}"
            raise RuntimeError(msg)

        data = extract_translation_result(raw, provider_label="AGY CLI")
        result = TranslationResultV1.model_validate(data)
        if result.batch_id != batch.batch_id:
            msg = f"AGY CLI returned batch_id={result.batch_id!r} but expected {batch.batch_id!r}"
            raise RuntimeError(msg)

        meta = TranslationResponseMeta(
            provider="agy-cli",
            model="agy-session-config",
            raw_response=raw,
            extra={
                "requested_model": model,
                "requested_reasoning_effort": self._reasoning_effort,
                "effective_model_verified": False,
                "executable": self._executable,
            },
        )

        log.info("AGY CLI translate_batch complete: segments=%d", len(result.segments))
        return TranslationResponse(result=result, meta=meta)


__all__ = ["AgyCLIAdapter"]
