"""Contract test for extraction-review UI patch exports."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.stages.patch.applicator import apply_patches
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.render_page_v1 import RenderPageV1

ROOT = Path(__file__).resolve().parents[6]
FIXTURE_DIR = ROOT / "packages" / "fixtures" / "sample_documents" / "review_fixture"


def test_review_route_patch_export_applies_to_render_page_fixture() -> None:
    render_page_path = FIXTURE_DIR / "expected" / "render_page.p0001.json"
    patch_path = FIXTURE_DIR / "patches" / "render" / "patch-review-fixture.json"

    render_page = json.loads(render_page_path.read_text(encoding="utf-8"))
    patch_set = PatchSetV1.model_validate_json(patch_path.read_text(encoding="utf-8"))

    patched = apply_patches(render_page, patch_set)
    validated = RenderPageV1.model_validate(patched)

    assert patch_set.target_kind == "render_page"
    assert patch_set.operations[0].scope == "text"
    assert validated.blocks[1].children[0].text == "Corrected body text."
