"""Store render pages with immutable targets for reader-drafted patches."""

from __future__ import annotations

from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.render_page_v1 import RenderBuildMeta, RenderPageV1


def store_reviewable_render_page(
    store: ArtifactStore,
    document_id: str,
    render: RenderPageV1,
) -> str:
    """Store a canonical patch target, then a published wrapper referring to it.

    The wrapper's content hash cannot refer to itself without becoming
    self-referential, so patches intentionally target the immutable first write.
    """
    target_ref = store.put_json(
        document_id=document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=render.page.id,
        data=render,
    )
    render.build_meta = render.build_meta or RenderBuildMeta()
    render.build_meta.artifact_ref = target_ref.relative_path
    published_ref = store.put_json(
        document_id=document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=render.page.id,
        data=render,
    )
    return published_ref.relative_path
