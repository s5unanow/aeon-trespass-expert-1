"""S5U-1542 — ``TranslatorRouter`` selects model_default vs model_hard.

The router builds the default translator eagerly (identical to today's
behaviour) and the ``model_hard`` translator lazily, only when a hard page is
first seen. Provider fallback semantics are untouched: the hard translator is
built from a config whose ``model_default`` is swapped for ``model_hard`` while
``fallback_provider`` / ``fallback_model`` stay as configured.
"""

from __future__ import annotations

from dataclasses import dataclass

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm.base import TranslationResponse, TranslationResponseMeta
from atr_pipeline.stages.translation.hardness import (
    HardnessScore,
    HardnessSignals,
)
from atr_pipeline.stages.translation.routing import TranslatorRouter
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


@dataclass
class _FakeAdapter:
    """A ``TranslatorAdapter`` that reports the model it was built with."""

    model: str

    def translate_batch(
        self, batch: TranslationBatchV1, model_profile: str = ""
    ) -> TranslationResponse:
        return TranslationResponse(
            result=TranslationResultV1(batch_id=batch.batch_id),
            meta=TranslationResponseMeta(model=self.model),
        )


def _score(is_hard: bool) -> HardnessScore:
    return HardnessScore(
        score=9.0 if is_hard else 0.0,
        threshold=2.0,
        is_hard=is_hard,
        features={},
        contributions={},
        signals=HardnessSignals(0, 0, 0, 0, 0),
    )


class _RecordingFactory:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(
        self, config: TranslationConfig, *, concept_registry: object = None
    ) -> _FakeAdapter:
        self.calls.append(config.model_default)
        return _FakeAdapter(model=config.model_default)


def _config() -> TranslationConfig:
    return TranslationConfig(
        provider="mock",
        model_default="mock-easy",
        model_hard="mock-hard",
        fallback_provider="",
    )


def test_default_translator_built_eagerly() -> None:
    """The default translator is constructed at router creation."""
    factory = _RecordingFactory()
    TranslatorRouter(_config(), concept_registry=None, translator_factory=factory)
    assert factory.calls == ["mock-easy"]


def test_select_easy_returns_default() -> None:
    factory = _RecordingFactory()
    router = TranslatorRouter(_config(), concept_registry=None, translator_factory=factory)
    adapter, model = router.select(_score(is_hard=False))
    assert model == "mock-easy"
    assert isinstance(adapter, _FakeAdapter)
    assert adapter.model == "mock-easy"
    # No hard translator was built for an easy page.
    assert factory.calls == ["mock-easy"]


def test_select_none_returns_default() -> None:
    """``select(None)`` (hardness disabled) always routes to model_default."""
    factory = _RecordingFactory()
    router = TranslatorRouter(_config(), concept_registry=None, translator_factory=factory)
    adapter, model = router.select(None)
    assert model == "mock-easy"
    assert isinstance(adapter, _FakeAdapter)
    assert adapter.model == "mock-easy"
    assert factory.calls == ["mock-easy"]


def test_select_hard_returns_hard_and_builds_lazily() -> None:
    """A hard verdict routes to model_hard, building that translator once."""
    factory = _RecordingFactory()
    router = TranslatorRouter(_config(), concept_registry=None, translator_factory=factory)
    adapter, model = router.select(_score(is_hard=True))
    assert model == "mock-hard"
    assert isinstance(adapter, _FakeAdapter)
    assert adapter.model == "mock-hard"
    # Default (eager) + hard (lazy) = two builds, hard swapped model_default.
    assert factory.calls == ["mock-easy", "mock-hard"]


def test_hard_translator_is_cached() -> None:
    """The lazily-built hard translator is reused across hard pages."""
    factory = _RecordingFactory()
    router = TranslatorRouter(_config(), concept_registry=None, translator_factory=factory)
    a1, _ = router.select(_score(is_hard=True))
    a2, _ = router.select(_score(is_hard=True))
    assert a1 is a2
    assert factory.calls == ["mock-easy", "mock-hard"]  # built once


def test_hard_config_preserves_fallback() -> None:
    """Swapping model_default for model_hard leaves fallback fields intact."""
    captured: list[TranslationConfig] = []

    def factory(config: TranslationConfig, *, concept_registry: object = None) -> _FakeAdapter:
        captured.append(config)
        return _FakeAdapter(model=config.model_default)

    cfg = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        model_hard="gemini-2.5-pro",
        fallback_provider="gemini",
        fallback_model="gemini-2.5-flash",
    )
    router = TranslatorRouter(cfg, concept_registry=None, translator_factory=factory)
    router.select(_score(is_hard=True))
    hard_cfg = captured[-1]
    assert hard_cfg.model_default == "gemini-2.5-pro"  # swapped to model_hard
    assert hard_cfg.fallback_provider == "gemini"  # unchanged
    assert hard_cfg.fallback_model == "gemini-2.5-flash"  # unchanged
