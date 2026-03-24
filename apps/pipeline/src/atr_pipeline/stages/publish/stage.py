"""Publish stage — build a release bundle from pipeline artifacts."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.registry.runs import get_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.publish.bundle_builder import BundleRefs, build_release_bundle
from atr_schemas.enums import StageScope


class PublishResult(BaseModel):
    """Summary of the publish stage output."""

    document_id: str
    build_id: str = ""
    files_published: int = Field(default=0, ge=0)
    output_dir: str = ""


class PublishStage:
    """Build a release bundle from the current run's artifacts.

    Uses explicit artifact refs from the run's stage events — no
    directory enumeration.
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
        render_data = _load_render_result_from_registry(ctx)
        page_refs = render_data.get("page_refs", {})
        if not isinstance(page_refs, dict) or not page_refs:
            msg = "No render page refs found. Run the render stage first."
            raise RuntimeError(msg)

        companion_refs = {
            k: str(render_data[k])
            for k in ("glossary_ref", "search_docs_ref", "nav_ref")
            if render_data.get(k)
        }

        raw_image_refs = render_data.get("image_refs", {})
        image_refs = (
            {str(k): str(v) for k, v in raw_image_refs.items()}
            if isinstance(raw_image_refs, dict)
            else {}
        )

        raw_raster_refs = render_data.get("raster_refs", {})
        flat_rasters: dict[str, str] = {}
        if isinstance(raw_raster_refs, dict):
            for pid, dpi_map in raw_raster_refs.items():
                if isinstance(dpi_map, dict):
                    for dpi_str, path in dpi_map.items():
                        flat_rasters[f"{pid}__{dpi_str}dpi"] = str(path)

        output_dir = ctx.artifact_store.root / ctx.document_id / "release"

        run_row = get_run(ctx.registry_conn, ctx.run_id)
        source_sha = run_row["source_pdf_sha256"] if run_row else ""

        manifest = build_release_bundle(
            document_id=ctx.document_id,
            artifact_root=ctx.artifact_store.root,
            output_dir=output_dir,
            pipeline_version=ctx.config.pipeline.version,
            refs=BundleRefs(
                render_pages={str(k): str(v) for k, v in page_refs.items()},
                companions=companion_refs,
                images=image_refs,
                rasters=flat_rasters,
                run_id=ctx.run_id,
                source_pdf_sha256=source_sha or "",
                edition="en" if ctx.edition == "en" else "ru",
            ),
        )

        ctx.logger.info("Published %d files to %s", len(manifest.files), output_dir)

        return PublishResult(
            document_id=ctx.document_id,
            build_id=manifest.build_id,
            files_published=len(manifest.files),
            output_dir=str(output_dir),
        )


def _load_render_result_from_registry(ctx: StageContext) -> dict[str, object]:
    """Load the render stage artifact using the current run's stage events."""
    events = list_stage_events(ctx.registry_conn, run_id=ctx.run_id)
    render_event = next(
        (
            ev
            for ev in events
            if ev["stage_name"] == "render" and ev["status"] in ("completed", "cached")
        ),
        None,
    )
    if render_event is None or not render_event["artifact_ref"]:
        msg = "No render result found. Run the render stage first."
        raise RuntimeError(msg)

    artifact_path = ctx.artifact_store.root / render_event["artifact_ref"]
    return json.loads(artifact_path.read_text())  # type: ignore[no-any-return]
