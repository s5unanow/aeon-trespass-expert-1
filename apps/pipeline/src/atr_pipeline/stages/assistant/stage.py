"""ChunkExportStage — export PageIRV1 pages as RuleChunkV1 semantic chunks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.assistant.chunker import chunk_page
from atr_pipeline.stages.assistant.indexer import build_index
from atr_schemas.assistant_pack_v1 import AssistantPackV1
from atr_schemas.enums import StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.rule_chunk_v1 import RuleChunkV1


class ChunkExportResult(BaseModel):
    """Summary of chunk export across all pages."""

    document_id: str
    pages_processed: int = Field(ge=0, default=0)
    chunks_produced: int = Field(ge=0, default=0)
    chunk_refs: dict[str, str] = Field(default_factory=dict)
    manifest_ref: str = ""
    index_path: str = ""


class ChunkExportStage:
    """Export PageIRV1 pages as RuleChunkV1 semantic chunks.

    Reads EN PageIRV1 artifacts, chunks each page into semantic units,
    and stores per-page RuleChunkV1 artifacts plus an AssistantPackV1
    manifest.
    """

    @property
    def name(self) -> str:
        return "chunk_export"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> ChunkExportResult:
        page_ids = ctx.filter_pages(self._resolve_en_page_ids(ctx))
        if not page_ids:
            msg = "No EN IR pages found"
            raise RuntimeError(msg)

        all_chunks: list[RuleChunkV1] = []
        chunk_refs: dict[str, str] = {}
        edition = "en"

        for page_id in page_ids:
            ir = self._load_page_ir(ctx, page_id, "en")
            if ir is None:
                ctx.logger.warning("Skipping %s: missing EN page IR", page_id)
                continue

            chunks = chunk_page(ir, ctx.document_id, edition)
            if not chunks:
                ctx.logger.info("Page %s: no chunks produced", page_id)
                continue

            for chunk in chunks:
                ref = ctx.artifact_store.put_json(
                    document_id=ctx.document_id,
                    schema_family=f"rule_chunk.v1.{edition}",
                    scope="page",
                    entity_id=page_id,
                    data=chunk,
                )
                chunk_refs[f"{page_id}.{chunk.canonical_anchor_id}"] = ref.relative_path

            all_chunks.extend(chunks)
            ctx.logger.info("Page %s: %d chunks", page_id, len(chunks))

        # Build FTS5 index from collected chunks
        index_db_path = self._build_fts_index(ctx, all_chunks, edition)
        index_rel = str(index_db_path.relative_to(ctx.artifact_store.root))

        manifest = AssistantPackV1(
            document_id=ctx.document_id,
            edition=edition,
            chunks_count=len(all_chunks),
            index_path=index_rel,
            build_id=ctx.run_id,
            generated_at=datetime.now(tz=UTC).isoformat(),
            pipeline_version="0.1.0",
        )
        manifest_ref = ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="assistant_pack.v1",
            scope="document",
            entity_id=ctx.document_id,
            data=manifest,
        )

        ctx.logger.info(
            "Chunk export complete: %d pages, %d chunks, index at %s",
            len(page_ids),
            len(all_chunks),
            index_rel,
        )

        return ChunkExportResult(
            document_id=ctx.document_id,
            pages_processed=len(page_ids),
            chunks_produced=len(all_chunks),
            chunk_refs=chunk_refs,
            manifest_ref=manifest_ref.relative_path,
            index_path=index_rel,
        )

    @staticmethod
    def _build_fts_index(ctx: StageContext, chunks: list[RuleChunkV1], edition: str) -> Path:
        """Build the FTS5 SQLite index and store it via artifact store."""
        index_dir = (
            ctx.artifact_store.root
            / ctx.document_id
            / f"assistant_index.{edition}"
            / "document"
            / ctx.document_id
        )
        index_dir.mkdir(parents=True, exist_ok=True)
        db_path = index_dir / "assistant_index.sqlite"
        build_index(chunks, db_path)
        ctx.logger.info("FTS5 index built: %d chunks indexed", len(chunks))
        return db_path

    @staticmethod
    def _resolve_en_page_ids(ctx: StageContext) -> list[str]:
        """Get page IDs from EN IR artifacts."""
        ir_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
        if not ir_dir.exists():
            return []
        return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())

    @staticmethod
    def _load_page_ir(ctx: StageContext, page_id: str, lang: str) -> PageIRV1 | None:
        """Load PageIRV1 for a specific language."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=f"page_ir.v1.{lang}",
            scope="page",
            entity_id=page_id,
        )
        if data is None:
            return None
        return PageIRV1.model_validate(data)
