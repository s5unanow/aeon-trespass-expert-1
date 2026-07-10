"""Image-set cache identity and immutable raw-image registration."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.image_set_preflight import (
    ImageSetIngestPlan,
    preflight_image_set,
)
from atr_pipeline.stages.ingest.path_safety import resolve_allowed_path
from atr_pipeline.utils.hashing import sha256_bytes, sha256_str
from atr_schemas.image_set_manifest_v1 import ImageSetManifestV1
from atr_schemas.source_manifest_v1 import (
    PageEntry,
    SourceImageEntryV1,
    SourceManifestV1,
)


def ingest_image_set(ctx: StageContext) -> SourceManifestV1:
    """Preflight every input, then register all raw bytes immutably."""
    source = ctx.config.document.source
    if source.source_kind != "image_set":
        msg = "ingest_image_set requires an image_set source"
        raise ValueError(msg)
    plan = preflight_image_set(
        source.manifest_path,
        base_dir=ctx.config.repo_root,
        allowed_roots=_allowed_roots(ctx),
    )
    return _register_plan(ctx, plan)


def image_set_cache_inputs(ctx: StageContext) -> list[str]:
    """Hash manifest and ordered image bytes before executor cache lookup."""
    source = ctx.config.document.source
    if source.source_kind != "image_set":
        msg = "image_set_cache_inputs requires an image_set source"
        raise ValueError(msg)
    roots = _allowed_roots(ctx)
    try:
        manifest_path = resolve_allowed_path(
            source.manifest_path,
            base_dir=ctx.config.repo_root,
            allowed_roots=roots,
            label="image-set manifest",
        )
    except (FileNotFoundError, ValueError) as exc:
        return [f"image_set_manifest:invalid:{sha256_str(str(exc))}"]

    manifest_bytes = manifest_path.read_bytes()
    inputs = [f"image_set_manifest_sha256:{sha256_bytes(manifest_bytes)}"]
    try:
        manifest = ImageSetManifestV1.model_validate_json(manifest_bytes)
    except ValidationError:
        return inputs

    for entry in manifest.images:
        try:
            image_path = resolve_allowed_path(
                entry.path,
                base_dir=manifest_path.parent,
                allowed_roots=roots,
                label="image-set image",
            )
        except (FileNotFoundError, ValueError) as exc:
            inputs.append(f"image:{entry.image_id}:invalid:{sha256_str(str(exc))}")
            continue
        inputs.append(f"image:{entry.image_id}:sha256:{sha256_bytes(image_path.read_bytes())}")
    return inputs


def image_set_raw_artifacts_present(ctx: StageContext, manifest: SourceManifestV1) -> bool:
    """Return whether every raw ref in a cached image-set manifest exists safely."""
    root = ctx.artifact_store.root
    for image in manifest.source_images:
        relative = Path(image.raw_artifact_ref)
        if relative.is_absolute() or ".." in relative.parts:
            return False
        resolved = (root / relative).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            return False
    return True


def _register_plan(ctx: StageContext, plan: ImageSetIngestPlan) -> SourceManifestV1:
    source_images: list[SourceImageEntryV1] = []
    pages: list[PageEntry] = []
    for image in plan.images:
        artifact_path = ctx.artifact_store.put_bytes(
            document_id=ctx.document_id,
            schema_family="raw_image",
            scope="page",
            entity_id=image.raw_image_id,
            data=image.data,
            extension=image.extension,
        )
        source_images.append(
            SourceImageEntryV1(
                image_id=image.entry.image_id,
                page_id=image.entry.page_id,
                page_number=image.entry.page_number,
                media_type=image.media_type,
                sha256=image.entry.sha256,
                raw_artifact_ref=artifact_path.relative_to(ctx.artifact_store.root).as_posix(),
                capture=image.capture,
            )
        )
        pages.append(
            PageEntry(
                page_id=image.entry.page_id,
                page_number=image.entry.page_number,
                raster_ref=artifact_path.relative_to(ctx.artifact_store.root).as_posix(),
            )
        )

    return SourceManifestV1(
        document_id=ctx.document_id,
        source_kind="image_set",
        source_pdf_sha256="",
        source_manifest_sha256=plan.manifest_sha256,
        source_image_set_sha256=plan.image_set_sha256,
        page_count=len(pages),
        pages=pages,
        source_images=source_images,
    )


def _allowed_roots(ctx: StageContext) -> tuple[Path, ...]:
    repo_root = ctx.config.repo_root.resolve(strict=True)
    materials_root = repo_root / "materials"
    if materials_root.is_dir():
        return (repo_root, materials_root.resolve(strict=True))
    return (repo_root,)
