"""Contract test for the extraction-review reader's exported patch shape."""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from atr_pipeline.cli.commands.patch import _parse_ref
from atr_pipeline.stages.patch.applicator import apply_patches
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.render_page_v1 import RenderPageV1


def test_review_export_applies_and_revalidates_render_page(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    render_path = (
        repo_root / "apps/web/public/documents/extraction_review/en/data/render_page.p0001.json"
    )
    patch_path = repo_root / "apps/pipeline/tests/contract/fixtures/review_patch_set_v1.json"

    render_page = TypeAdapter(RenderPageV1).validate_json(render_path.read_text(encoding="utf-8"))
    patch_set = TypeAdapter(PatchSetV1).validate_json(patch_path.read_text(encoding="utf-8"))
    target_ref = _parse_ref(patch_set.target_artifact_ref)
    assert target_ref.document_id == "extraction_review"
    assert target_ref.schema_family == "render_page.v1"
    assert target_ref.scope == "page"
    assert target_ref.entity_id == "p0001"
    target_render = render_page.model_copy(update={"build_meta": None})
    stored_ref = ArtifactStore(tmp_path).put_json(
        document_id="extraction_review",
        schema_family="render_page.v1",
        scope="page",
        entity_id="p0001",
        data=target_render,
    )
    assert stored_ref == target_ref
    ingestible_render = ArtifactStore(tmp_path).get_json(stored_ref)

    patched = apply_patches(ingestible_render, patch_set)
    TypeAdapter(RenderPageV1).validate_python(patched)

    assert patched["blocks"][1]["children"][0]["text"] == "Move up to two spaces."
