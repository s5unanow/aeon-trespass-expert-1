"""Ingest stage — fingerprint PDF, rasterize pages, extract images, emit SourceManifestV1."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.pdf.image_extractor import extract_page_images
from atr_pipeline.services.pdf.raster_provider import PageRasterProvider
from atr_pipeline.stages.ingest.image_set import (
    ImageSetIngestError,
    PreparedImageSet,
    prepare_image_set_source,
)
from atr_pipeline.stages.ingest.manifest_builder import build_manifest
from atr_pipeline.stages.ingest.pdf_fingerprint import fingerprint_pdf
from atr_pipeline.utils.hashing import sha256_file
from atr_schemas.enums import StageScope
from atr_schemas.page_images_v1 import PageImageEntry, PageImagesV1
from atr_schemas.source_manifest_v1 import PageEntry, SourceManifestV1


class IngestStage:
    """Ingest: register the source PDF, rasterize pages, emit manifest."""

    @property
    def name(self) -> str:
        return "ingest"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        # 1.2 -> 1.3 (S5U-1537): IngestStage supports image-set sources,
        # folds image source identity into cache keys, and registers raw-image
        # bytes plus metadata artifacts on image-set cache misses.
        # 1.1 -> 1.2 (S5U-1221): IngestStage now contributes
        # ``extra_cache_inputs`` that fold the source-PDF *content* hash
        # into the cache key (the config hash only carries the PDF
        # *path*; ``fingerprint_pdf`` ran only inside ``run()``, i.e. on a
        # cache miss). Without this, swapping the PDF at the configured
        # path cache-hit the stale ``SourceManifestV1`` and the whole
        # downstream chain silently reflected the previous PDF. The bump
        # invalidates every 1.1 ingest event so a re-run recomputes the
        # cache key from the current PDF bytes. Per ``.claude/rules/pipeline.md``
        # § "Stage-output cache invalidation", a cache-key composition change
        # warrants a version bump in the same PR so the change is
        # self-documenting and the reviewer cache-hit probe stays quiet.
        # 1.0 -> 1.1 (S5U-730): IngestStage emits a per-page
        # ``page_images.v1`` manifest after the PDF image-extraction loop,
        # consumed by the QA stage's ``_filter_publishable_pages``.
        return "1.3"

    def extra_cache_inputs(self, ctx: StageContext) -> list[str]:
        """Fold the source-PDF content hash into the ingest cache key (S5U-1221).

        ``DocumentBuildConfig`` carries the PDF *path*, not its bytes, and
        ``fingerprint_pdf`` runs only inside :meth:`run` (on a cache miss). The
        executor checks the cache *before* calling ``run``, so a replaced PDF at
        the same path would otherwise cache-hit the stale ``SourceManifestV1``
        and every downstream stage would cache-hit in turn — the whole run
        silently reflecting the previous PDF (an S5U-662-class hazard;
        previously only the web export caught it via ``verify_source_pdf_sha``,
        S5U-889). Hashing the file bytes here invalidates ingest — and the
        downstream chain — whenever the source PDF changes.

        Uses a plain ``sha256_file`` rather than ``fingerprint_pdf`` to avoid a
        full PyMuPDF parse on every invocation (the page count is recomputed in
        :meth:`run`). A missing PDF returns the ``pdf_sha256:missing`` sentinel
        rather than raising — :meth:`run` already raises ``FileNotFoundError``
        with a clear message and remains the authoritative failure point.
        """
        if ctx.config.document.source_kind == "image_set":
            try:
                prepared = prepare_image_set_source(
                    manifest_path=ctx.config.image_set_manifest_path,
                    repo_root=ctx.repo_root,
                )
            except ImageSetIngestError:
                return ["image_set_sha256:invalid"]
            return [
                f"image_set_sha256:{prepared.source_image_set_sha256}",
                f"image_set_manifest_sha256:{prepared.manifest_sha256}",
            ]

        pdf_path = ctx.config.source_pdf_path
        if not pdf_path.exists():
            return ["pdf_sha256:missing"]
        return [f"pdf_sha256:{sha256_file(pdf_path)}"]

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> SourceManifestV1:
        if ctx.config.document.source_kind == "image_set":
            prepared = prepare_image_set_source(
                manifest_path=ctx.config.image_set_manifest_path,
                repo_root=ctx.repo_root,
            )
            return _run_image_set_ingest(ctx, prepared)

        pdf_path = ctx.config.source_pdf_path
        if not pdf_path.exists():
            msg = f"Source PDF not found: {pdf_path}"
            raise FileNotFoundError(msg)

        ctx.logger.info("Fingerprinting %s", pdf_path.name)
        sha256, page_count = fingerprint_pdf(pdf_path)

        # Build raster provider for multi-DPI pyramid rendering
        raster_provider = PageRasterProvider(
            store=ctx.artifact_store,
            document_id=ctx.document_id,
            pyramid_dpi=ctx.config.extraction.raster.pyramid_dpi,
        )

        all_page_ids = [f"p{n:04d}" for n in range(1, page_count + 1)]
        active_pages = set(ctx.filter_pages(all_page_ids))
        for page_num in range(1, page_count + 1):
            page_id = f"p{page_num:04d}"
            if active_pages and page_id not in active_pages:
                continue
            dpis = raster_provider.pyramid_dpi
            ctx.logger.info("Rasterizing %s at %s DPI", page_id, dpis)
            raster_provider.render_page(
                pdf_path,
                page_num,
                page_id,
                source_pdf_sha256=sha256,
            )

            # Extract embedded images from the page
            images = extract_page_images(pdf_path, page_number=page_num)
            page_image_entries: list[PageImageEntry] = []
            for img in images:
                ctx.logger.info(
                    "Extracted image %s (%dx%d) from %s",
                    img.image_id,
                    img.width_px,
                    img.height_px,
                    page_id,
                )
                ctx.artifact_store.put_bytes(
                    document_id=ctx.document_id,
                    schema_family="image",
                    scope="page",
                    entity_id=img.image_id,
                    data=img.image_bytes,
                    extension=img.extension,
                )
                page_image_entries.append(
                    PageImageEntry(
                        image_id=img.image_id,
                        width_px=img.width_px,
                        height_px=img.height_px,
                        extension=img.extension,
                    )
                )

            # S5U-730 — emit a per-page manifest so QA can align its
            # dead-page-ref suppression set with the web exporter's
            # image-injection rescue behaviour without re-loading the
            # source PDF on every QA invocation. The manifest is written
            # for every active page (even when no images were extracted)
            # so QA can distinguish "no images at this page" from "ingest
            # never ran on this page" — both safely degrade to the
            # render-only filter, but the explicit empty manifest is the
            # affirmative signal of "ingest ran, found nothing rescuable."
            page_images_payload = PageImagesV1(
                document_id=ctx.document_id,
                page_id=page_id,
                page_number=page_num,
                images=page_image_entries,
            )
            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="page_images.v1",
                scope="page",
                entity_id=page_id,
                data=page_images_payload,
            )

        manifest = build_manifest(
            document_id=ctx.document_id,
            source_pdf_sha256=sha256,
            page_count=page_count,
        )
        return manifest


def _run_image_set_ingest(ctx: StageContext, prepared: PreparedImageSet) -> SourceManifestV1:
    """Register raw image-set bytes and metadata artifacts."""
    pages: list[PageEntry] = []

    for prepared_image in prepared.images:
        entry = prepared_image.entry
        extension = ".jpg" if entry.media_type == "image/jpeg" else ".png"
        raw_path = ctx.artifact_store.put_bytes(
            document_id=ctx.document_id,
            schema_family="raw_image",
            scope="page",
            entity_id=entry.image_id,
            data=prepared_image.data,
            extension=extension,
        )
        raw_ref = raw_path.relative_to(ctx.artifact_store.root).as_posix()
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="raw_image_metadata.v1",
            scope="page",
            entity_id=entry.image_id,
            data={
                "schema_version": "raw_image_metadata.v1",
                "document_id": ctx.document_id,
                "image": entry.model_dump(mode="json"),
                "raw_image_ref": raw_ref,
            },
        )
        pages.append(
            PageEntry(
                page_id=entry.page_id,
                page_number=entry.page_number,
                source_image_id=entry.image_id,
                raw_image_ref=raw_ref,
            )
        )

    return SourceManifestV1(
        document_id=ctx.document_id,
        source_kind="image_set",
        source_pdf_sha256="",
        source_image_set_sha256=prepared.source_image_set_sha256,
        source_image_set_manifest_sha256=prepared.manifest_sha256,
        page_count=len(pages),
        pages=pages,
        image_set=prepared.manifest,
    )
