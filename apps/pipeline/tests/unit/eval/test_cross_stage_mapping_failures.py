"""Negative fixtures for cross-boundary mapping failures.

Each test constructs artifacts that are individually valid on both sides
of a stage boundary, but where the *mapping* between them is wrong.
These are not schema-validation failures — both sides pass validation
independently. The failure is that they disagree on identity.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.eval.cross_stage_refs import (
    XREF_EVIDENCE_TO_IR,
    XREF_IR_FIGURE_REMAP,
    XREF_IR_TO_RENDER,
    XREF_NATIVE_WORD,
    XREF_RENDER_ASSET,
    XREF_RENDER_TO_PUBLISH,
    PageArtifacts,
    run_cross_stage_checks,
)
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import LanguageCode, Severity
from atr_schemas.evidence_primitives_v1 import EvidenceChar
from atr_schemas.native_page_v1 import NativePageV1, WordEvidence
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
from atr_schemas.page_ir_v1 import (
    FigureBlock,
    PageIRV1,
    ParagraphBlock,
    SourceRef,
    TextInline,
)
from atr_schemas.render_page_v1 import (
    RenderFigure,
    RenderFigureBlock,
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderTextInline,
)

_DIMS = PageDimensions(width=612.0, height=792.0)
_BBOX = Rect(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
_NORM = NormRect(x0=0.0, y0=0.0, x1=0.5, y1=0.5)


# === Mapping failure: IR figure asset_id silently remapped in render ===


class TestFigureAssetRemapMapping:
    """Both IR and render are internally valid, but figure asset_ids disagree."""

    def test_silent_remap_detected_via_orchestrator(self) -> None:
        """run_cross_stage_checks catches figure remap across IR→render."""
        ir = PageIRV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[FigureBlock(block_id="p0001.b001", asset_id="original_img")],
        )
        render = RenderPageV1(
            page=RenderPageMeta(id="p0001", source_page_number=1),
            blocks=[RenderFigureBlock(id="p0001.b001", asset_id="wrong_img")],
            figures={"wrong_img": RenderFigure(src="images/wrong_img.png")},
        )
        records = run_cross_stage_checks(
            PageArtifacts(page_id="p0001", document_id="doc1", ir=ir, render=render)
        )
        remap = [r for r in records if r.code == XREF_IR_FIGURE_REMAP]
        assert len(remap) == 1
        assert remap[0].severity == Severity.ERROR
        assert "original_img" in remap[0].message
        assert "wrong_img" in remap[0].message


# === Mapping failure: native word_ids silently remapped in IR ===


class TestNativeWordRemapMapping:
    """IR references word_ids that exist in native but are the WRONG ones.

    The subtle case: IR uses a valid word_id from the same page, but the
    block maps to a different word than intended. The verifier can only
    detect the case where the word_id is completely absent.
    """

    def test_ir_references_absent_word(self) -> None:
        """IR word_id 'w_typo' doesn't exist in native — detected."""
        native = NativePageV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            dimensions_pt=_DIMS,
            words=[
                WordEvidence(word_id="w001", text="hello", bbox=_BBOX),
                WordEvidence(word_id="w002", text="world", bbox=_BBOX),
            ],
        )
        ir = PageIRV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    children=[TextInline(text="hello", source_word_ids=["w001", "w_typo"])],
                )
            ],
        )
        records = run_cross_stage_checks(
            PageArtifacts(page_id="p0001", document_id="doc1", native=native, ir=ir)
        )
        errors = [r for r in records if r.code == XREF_NATIVE_WORD]
        assert len(errors) == 1
        assert "w_typo" in errors[0].entity_ref


# === Mapping failure: evidence_refs silently remapped in IR ===


class TestEvidenceRefRemapMapping:
    """IR references evidence IDs that don't exist in evidence layer."""

    def test_ir_references_absent_evidence(self) -> None:
        """Both sides are valid, but IR points to non-existent evidence."""
        evidence = PageEvidenceV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
            entities=[
                EvidenceChar(evidence_id="e.char.001", text="x", bbox=_BBOX, norm_bbox=_NORM),
            ],
        )
        ir = PageIRV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    source_ref=SourceRef(evidence_refs=["e.char.001", "e.char.phantom"]),
                )
            ],
        )
        records = run_cross_stage_checks(
            PageArtifacts(page_id="p0001", document_id="doc1", evidence=evidence, ir=ir)
        )
        errors = [r for r in records if r.code == XREF_EVIDENCE_TO_IR]
        assert len(errors) == 1
        assert "e.char.phantom" in errors[0].entity_ref


# === Mapping failure: render block_ids silently remapped from IR ===


