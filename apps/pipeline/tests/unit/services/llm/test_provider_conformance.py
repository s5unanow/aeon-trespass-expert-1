"""Provider conformance tests — invariants every TranslatorAdapter satisfies.

These tests exercise a small, *portable* set of behavioral invariants
across every translation provider supported by the factory:

* ``mock`` (built-in deterministic translator)
* ``gemini-cli`` (subprocess-shaped, uses ``gemini`` on PATH)
* ``codex-cli`` (subprocess-shaped, uses ``codex`` on PATH)

Adding a new provider is a one-row change: append a tuple to
:data:`PROVIDER_CASES` whose ``adapter_factory`` builds a configured
adapter (with the appropriate external surface mocked) and the conformance
grid runs against it automatically.

All checks below mock the external boundary (subprocess for CLI providers,
no boundary for mock) — no test in this file shells out to a real
``codex`` or ``gemini`` binary. The opt-in real-subprocess smoke lives in
``test_codex_cli_smoke.py`` and is gated by the ``codex_live`` marker plus
the ``ATR_CODEX_LIVE_SMOKE=1`` env var.

Red-before posture (S5U-615 § three-input test discipline):
    Red-before confirmation: N/A — no production code change in this PR
    (test documents existing invariants); reviewer asked to cross-check
    diff.

The carve-out applies because the adapter modules
(``codex_cli_adapter.py``, ``gemini_cli_adapter.py``, ``mock_translator.py``,
``factory.py``) are untouched by this PR; these conformance tests pin
behavior already enforced by code that shipped under S5U-746/S5U-747.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from unittest.mock import patch

import pytest

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm.base import TranslationResponse, TranslatorAdapter
from atr_pipeline.services.llm.factory import create_translator
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)

# ── Helpers ───────────────────────────────────────────────────────────


def _make_batch(batch_id: str = "tr.p0001.01") -> TranslationBatchV1:
    """Minimal one-segment batch — small enough to mock cheaply."""
    return TranslationBatchV1(
        batch_id=batch_id,
        source_lang="en",
        target_lang="ru",
        segments=[
            TranslationSegment(
                segment_id="blk_001",
                block_type="heading",
                # Use the literal text the mock translator special-cases so
                # the mock provider produces a well-formed output. CLI
                # providers ignore this and use the canned mocked response.
                source_inline=[{"type": "text", "text": "Attack Test"}],  # type: ignore[list-item]
                context=SegmentContext(page_id="p0001"),
            ),
        ],
    )


def _valid_result_json(batch_id: str = "tr.p0001.01") -> str:
    """Schema-valid TranslationResultV1 JSON for a one-segment batch."""
    return json.dumps(
        {
            "batch_id": batch_id,
            "segments": [
                {
                    "segment_id": "blk_001",
                    "target_inline": [{"type": "text", "text": "Тест атаки"}],
                    "concept_realizations": [],
                },
            ],
        },
        ensure_ascii=False,
    )


def _gemini_cli_subprocess_side(payload: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """``subprocess.run`` side-effect for gemini-cli — returns *payload* on stdout."""

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0] if args else []
        return subprocess.CompletedProcess(
            args=argv if isinstance(argv, list) else [],
            returncode=0,
            stdout=payload,
            stderr="",
        )

    return _side


def _codex_cli_subprocess_side(payload: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """``subprocess.run`` side-effect for codex-cli — writes *payload* to the
    ``--output-last-message`` file in argv and returns a clean exit."""

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        from pathlib import Path

        argv = args[0] if args else []
        assert isinstance(argv, list), "subprocess.run must be called with an argv list"
        # Find the --output-last-message path and write payload into it.
        try:
            i = argv.index("--output-last-message")
        except ValueError as exc:
            msg = "codex-cli adapter must pass --output-last-message"
            raise AssertionError(msg) from exc
        Path(argv[i + 1]).write_text(payload, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="",
            stderr="",
        )

    return _side


# ── Per-provider adapter builders ────────────────────────────────────


def _build_mock_adapter(payload: str) -> Iterator[TranslatorAdapter]:
    """Yield a mock adapter; payload is ignored (mock translates deterministically)."""
    del payload  # mock can't be tricked into a specific output payload
    config = TranslationConfig(provider="mock", fallback_provider="")
    yield create_translator(config)


def _build_gemini_cli_adapter(payload: str) -> Iterator[TranslatorAdapter]:
    """Yield a gemini-cli adapter with subprocess.run mocked to return *payload*."""
    config = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="",
    )
    adapter = create_translator(config)
    with patch(
        "atr_pipeline.services.llm.gemini_cli_adapter.subprocess.run",
        side_effect=_gemini_cli_subprocess_side(payload),
    ):
        yield adapter


def _build_codex_cli_adapter(payload: str) -> Iterator[TranslatorAdapter]:
    """Yield a codex-cli adapter with subprocess.run mocked to write *payload*."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
    )
    adapter = create_translator(config)
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=_codex_cli_subprocess_side(payload),
    ):
        yield adapter


