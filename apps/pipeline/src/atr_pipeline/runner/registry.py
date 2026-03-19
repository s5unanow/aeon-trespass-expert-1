"""Stage registry — maps stage names to Stage protocol instances."""

from __future__ import annotations

from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.publish.stage import PublishStage
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage


def build_stage_registry() -> dict[str, Stage]:
    """Create the default stage registry with all walking-skeleton stages."""
    return {
        "ingest": IngestStage(),
        "extract_native": ExtractNativeStage(),
        "symbols": SymbolsStage(),
        "structure": StructureStage(),
        "translate": TranslationStage(),
        "render": RenderStage(),
        "qa": QAStage(),
        "publish": PublishStage(),
    }
