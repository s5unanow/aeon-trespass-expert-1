"""Per-batch translator routing for hard-page escalation (S5U-1542).

``TranslatorRouter`` owns two adapters built from the same config: the
``model_default`` translator (built eagerly — identical to the pre-S5U-1542
single-translator path) and the ``model_hard`` translator (built lazily, only
when the first hard page is routed).

The hard translator is created from a config copy in which ``model_default`` is
replaced by ``model_hard``; ``fallback_provider`` / ``fallback_model`` are left
untouched, so provider fallback semantics are unchanged on both paths. This is
why we build a second adapter rather than forwarding ``model_hard`` via
``translate_batch(model_profile=...)`` — that hook leaks into the fallback
adapter and would silently override ``fallback_model`` on hard pages.

The ``translator_factory`` is injected so the stage passes its own
module-level ``create_translator`` binding, keeping existing tests that
monkeypatch ``stage.create_translator`` effective.
"""

from __future__ import annotations

from collections.abc import Callable

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm.base import TranslatorAdapter
from atr_pipeline.stages.translation.hardness import HardnessScore
from atr_schemas.concept_registry_v1 import ConceptRegistryV1

TranslatorFactory = Callable[..., TranslatorAdapter]


class TranslatorRouter:
    """Route each batch to the ``model_default`` or ``model_hard`` translator."""

    def __init__(
        self,
        config: TranslationConfig,
        *,
        concept_registry: ConceptRegistryV1 | None,
        translator_factory: TranslatorFactory,
    ) -> None:
        self._config = config
        self._concept_registry = concept_registry
        self._factory = translator_factory
        self._default: TranslatorAdapter = translator_factory(
            config,
            concept_registry=concept_registry,
        )
        self._hard: TranslatorAdapter | None = None

    def _hard_translator(self) -> TranslatorAdapter:
        if self._hard is None:
            hard_config = self._config.model_copy(
                update={"model_default": self._config.model_hard},
                deep=True,
            )
            self._hard = self._factory(
                hard_config,
                concept_registry=self._concept_registry,
            )
        return self._hard

    def select(self, hardness: HardnessScore | None) -> tuple[TranslatorAdapter, str]:
        """Return ``(translator, chosen_model)`` for a page's hardness verdict.

        ``hardness is None`` means routing is disabled — always ``model_default``.
        """
        if hardness is not None and hardness.is_hard:
            return self._hard_translator(), self._config.model_hard
        return self._default, self._config.model_default
