"""Tests for FallbackTranslator retry and fallback behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atr_pipeline.services.llm.base import TranslationResponse, TranslationResponseMeta
from atr_pipeline.services.llm.fallback import FallbackTranslator
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


def _ok_response(provider: str = "test") -> TranslationResponse:
    return TranslationResponse(
        result=TranslationResultV1(batch_id="b1"),
        meta=TranslationResponseMeta(provider=provider, model="m1"),
    )


def _make_batch() -> TranslationBatchV1:
    return TranslationBatchV1(batch_id="b1")


# ── Success on first try ─────────────────────────────────────────────


def test_primary_succeeds_first_try() -> None:
    primary = MagicMock()
    primary.translate_batch.return_value = _ok_response("primary")

    ft = FallbackTranslator(primary, max_retries=2, retry_delay_seconds=0)
    resp = ft.translate_batch(_make_batch())

    assert resp.meta.provider == "primary"
    assert resp.meta.extra["fallback_used"] is False
    assert resp.meta.extra["attempts"] == 1
    primary.translate_batch.assert_called_once()


# ── Retry then succeed ───────────────────────────────────────────────


def test_primary_succeeds_after_retry() -> None:
    primary = MagicMock()
    primary.translate_batch.side_effect = [
        RuntimeError("transient"),
        _ok_response("primary"),
    ]

    ft = FallbackTranslator(primary, max_retries=2, retry_delay_seconds=0)
    resp = ft.translate_batch(_make_batch())

    assert resp.meta.provider == "primary"
    assert resp.meta.extra["attempts"] == 2
    assert resp.meta.extra["fallback_used"] is False


# ── All primary retries fail → fallback succeeds ─────────────────────


def test_fallback_used_on_primary_failure() -> None:
    primary = MagicMock()
    primary.translate_batch.side_effect = RuntimeError("dead")

    fallback = MagicMock()
    fallback.translate_batch.return_value = _ok_response("fallback")

    ft = FallbackTranslator(
        primary,
        fallback,
        max_retries=1,
        retry_delay_seconds=0,
    )
    resp = ft.translate_batch(_make_batch())

    assert resp.meta.provider == "fallback"
    assert resp.meta.extra["fallback_used"] is True
    assert "dead" in resp.meta.extra["primary_error"]
    assert primary.translate_batch.call_count == 2  # 1 + 1 retry
    fallback.translate_batch.assert_called_once()


# ── Both providers fail → raises last error ──────────────────────────


def test_raises_when_both_fail() -> None:
    primary = MagicMock()
    primary.translate_batch.side_effect = RuntimeError("primary-dead")

    fallback = MagicMock()
    fallback.translate_batch.side_effect = RuntimeError("fallback-dead")

    ft = FallbackTranslator(
        primary,
        fallback,
        max_retries=0,
        retry_delay_seconds=0,
    )

    with pytest.raises(RuntimeError, match="fallback-dead"):
        ft.translate_batch(_make_batch())


# ── No fallback configured → raises primary error ────────────────────


def test_raises_without_fallback() -> None:
    primary = MagicMock()
    primary.translate_batch.side_effect = RuntimeError("only-primary")

    ft = FallbackTranslator(primary, max_retries=0, retry_delay_seconds=0)

    with pytest.raises(RuntimeError, match="only-primary"):
        ft.translate_batch(_make_batch())


# ── Zero retries means exactly one attempt ────────────────────────────


def test_zero_retries_single_attempt() -> None:
    primary = MagicMock()
    primary.translate_batch.side_effect = RuntimeError("fail")

    ft = FallbackTranslator(primary, max_retries=0, retry_delay_seconds=0)

    with pytest.raises(RuntimeError):
        ft.translate_batch(_make_batch())

    primary.translate_batch.assert_called_once()
