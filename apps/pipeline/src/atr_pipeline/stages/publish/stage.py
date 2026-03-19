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
        render_data = self._load_render_result(ctx)
        page_refs = render_data.get("page_refs", {})
        if not isinstance(page_refs, dict) or not page_refs:
            msg = "No render page refs found. Run the render stage first."
            raise RuntimeError(msg)

        companion_refs = {
            k: str(render_data[k])
            for k in ("glossary_ref", "search_docs_ref", "nav_ref")
            if render_data.get(k)
        }

        output_dir = ctx.artifact_store.root / ctx.document_id / "release"

        manifest = build_release_bundle(
            document_id=ctx.document_id,
            artifact_root=ctx.artifact_store.root,
            output_dir=output_dir,
            pipeline_version=ctx.config.pipeline.version,
            render_page_refs={str(k): str(v) for k, v in page_refs.items()},
            companion_refs=companion_refs,
        )

        ctx.logger.info("Published %d files to %s", len(manifest.files), output_dir)

        return PublishResult(
            document_id=ctx.document_id,
            build_id=manifest.build_id,
            files_published=len(manifest.files),
            output_dir=str(output_dir),
        )

    @staticmethod
    def _load_render_result(ctx: StageContext) -> dict[str, object]:
        """Load the render stage result artifact."""
        render_dir = (
            ctx.artifact_store.root / ctx.document_id / "render" / "document" / ctx.document_id
        )
        if not render_dir.exists():
            msg = "No render result found. Run the render stage first."
            raise RuntimeError(msg)

        jsons = sorted(render_dir.glob("*.json"))
        if not jsons:
            msg = "No render result found. Run the render stage first."
            raise RuntimeError(msg)

        return json.loads(jsons[-1].read_text())  # type: ignore[no-any-return]
