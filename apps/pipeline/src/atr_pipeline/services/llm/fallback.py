"""Retry-and-fallback translator wrapper."""

from __future__ import annotations

import logging
import time

from atr_pipeline.services.llm.base import TranslationResponse, TranslatorAdapter
from atr_schemas.translation_batch_v1 import TranslationBatchV1

logger = logging.getLogger(__name__)


class FallbackTranslator:
    """Translator that retries the primary adapter, then falls back.

    Wraps a *primary* and optional *fallback* ``TranslatorAdapter``.
    On each call to ``translate_batch``:

    1. Try the primary adapter up to *max_retries* + 1 times.
    2. If all primary attempts fail and a fallback is configured,
       try the fallback with the same retry budget.
    3. If both fail, re-raise the last exception.

    The winning response has ``meta.extra`` enriched with provenance:
    ``fallback_used``, ``attempts``, and (on fallback) ``primary_error``.
    """

    def __init__(
        self,
        primary: TranslatorAdapter,
        fallback: TranslatorAdapter | None = None,
        *,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate with retry + fallback semantics."""
        primary_result = self._try_with_retries(
            self._primary,
            batch,
            model_profile,
            label="primary",
        )
        if isinstance(primary_result, TranslationResponse):
            primary_result.meta.extra["fallback_used"] = False
            return primary_result

        # Primary exhausted — try fallback
        if self._fallback is not None:
            logger.warning(
                "Primary provider failed, trying fallback: %s",
                primary_result,
            )
            fb_result = self._try_with_retries(
                self._fallback,
                batch,
                model_profile,
                label="fallback",
            )
            if isinstance(fb_result, TranslationResponse):
                fb_result.meta.extra["fallback_used"] = True
                fb_result.meta.extra["primary_error"] = str(primary_result)
                return fb_result
            # Both failed — raise fallback error chained to primary
            raise fb_result from primary_result

        raise primary_result

    # ------------------------------------------------------------------

    def _try_with_retries(
        self,
        adapter: TranslatorAdapter,
        batch: TranslationBatchV1,
        model_profile: str,
        *,
        label: str,
    ) -> TranslationResponse | Exception:
        """Try *adapter* up to ``max_retries + 1`` times.

        Returns the response on success, or the last exception on failure.
        """
        last_exc: Exception | None = None
        attempts = self._max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                resp = adapter.translate_batch(batch, model_profile)
                resp.meta.extra["attempts"] = attempt
                return resp
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "%s attempt %d/%d failed: %s",
                    label,
                    attempt,
                    attempts,
                    exc,
                    exc_info=True,
                )
                if attempt < attempts:
                    time.sleep(self._retry_delay)

        assert last_exc is not None
        return last_exc