# (provider_id, expected_provider_meta_string, adapter_builder, capabilities)
#
# Capabilities are a small dict of feature flags so the conformance grid
# can skip checks that don't apply to a given provider:
#
# * ``supports_failure_injection``: False for ``mock`` — its translation
#   is derived deterministically from the request, so we can't trick it
#   into returning unparseable output.
# * ``validates_batch_id``: True if the adapter cross-checks
#   ``response.batch_id == request.batch_id`` and rejects mismatches.
#   Both ``codex-cli`` and ``gemini-cli`` enforce this invariant
#   (see CodexCLIAdapter.translate_batch and GeminiCLIAdapter.translate_batch).
#   ``mock`` has the same invariant but constructs the response from the
#   request, so no mismatch is possible.
PROVIDER_CASES: list[
    tuple[str, str, Callable[[str], Iterator[TranslatorAdapter]], dict[str, bool]]
] = [
    (
        "mock",
        "mock",
        _build_mock_adapter,
        {"supports_failure_injection": False, "validates_batch_id": False},
    ),
    (
        "gemini-cli",
        "gemini-cli",
        _build_gemini_cli_adapter,
        {"supports_failure_injection": True, "validates_batch_id": True},
    ),
    (
        "codex-cli",
        "codex-cli",
        _build_codex_cli_adapter,
        {"supports_failure_injection": True, "validates_batch_id": True},
    ),
]


# ── Conformance grid ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("provider_id", "expected_meta_provider", "builder", "caps"),
    PROVIDER_CASES,
    ids=[case[0] for case in PROVIDER_CASES],
)
def test_provider_conformance_returns_translation_response(
    provider_id: str,
    expected_meta_provider: str,
    builder: Callable[[str], Iterator[TranslatorAdapter]],
    caps: dict[str, bool],
) -> None:
    """Every provider returns a TranslationResponse with a valid result.

    Concretely: ``response.result.batch_id == request.batch_id`` and
    ``len(response.result.segments) >= 1``.
    """
    del provider_id  # parametrize id is for test display only
    batch = _make_batch()
    payload = _valid_result_json(batch.batch_id)
    gen = builder(payload)
    adapter = next(gen)
    try:
        response = adapter.translate_batch(batch)
        assert isinstance(response, TranslationResponse)
        assert response.result.batch_id == batch.batch_id
        assert len(response.result.segments) >= 1
        assert response.meta.provider == expected_meta_provider
    finally:
        for _ in gen:  # drain to release any patch context
            pass


