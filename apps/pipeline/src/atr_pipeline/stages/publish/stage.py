"""Publish stage — build a release bundle from pipeline artifacts."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.publish.bundle_builder import build_release_bundle
from atr_schemas.enums import StageScope


class PublishResult(BaseModel):
    """Summary of the publish stage output."""

    document_id: str
    build_id: str = ""
    files_published: int = Field(default=0, ge=0)
    output_dir: str = ""


class PublishStage:
    """Build a release bundle from the current run's artifacts.

    Reads render page refs and companion artifact refs from the
    render stage output, builds a self-contained release directory
    with a manifest.
    """

    @property
    def name(self) -> str:
        return "publish"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> PublishResult:
        render_refs = self._load_render_refs(ctx)
        output_dir = ctx.artifact_store.root / ctx.document_id / "release"

        manifest = build_release_bundle(
            document_id=ctx.document_id,
            artifact_root=ctx.artifact_store.root,
            output_dir=output_dir,
            pipeline_version=ctx.config.pipeline.version,
            render_page_refs=render_refs,
        )

        ctx.logger.info("Published %d files to %s", len(manifest.files), output_dir)

        return PublishResult(
            document_id=ctx.document_id,
            build_id=manifest.build_id,
            files_published=len(manifest.files),
            output_dir=str(output_dir),
        )

    @staticmethod
    def _load_render_refs(ctx: StageContext) -> dict[str, str] | None:
        """Extract render page refs from the render stage's artifact."""
        render_dir = (
            ctx.artifact_store.root / ctx.document_id / "render" / "document" / ctx.document_id
        )
        if not render_dir.exists():
            ctx.logger.warning("No render result found, using filesystem fallback")
            return None

        jsons = sorted(render_dir.glob("*.json"))
        if not jsons:
            return None

        data = json.loads(jsons[-1].read_text())
        page_refs = data.get("page_refs")
        if isinstance(page_refs, dict) and page_refs:
            return {str(k): str(v) for k, v in page_refs.items()}

        return None