class TestBlockIdRemapMapping:
    """IR and render both valid, but translatable block_ids diverge."""

    def test_translatable_block_absent_in_render(self) -> None:
        """IR has translatable block 'p0001.b001'; render has 'p0001.b099'."""
        ir = PageIRV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    children=[TextInline(text="hello")],
                )
            ],
        )
        render = RenderPageV1(
            page=RenderPageMeta(id="p0001", source_page_number=1),
            blocks=[
                RenderParagraphBlock(
                    id="p0001.b099",
                    children=[RenderTextInline(text="hello")],
                )
            ],
        )
        records = run_cross_stage_checks(
            PageArtifacts(page_id="p0001", document_id="doc1", ir=ir, render=render)
        )
        warnings = [r for r in records if r.code == XREF_IR_TO_RENDER]
        assert len(warnings) == 1
        assert warnings[0].entity_ref == "p0001.b001"


# === Mapping failure: publish points to wrong but existing artifact ===


class TestPublishWrongArtifactMapping:
    """Published bundle has files, but render.figures.src points to wrong one."""

    def test_figure_src_points_to_wrong_file(self, tmp_path: Path) -> None:
        """Render says 'images/fig_a.png' but only 'images/fig_b.png' exists."""
        release_dir = tmp_path / "release"
        (release_dir / "pages").mkdir(parents=True)
        (release_dir / "pages" / "p0001.json").write_text("{}")
        (release_dir / "images").mkdir()
        (release_dir / "images" / "fig_b.png").write_text("")  # exists but wrong

        render = RenderPageV1(
            page=RenderPageMeta(id="p0001", source_page_number=1),
            blocks=[],
            figures={"fig_a": RenderFigure(src="images/fig_a.png")},  # points to missing
        )
        records = run_cross_stage_checks(
            PageArtifacts(
                page_id="p0001",
                document_id="doc1",
                render=render,
                release_dir=release_dir,
            )
        )
        errors = [r for r in records if r.code == XREF_RENDER_TO_PUBLISH]
        assert len(errors) == 1
        assert errors[0].entity_ref == "fig_a"

    def test_render_internal_asset_dangling(self, tmp_path: Path) -> None:
        """Render block references asset_id not in figures dict (valid-looking block)."""
        release_dir = tmp_path / "release"
        (release_dir / "pages").mkdir(parents=True)
        (release_dir / "pages" / "p0001.json").write_text("{}")

        render = RenderPageV1(
            page=RenderPageMeta(id="p0001", source_page_number=1),
            blocks=[RenderFigureBlock(id="p0001.b001", asset_id="orphan_asset")],
            figures={"other_asset": RenderFigure(src="images/other.png")},
        )
        ir = PageIRV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[FigureBlock(block_id="p0001.b001", asset_id="orphan_asset")],
        )
        records = run_cross_stage_checks(
            PageArtifacts(
                page_id="p0001",
                document_id="doc1",
                ir=ir,
                render=render,
                release_dir=release_dir,
            )
        )
        asset_errors = [r for r in records if r.code == XREF_RENDER_ASSET]
        assert len(asset_errors) == 1
        assert asset_errors[0].entity_ref == "orphan_asset"


# === Multi-boundary: combined mapping failures across stages ===


class TestMultiBoundaryMappingFailure:
    """Artifacts valid at each stage, but mapping chain breaks across multiple."""

    def test_all_boundaries_checked(self) -> None:
        """run_cross_stage_checks runs all applicable checks in one pass."""
        native = NativePageV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            dimensions_pt=_DIMS,
            words=[WordEvidence(word_id="w001", text="hello", bbox=_BBOX)],
        )
        ir = PageIRV1(
            document_id="doc1",
            page_id="p0001",
            page_number=1,
            language=LanguageCode.EN,
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    children=[TextInline(text="hello", source_word_ids=["w001", "w_bad"])],
                ),
                FigureBlock(block_id="p0001.b002", asset_id="img_ir"),
            ],
        )
        render = RenderPageV1(
            page=RenderPageMeta(id="p0001", source_page_number=1),
            blocks=[
                RenderParagraphBlock(id="p0001.b001", children=[RenderTextInline(text="hello")]),
                RenderFigureBlock(id="p0001.b002", asset_id="img_render"),
            ],
            figures={"img_render": RenderFigure(src="images/img_render.png")},
        )
        records = run_cross_stage_checks(
            PageArtifacts(
                page_id="p0001",
                document_id="doc1",
                native=native,
                ir=ir,
                render=render,
            )
        )
        codes = {r.code for r in records}
        assert XREF_NATIVE_WORD in codes  # w_bad missing
        assert XREF_IR_FIGURE_REMAP in codes  # img_ir != img_render