@pytest.mark.parametrize(
    ("provider_id", "expected_meta_provider", "builder", "caps"),
    PROVIDER_CASES,
    ids=[case[0] for case in PROVIDER_CASES],
)
def test_provider_conformance_metadata_populated(
    provider_id: str,
    expected_meta_provider: str,
    builder: Callable[[str], Iterator[TranslatorAdapter]],
    caps: dict[str, bool],
) -> None:
    """Every provider populates meta.provider and a non-empty meta.model.

    Token counts may default to 0 when no usage info is available — we
    only assert their type, not their value.
    """
    del provider_id
    batch = _make_batch()
    payload = _valid_result_json(batch.batch_id)
    gen = builder(payload)
    adapter = next(gen)
    try:
        response = adapter.translate_batch(batch)
        assert response.meta.provider == expected_meta_provider
        assert isinstance(response.meta.model, str)
        assert response.meta.model  # non-empty
        assert isinstance(response.meta.input_tokens, int)
        assert isinstance(response.meta.output_tokens, int)
    finally:
        for _ in gen:
            pass


@pytest.mark.parametrize(
    ("provider_id", "expected_meta_provider", "builder", "caps"),
    PROVIDER_CASES,
    ids=[case[0] for case in PROVIDER_CASES],
)
def test_provider_conformance_rejects_batch_id_mismatch(
    provider_id: str,
    expected_meta_provider: str,
    builder: Callable[[str], Iterator[TranslatorAdapter]],
    caps: dict[str, bool],
) -> None:
    """Adapters that document the batch_id-validation invariant enforce it.

    Currently only ``codex-cli`` documents this invariant; ``gemini-cli``
    is a documented gap (it trusts upstream batch_id). ``mock`` constructs
    the response from the request so no mismatch is possible.

    When a future adapter adds the invariant, flip its
    ``validates_batch_id`` capability to True in :data:`PROVIDER_CASES`
    and this test exercises the invariant on it automatically.
    """
    if not caps.get("validates_batch_id"):
        pytest.skip(f"{provider_id} does not document the batch_id-validation invariant")
    batch = _make_batch("EXPECTED")
    wrong_payload = _valid_result_json("WRONG_BATCH")
    gen = builder(wrong_payload)
    adapter = next(gen)
    try:
        with pytest.raises((RuntimeError, ValueError)) as excinfo:
            adapter.translate_batch(batch)
        assert "batch" in str(excinfo.value).lower() or "WRONG_BATCH" in str(excinfo.value)
    finally:
        for _ in gen:
            pass


@pytest.mark.parametrize(
    ("provider_id", "expected_meta_provider", "builder", "caps"),
    PROVIDER_CASES,
    ids=[case[0] for case in PROVIDER_CASES],
)
def test_provider_conformance_error_message_is_bounded(
    provider_id: str,
    expected_meta_provider: str,
    builder: Callable[[str], Iterator[TranslatorAdapter]],
    caps: dict[str, bool],
) -> None:
    """Adapters surface bounded error messages on parse failure (no full-buffer dumps)."""
    if not caps.get("supports_failure_injection"):
        pytest.skip(f"{provider_id} produces no parse-failure path")
    # Drown the failure path in a 100k-char unparseable garbage payload —
    # if the adapter included the whole thing in the error, the str repr
    # would balloon past any reasonable bound.
    huge_garbage = "X" * 100_000
    gen = builder(huge_garbage)
    adapter = next(gen)
    try:
        with pytest.raises((RuntimeError, ValueError)) as excinfo:
            adapter.translate_batch(_make_batch())
        assert len(str(excinfo.value)) < 1500, (
            f"{provider_id} error message is unbounded: {len(str(excinfo.value))} chars"
        )
    finally:
        for _ in gen:
            pass


# ── Coverage assertion: factory provider count ───────────────────────


def test_provider_conformance_grid_covers_required_providers() -> None:
    """The conformance grid covers at least mock, gemini-cli, codex-cli.

    Pins the S5U-748 success criterion: "Existing provider factory tests
    cover at least mock, gemini-cli, and codex-cli." Adding a fourth
    provider is a one-row change to PROVIDER_CASES; this assertion stays
    a ≥ check so additions don't tighten it artificially.
    """
    covered = {row[0] for row in PROVIDER_CASES}
    assert {"mock", "gemini-cli", "codex-cli"} <= covered
