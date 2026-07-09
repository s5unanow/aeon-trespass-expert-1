"""Contract test — a UI-shaped `patch_set.v1` round-trips through the applicator.

The extraction-review reader route (S5U-1539) exports a `patch_set.v1` JSON that
the pipeline must be able to ingest. This test pins that contract: fixtures whose
shape is identical to the reader's export must

  1. parse as :class:`PatchSetV1` (schema validation),
  2. apply cleanly via :func:`apply_patches` to the committed render-page fixture, and
  3. leave a document that still validates as :class:`RenderPageV1`.

The render-page fixture mirrors
``apps/web/public/documents/review_sample/en/data/render_page.p0001.json`` so the
patch pointers correspond to a page the reader actually serves.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from atr_pipeline.stages.patch.applicator import apply_patches
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.render_page_v1 import RenderPageV1

FIXTURES = Path(__file__).parents[3] / "fixtures" / "review"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def render_page() -> dict[str, Any]:
    page = _load("render_page.p0001.json")
    # Sanity: the base fixture is itself a valid render page.
    RenderPageV1.model_validate(page)
    return page


def _text_corrected(result: dict[str, Any]) -> bool:
    return result["blocks"][1]["children"][0]["text"].endswith("ATTACK value.")


def _callout_suppressed(result: dict[str, Any]) -> bool:
    return len(result["blocks"]) == 3 and all(b["id"] != "p0001.b004" for b in result["blocks"])


def _reordered(result: dict[str, Any]) -> bool:
    return [b["id"] for b in result["blocks"][:2]] == ["p0001.b002", "p0001.b001"]


def _combined(result: dict[str, Any]) -> bool:
    return _text_corrected(result) and len(result["blocks"]) == 3


@pytest.mark.parametrize(
    ("fixture_name", "expected_scopes", "postcondition"),
    [
        ("patch_text.json", {"text"}, _text_corrected),
        ("patch_suppress.json", {"block_structure"}, _callout_suppressed),
        ("patch_reorder.json", {"reading_order"}, _reordered),
        ("patch_combined.json", {"text", "block_structure"}, _combined),
    ],
)
def test_ui_export_roundtrips_through_applicator(
    render_page: dict[str, Any],
    fixture_name: str,
    expected_scopes: set[str],
    postcondition: Callable[[dict[str, Any]], bool],
) -> None:
    raw = _load(fixture_name)

    # 1. Parses as PatchSetV1 (schema validation of the reader export shape).
    patch_set = PatchSetV1.model_validate(raw)
    assert patch_set.schema_version == "patch_set.v1"
    assert patch_set.target_kind is not None and patch_set.target_kind.value == "render_page"
    assert patch_set.provenance is not None
    assert patch_set.provenance.author != ""
    assert patch_set.reason != ""
    assert {op.scope.value for op in patch_set.operations if op.scope} == expected_scopes

    # 2. Applies cleanly to the committed render-page fixture.
    result = apply_patches(render_page, patch_set)

    # 3. The patched artifact still validates as RenderPageV1.
    RenderPageV1.model_validate(result)

    # 4. The intended correction actually took effect.
    assert postcondition(result)

    # The applicator must not mutate the original artifact (ADR-003 immutability).
    assert render_page != result


def test_text_pointer_targets_a_real_text_node(render_page: dict[str, Any]) -> None:
    """The `text`-scope pointer the reader emits resolves to a text inline."""
    patch_set = PatchSetV1.model_validate(_load("patch_text.json"))
    op = patch_set.operations[0]
    assert op.path == "/blocks/1/children/0/text"
    node = render_page["blocks"][1]["children"][0]
    assert node["kind"] == "text"
    assert isinstance(node["text"], str)
