"""S5U-576: Integration test for S5U-429 negative y-gap bbox fix.

Verifies that the negative y-gap fix in real_block_builder produces
correct annotation positions in the facsimile render. This test exercises
the full path: native_page → build_page_ir_real → build_facsimile_annotations.

Synthetic data mimics the p0007 pattern: caption spans emitted in
non-monotonic y-order that would incorrectly merge into a single block
with a coarse bbox if not properly split.
"""

from __future__ import annotations

import pytest

from atr_pipeline.stages.render.annotation_builder import (
    AnnotationQualityConfig,
    build_facsimile_annotations,
)
from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence


def _make_native_page(
    *,
    page_id: str = "p0007",
    page_number: int = 7,
    spans: list[SpanEvidence],
) -> NativePageV1:
    """Create a synthetic native page with given spans."""
    return NativePageV1(
        document_id="ato_core_v1_1",
        page_id=page_id,
        page_number=page_number,
        dimensions_pt=PageDimensions(width=595.28, height=841.89),
        words=[],
        spans=spans,
        image_blocks=[],
    )


class TestNegativeYGapAnnotationPositions:
    """Verify that spans with negative y-gaps produce tight annotation bboxes.

    This is the end-to-end verification for S5U-429.
    """

    @pytest.fixture
    def negative_ygap_spans(self) -> list[SpanEvidence]:
        """Spans mimicking p0007 caption pattern with negative y-gap.

        Two caption spans at y=452 and y=298 — the second span jumps
        backwards vertically by -154pt, which is well beyond any
        normal line spacing. Without the fix, these would merge into
        one block with a bbox spanning from y0=298 to y1=462 (164pt tall).
        With the fix, each caption gets its own tight bbox (~10pt tall).
        """
        return [
            SpanEvidence(
                span_id="s001",
                text="199 BP Cards",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=245.0, y0=452.0, x1=360.0, y1=462.0),
            ),
            SpanEvidence(
                span_id="s002",
                text="10 Trait Cards",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=245.0, y0=298.0, x1=380.0, y1=308.0),
            ),
        ]

    @pytest.fixture
    def normal_spans(self) -> list[SpanEvidence]:
        """Normal spans with monotonic y-order (control group).

        These should merge into a single paragraph as expected.
        """
        return [
            SpanEvidence(
                span_id="s001",
                text="Welcome to the game. ",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=50.0, y0=100.0, x1=200.0, y1=110.0),
            ),
            SpanEvidence(
                span_id="s002",
                text="This is the second line.",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=50.0, y0=112.0, x1=220.0, y1=122.0),
            ),
        ]

    def test_negative_ygap_produces_separate_tight_blocks(
        self, negative_ygap_spans: list[SpanEvidence]
    ) -> None:
        """Negative y-gap spans must split into separate blocks with tight bboxes."""
        native = _make_native_page(spans=negative_ygap_spans)
        ir = build_page_ir_real(native)

        # Must produce 2 separate blocks, not 1 merged block
        assert len(ir.blocks) == 2, f"Expected 2 blocks, got {len(ir.blocks)}"

        for block in ir.blocks:
            assert block.bbox is not None, f"Block {block.block_id} has no bbox"
            bbox_height = block.bbox.y1 - block.bbox.y0
            assert bbox_height < 20.0, (
                f"Block {block.block_id} bbox height {bbox_height:.1f}pt is too tall "
                f"for a single caption line — blocks may have incorrectly merged"
            )

    def test_negative_ygap_annotations_positioned_correctly(
        self, negative_ygap_spans: list[SpanEvidence]
    ) -> None:
        """Annotations from negative y-gap blocks must have tight normalized positions."""
        native = _make_native_page(spans=negative_ygap_spans)
        ir = build_page_ir_real(native)

        # Use permissive quality config to ensure annotations aren't filtered
        quality = AnnotationQualityConfig(
            max_bbox_area=0.5,
            max_total_area=1.0,
            max_annotation_count=100,
            min_letter_ratio=0.0,
            max_drop_ratio=1.0,
        )
        annotations = build_facsimile_annotations(ir, None, quality=quality)

        assert len(annotations) == 2, f"Expected 2 annotations, got {len(annotations)}"

        page_height = native.dimensions_pt.height
        for ann in annotations:
            # NormRect y values are normalized to 0-1 range
            ann_height_norm = ann.bbox.y1 - ann.bbox.y0
            ann_height_pt = ann_height_norm * page_height
            assert ann_height_pt < 25.0, (
                f"Annotation '{ann.text[:20]}...' has height {ann_height_pt:.1f}pt "
                f"in page coordinates — too tall for a single caption"
            )

    def test_normal_spans_merge_correctly(self, normal_spans: list[SpanEvidence]) -> None:
        """Normal monotonic spans should merge into a single paragraph.

        This is the regression guard — we don't want the fix to over-split.
        """
        native = _make_native_page(page_id="p0001", page_number=1, spans=normal_spans)
        ir = build_page_ir_real(native)

        # Should produce 1 merged paragraph, not 2 separate blocks
        assert len(ir.blocks) == 1, (
            f"Expected 1 merged paragraph, got {len(ir.blocks)} — "
            f"the negative y-gap fix may be over-splitting normal text"
        )

        block = ir.blocks[0]
        assert block.type == "paragraph"
        assert block.bbox is not None
        # Merged bbox should span both lines (~22pt)
        bbox_height = block.bbox.y1 - block.bbox.y0
        assert 15.0 < bbox_height < 30.0, (
            f"Merged paragraph bbox height {bbox_height:.1f}pt unexpected"
        )

    def test_mixed_page_handles_both_patterns(self) -> None:
        """Page with both normal and negative y-gap regions.

        Verifies the fix is selective — only splits at true discontinuities.
        """
        spans = [
            # Normal paragraph region (should merge)
            SpanEvidence(
                span_id="s001",
                text="Introduction text. ",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=50.0, y0=100.0, x1=200.0, y1=110.0),
            ),
            SpanEvidence(
                span_id="s002",
                text="Continues here.",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=50.0, y0=112.0, x1=180.0, y1=122.0),
            ),
            # Negative y-gap caption region (should split)
            SpanEvidence(
                span_id="s003",
                text="Caption A at bottom",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=300.0, y0=700.0, x1=450.0, y1=710.0),
            ),
            SpanEvidence(
                span_id="s004",
                text="Caption B above A",
                font_name="Adonis-Regular",
                font_size=9.0,
                bbox=Rect(x0=300.0, y0=500.0, x1=450.0, y1=510.0),
            ),
        ]

        native = _make_native_page(spans=spans)
        ir = build_page_ir_real(native)

        # Should produce 3 blocks: 1 merged paragraph + 2 separate captions
        assert len(ir.blocks) == 3, (
            f"Expected 3 blocks (1 paragraph + 2 captions), got {len(ir.blocks)}"
        )

        # Verify the paragraph is merged (spans y=100-122)
        para_blocks = [b for b in ir.blocks if b.bbox and b.bbox.y0 < 200]
        assert len(para_blocks) == 1, "Introduction spans should merge"

        # Verify captions are separate
        caption_blocks = [b for b in ir.blocks if b.bbox and b.bbox.y0 > 400]
        assert len(caption_blocks) == 2, "Caption spans with negative gap should split"
