"""Extract native stage — extract text and image evidence from each PDF page."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_schemas.enums import StageScope
from atr_schemas.source_manifest_v1 import SourceManifestV1


class ExtractNativeResult(BaseModel):
    """Summary of native extraction across all pages."""

    document_id: str
    page_count: int = Field(ge=1)
    page_ids: list[str]


class ExtractNativeStage:
    """Extract native PDF evidence for all pages in a document.

    Expects a SourceManifestV1 as input_data (from IngestStage) to determine
    the page count.  Falls back to reading the manifest from the artifact store.
    Stores one NativePageV1 artifact per page.
    """

    @property
    def name(self) -> str:
        return "extract_native"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> ExtractNativeResult:
        page_count = self._resolve_page_count(ctx, input_data)
        page_ids: list[str] = []

        for page_num in range(1, page_count + 1):
            page_id = f"p{page_num:04d}"
            ctx.logger.info("Extracting native evidence for %s", page_id)

            native = extract_native_page(
                ctx.config.source_pdf_path,
                page_number=page_num,
                document_id=ctx.document_id,
            )

            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="native_page.v1",
                scope="page",
                entity_id=page_id,
                data=native,
            )
            page_ids.append(page_id)

        ctx.logger.info("Extracted %d pages", len(page_ids))
        return ExtractNativeResult(
            document_id=ctx.document_id,
            page_count=len(page_ids),
            page_ids=page_ids,
        )

    @staticmethod
    def _resolve_page_count(ctx: StageContext, input_data: BaseModel | None) -> int:
        """Get page count from input manifest or artifact store."""
        if isinstance(input_data, SourceManifestV1):
            return input_data.page_count

        # Fallback: read manifest from artifact store (stored by executor
        # under schema_family="ingest", scope="document")
        manifest_dir = (
            ctx.artifact_store.root / ctx.document_id / "ingest" / "document" / ctx.document_id
        )
        if manifest_dir.exists():
            jsons = sorted(manifest_dir.glob("*.json"))
            if jsons:
                data = json.loads(jsons[-1].read_text())
                manifest = SourceManifestV1.model_validate(data)
                return manifest.page_count

        msg = (
            "Cannot determine page count: no SourceManifestV1 input and no "
            "manifest found in artifact store. Run ingest first."
        )
        raise RuntimeError(msg)
