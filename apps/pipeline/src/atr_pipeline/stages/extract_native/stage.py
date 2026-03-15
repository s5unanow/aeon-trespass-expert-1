"""Extract native stage — extract text and image evidence from PDF."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_schemas.enums import StageScope
from atr_schemas.native_page_v1 import NativePageV1


class ExtractNativeStage:
    """Extract native PDF evidence for a single page."""

    def __init__(self, page_number: int = 1) -> None:
        self._page_number = page_number

    @property
    def name(self) -> str:
        return "extract_native"

    @property
    def scope(self) -> StageScope:
        return StageScope.PAGE

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> NativePageV1:
        return extract_native_page(
            ctx.config.source_pdf_path,
            page_number=self._page_number,
            document_id=ctx.document_id,
        )
