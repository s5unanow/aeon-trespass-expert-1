"""Config-propagation regression tests for non-default extraction settings.

Ensures that auxiliary CLI/debug paths honour document config rather than
falling back to implicit service defaults.  The canonical failure mode is
a helper that constructs a shared service (e.g. PageRasterProvider) with
default arguments, ignoring the document's configured raster pyramid.

Call-site inventory (as of S5U-305):

  MAIN STAGES (all properly propagate config via StageContext):
    - IngestStage.run()           → PageRasterProvider(pyramid_dpi=ctx.config…)
    - ExtractLayoutStage.run()    → PageRasterProvider(pyramid_dpi=ctx.config…)
    - SymbolsStage.run()          → PageRasterProvider(pyramid_dpi=ctx.config…)
    - TranslationStage.run()      → create_translator(config=ctx.config…)
    - SymbolsStage.run()          → TemplateCache.from_catalog(catalog_path…)

  AUXILIARY PATHS (regression-tested below):
    - eval_cmd._generate_overlays → PageRasterProvider(pyramid_dpi=param)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from atr_pipeline.services.pdf.raster_provider import PageRasterProvider
from atr_pipeline.store.artifact_store import ArtifactStore

# === Eval overlay path: pyramid_dpi propagation ===


class TestEvalOverlayConfigPropagation:
    """Regression: _generate_overlays must forward pyramid_dpi to PageRasterProvider."""

    def test_non_default_pyramid_forwarded(self) -> None:
        """Non-default pyramid [150] is forwarded to provider, not silently dropped."""
        from atr_pipeline.cli.commands.eval_cmd import _generate_overlays
        from atr_pipeline.eval.models import EvalReport

        report = MagicMock(spec=EvalReport)
        report.pages = []
        store = MagicMock(spec=ArtifactStore)

        with patch("atr_pipeline.services.pdf.raster_provider.PageRasterProvider") as mock_cls:
            _generate_overlays(store, "doc1", report, pyramid_dpi=[150])

        mock_cls.assert_called_once_with(store=store, document_id="doc1", pyramid_dpi=[150])

    def test_single_dpi_pyramid_forwarded(self) -> None:
        """Edge case: single-value pyramid [72] is forwarded unchanged."""
        from atr_pipeline.cli.commands.eval_cmd import _generate_overlays
        from atr_pipeline.eval.models import EvalReport

        report = MagicMock(spec=EvalReport)
        report.pages = []
        store = MagicMock(spec=ArtifactStore)

        with patch("atr_pipeline.services.pdf.raster_provider.PageRasterProvider") as mock_cls:
            _generate_overlays(store, "doc1", report, pyramid_dpi=[72])

        mock_cls.assert_called_once_with(store=store, document_id="doc1", pyramid_dpi=[72])

    def test_none_pyramid_does_not_override_provider_default(self) -> None:
        """When pyramid_dpi=None, provider uses its own default [300]."""
        from atr_pipeline.cli.commands.eval_cmd import _generate_overlays
        from atr_pipeline.eval.models import EvalReport

        report = MagicMock(spec=EvalReport)
        report.pages = []
        store = MagicMock(spec=ArtifactStore)

        with patch("atr_pipeline.services.pdf.raster_provider.PageRasterProvider") as mock_cls:
            _generate_overlays(store, "doc1", report)

        mock_cls.assert_called_once_with(store=store, document_id="doc1", pyramid_dpi=None)


# === PageRasterProvider: non-default pyramid semantics ===


class TestRasterProviderNonDefaultPyramid:
    """Verify PageRasterProvider respects non-default pyramid_dpi."""

    def test_custom_pyramid_stored(self) -> None:
        """Provider initialised with [150] exposes that pyramid."""
        store = MagicMock(spec=ArtifactStore)
        provider = PageRasterProvider(store=store, document_id="doc1", pyramid_dpi=[150])
        assert provider.pyramid_dpi == [150]
        assert provider.default_dpi == 150

    def test_multi_dpi_pyramid_sorted(self) -> None:
        """Provider sorts pyramid levels ascending."""
        store = MagicMock(spec=ArtifactStore)
        provider = PageRasterProvider(store=store, document_id="doc1", pyramid_dpi=[300, 72, 150])
        assert provider.pyramid_dpi == [72, 150, 300]
        assert provider.default_dpi == 300

    def test_default_pyramid_when_none(self) -> None:
        """Provider without pyramid_dpi defaults to [300]."""
        store = MagicMock(spec=ArtifactStore)
        provider = PageRasterProvider(store=store, document_id="doc1")
        assert provider.pyramid_dpi == [300]
        assert provider.default_dpi == 300


# === Config model: RasterConfig validation ===


class TestRasterConfigNonDefault:
    """Verify RasterConfig accepts non-default pyramid values."""

    def test_single_value_pyramid(self) -> None:
        from atr_pipeline.config.models import RasterConfig

        cfg = RasterConfig(pyramid_dpi=[150])
        assert cfg.pyramid_dpi == [150]

    def test_triple_pyramid(self) -> None:
        from atr_pipeline.config.models import RasterConfig

        cfg = RasterConfig(pyramid_dpi=[72, 150, 300])
        assert cfg.pyramid_dpi == [72, 150, 300]

    def test_rejects_below_minimum(self) -> None:
        import pytest

        from atr_pipeline.config.models import RasterConfig

        with pytest.raises(ValueError, match="72"):
            RasterConfig(pyramid_dpi=[50])

    def test_rejects_empty(self) -> None:
        import pytest

        from atr_pipeline.config.models import RasterConfig

        with pytest.raises(ValueError):
            RasterConfig(pyramid_dpi=[])
