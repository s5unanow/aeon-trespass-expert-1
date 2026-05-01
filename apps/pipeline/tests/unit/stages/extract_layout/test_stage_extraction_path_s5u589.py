"""S5U-589 — ExtractLayoutStage records extraction_path on every artifact.

These tests pin the contract LayoutPageV1.extraction_path establishes
between ExtractLayoutStage and StructureStage. The structure stage uses
the field to decide whether to populate FallbackProvenance on resolved
blocks; silent regressions on this attribution would re-introduce the
audit gap S5U-589 was filed to close (24 hard pages, 0 fallback-route
pages).

Three values are pinned: ``"primary"`` (clean Docling result kept;
includes the case where OCR was attempted but returned no usable zones,
because the persisted bytes are still primary), ``"ocr_fallback"`` (OCR
was selected because either the primary failed entirely or it flagged the
page as hard, and the OCR result has zones), and ``"extraction_failed"``
(both primary and OCR produced nothing; the stage synthesizes a
degenerate marker).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from atr_pipeline.stages.extract_layout.stage import ExtractLayoutStage
from atr_schemas.common import Rect as RectModel
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1, LayoutZone
from tests.unit.stages.extract_layout.test_stage import _make_ctx, _write_native_page


def _read_layout(tmp_path: Path, page_id: str) -> dict:
    layout_dir = tmp_path / "artifacts" / "test_doc" / "layout_page.v1" / "page" / page_id
    files = sorted(layout_dir.glob("*.json"))
    assert files, f"no layout artifact for {page_id}"
    return json.loads(files[-1].read_text())


def _primary_layout(*, hard: bool, route: str) -> LayoutPageV1:
    return LayoutPageV1(
        document_id="test_doc",
        page_id="p0001",
        zones=[
            LayoutZone(
                zone_id="z001",
                kind="body",
                bbox=RectModel(x0=50, y0=50, x1=560, y1=740),
                confidence=1.0,
            )
        ],
        difficulty=DifficultyScoreV1(
            page_id="p0001",
            native_text_coverage=0.6 if not hard else 0.05,
            hard_page=hard,
            recommended_route=route,
        ),
    )


def _ocr_layout(*, zones: int) -> LayoutPageV1:
    return LayoutPageV1(
        document_id="test_doc",
        page_id="p0001",
        zones=[
            LayoutZone(
                zone_id=f"ocr{i:03d}",
                kind="body",
                bbox=RectModel(x0=10, y0=10 + i * 30, x1=600, y1=30 + i * 30),
                confidence=0.85,
            )
            for i in range(zones)
        ],
        difficulty=DifficultyScoreV1(page_id="p0001"),
    )


def test_records_primary_extraction_path(tmp_path: Path) -> None:
    """Clean primary path stamps extraction_path='primary' on the artifact."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    with patch(
        "atr_pipeline.stages.extract_layout.stage.extract_layout_docling",
        return_value=_primary_layout(hard=False, route="R1"),
    ):
        ExtractLayoutStage().run(ctx, None)

    assert _read_layout(tmp_path, "p0001")["extraction_path"] == "primary"


def test_records_ocr_fallback_extraction_path(tmp_path: Path) -> None:
    """Hard primary + non-empty OCR -> extraction_path='ocr_fallback'."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    with (
        patch(
            "atr_pipeline.stages.extract_layout.stage.extract_layout_docling",
            return_value=_primary_layout(hard=True, route="R2"),
        ),
        patch(
            "atr_pipeline.stages.extract_layout.stage.extract_layout_ocr",
            return_value=_ocr_layout(zones=1),
        ),
    ):
        ExtractLayoutStage().run(ctx, None)

    assert _read_layout(tmp_path, "p0001")["extraction_path"] == "ocr_fallback"


def test_records_extraction_failed_path(tmp_path: Path) -> None:
    """Primary + OCR both fail -> extraction_path='extraction_failed'."""
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    with (
        patch(
            "atr_pipeline.stages.extract_layout.stage.extract_layout_docling",
            side_effect=RuntimeError("docling failed"),
        ),
        patch(
            "atr_pipeline.stages.extract_layout.stage.extract_layout_ocr",
            side_effect=RuntimeError("paddleocr failed"),
        ),
    ):
        ExtractLayoutStage().run(ctx, None)

    data = _read_layout(tmp_path, "p0001")
    assert data["extraction_path"] == "extraction_failed"
    # Cross-check: the synthesized marker still flags the page as hard so
    # it never silently masquerades as a clean R1 result.
    assert data["difficulty"]["hard_page"] is True


def test_keeps_primary_path_when_ocr_returns_empty(tmp_path: Path) -> None:
    """Hard primary + empty OCR -> primary kept, extraction_path stays 'primary'.

    OCR was attempted but produced no zones; the persisted bytes are from
    the primary extractor, so the path attribution is 'primary' even though
    the page is flagged hard. The audit count for fallback-route pages must
    not include this case.
    """
    ctx = _make_ctx(tmp_path)
    _write_native_page(ctx.artifact_store, "test_doc", "p0001")

    with (
        patch(
            "atr_pipeline.stages.extract_layout.stage.extract_layout_docling",
            return_value=_primary_layout(hard=True, route="R2"),
        ),
        patch(
            "atr_pipeline.stages.extract_layout.stage.extract_layout_ocr",
            return_value=_ocr_layout(zones=0),
        ),
    ):
        ExtractLayoutStage().run(ctx, None)

    data = _read_layout(tmp_path, "p0001")
    assert data["extraction_path"] == "primary"
    assert data["difficulty"]["hard_page"] is True
