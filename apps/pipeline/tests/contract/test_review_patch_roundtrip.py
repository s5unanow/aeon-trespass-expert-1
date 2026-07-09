"""Contract test for the extraction-review reader's exported patch shape."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.stages.patch.applicator import apply_patches
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.render_page_v1 import RenderPageV1


def test_review_export_applies_and_revalidates_render_page() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    render_path = (
        repo_root / "apps/web/public/documents/extraction_review/en/data/render_page.p0001.json"
    )
    patch_path = repo_root / "apps/pipeline/tests/contract/fixtures/review_patch_set_v1.json"

    render_data = json.loads(render_path.read_text(encoding="utf-8"))
    patch_data = json.loads(patch_path.read_text(encoding="utf-8"))

    RenderPageV1.model_validate(render_data)
    patch_set = PatchSetV1.model_validate(patch_data)
    patched = apply_patches(render_data, patch_set)
    validated = RenderPageV1.model_validate(patched)

    assert validated.blocks[1].children[0].text == "Move up to two spaces."
