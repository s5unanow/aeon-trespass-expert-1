"""Tests for cross-stage reference-integrity checks."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.eval.cross_stage_refs import (
    XREF_EVIDENCE_TO_IR,
    XREF_IR_TO_RENDER,
    XREF_NATIVE_WORD,
    XREF_RENDER_ASSET,
    XREF_RENDER_TO_PUBLISH,
    XREF_SYMBOL_DROPPED,
    XREF_SYMBOL_TO_IR,
    PageArtifacts,
    check_evidence_to_ir,
    check_ir_to_render,
    check_native_to_ir,
    check_render_to_publish,
    check_symbols_to_ir,
    run_cross_stage_checks,
)
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import NativePageV1, WordEvidence
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
from atr_schemas.page_ir_v1 import (
    FigureBlock,
    IconInline,
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
from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1

_DIMS = PageDimensions(width=612.0, height=792.0)
_BBOX = Rect(x0=0.0, y0=0.0, x1=100.0, y1=100.0)


def _make_native(
    words: list[WordEvidence] | None = None,
) -> NativePageV1:
    return NativePageV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        dimensions_pt=_DIMS,
        words=words or [],
    )


def _make_ir(
    blocks: list[ParagraphBlock | FigureBlock] | None = None,
) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=blocks or [],
    )


def _make_evidence(
    entity_ids: list[str] | None = None,
) -> PageEvidenceV1:
    from atr_schemas.common import NormRect
    from atr_schemas.evidence_primitives_v1 import EvidenceChar

    entities = [
        EvidenceChar(
            evidence_id=eid,
            text="x",
            bbox=_BBOX,
            norm_bbox=NormRect(x0=0.0, y0=0.0, x1=0.5, y1=0.5),
        )
        for eid in (entity_ids or [])
    ]
    return PageEvidenceV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
        entities=entities,
    )


def _make_symbols(
    symbol_ids: list[str] | None = None,
) -> SymbolMatchSetV1:
    matches = [SymbolMatch(symbol_id=sid, bbox=_BBOX, score=0.9) for sid in (symbol_ids or [])]
    return SymbolMatchSetV1(
        document_id="test_doc",
        page_id="p0001",
        matches=matches,
    )


def _make_render(
    block_ids: list[str] | None = None,
    figures: dict[str, RenderFigure] | None = None,
    figure_blocks: list[RenderFigureBlock] | None = None,
) -> RenderPageV1:
    blocks: list[RenderParagraphBlock | RenderFigureBlock] = []
    for bid in block_ids or []:
        blocks.append(
            RenderParagraphBlock(
                id=bid,
                children=[RenderTextInline(text="hello")],
            )
        )
    if figure_blocks:
        blocks.extend(figure_blocks)
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", source_page_number=1),
        blocks=blocks,
        figures=figures or {},
    )


def _word(wid: str) -> WordEvidence:
    return WordEvidence(word_id=wid, text="test", bbox=_BBOX)


# --- Boundary 1: NativePageV1 → PageIRV1 ---


def test_native_to_ir_valid() -> None:
    native = _make_native(words=[_word("w001"), _word("w002")])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="hello", source_word_ids=["w001", "w002"])],
            )
        ]
    )
    assert check_native_to_ir(native, ir) == []


def test_native_to_ir_dangling_word() -> None:
    native = _make_native(words=[_word("w001")])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="hello", source_word_ids=["w001", "w999"])],
            )
        ]
    )
    records = check_native_to_ir(native, ir)
    assert len(records) == 1
    assert records[0].code == XREF_NATIVE_WORD
    assert "w999" in records[0].entity_ref


def test_native_to_ir_source_ref_word_ids() -> None:
    native = _make_native(words=[_word("w001")])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                source_ref=SourceRef(page_id="p0001", word_ids=["w001", "w888"]),
            )
        ]
    )
    records = check_native_to_ir(native, ir)
    assert len(records) == 1
    assert records[0].code == XREF_NATIVE_WORD
    assert "w888" in records[0].entity_ref


def test_native_to_ir_empty_word_ids_ok() -> None:
    native = _make_native(words=[_word("w001")])
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001", children=[TextInline(text="hi")])])
    assert check_native_to_ir(native, ir) == []


# --- Boundary 2: PageEvidenceV1 → PageIRV1 ---


def test_evidence_to_ir_valid() -> None:
    evidence = _make_evidence(entity_ids=["e.char.001", "e.char.002"])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                source_ref=SourceRef(evidence_refs=["e.char.001", "e.char.002"]),
            )
        ]
    )
    assert check_evidence_to_ir(evidence, ir) == []


def test_evidence_to_ir_dangling_ref() -> None:
    evidence = _make_evidence(entity_ids=["e.char.001"])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                source_ref=SourceRef(evidence_refs=["e.char.001", "e.char.999"]),
            )
        ]
    )
    records = check_evidence_to_ir(evidence, ir)
    assert len(records) == 1
    assert records[0].code == XREF_EVIDENCE_TO_IR
    assert "e.char.999" in records[0].entity_ref


def test_evidence_to_ir_no_source_ref_ok() -> None:
    evidence = _make_evidence(entity_ids=["e.char.001"])
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001")])
    assert check_evidence_to_ir(evidence, ir) == []


# --- Boundary 3: SymbolMatchSetV1 → PageIRV1 ---


def test_symbols_to_ir_valid() -> None:
    symbols = _make_symbols(symbol_ids=["icon_a", "icon_b"])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    IconInline(symbol_id="icon_a"),
                    IconInline(symbol_id="icon_b"),
                ],
            )
        ]
    )
    assert check_symbols_to_ir(symbols, ir) == []


def test_symbols_to_ir_phantom() -> None:
    symbols = _make_symbols(symbol_ids=["icon_a"])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[IconInline(symbol_id="icon_phantom")],
            )
        ]
    )
    records = check_symbols_to_ir(symbols, ir)
    errors = [r for r in records if r.code == XREF_SYMBOL_TO_IR]
    assert len(errors) == 1
    assert errors[0].entity_ref == "icon_phantom"


def test_symbols_to_ir_dropped_warning() -> None:
    symbols = _make_symbols(symbol_ids=["icon_a", "icon_dropped"])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[IconInline(symbol_id="icon_a")],
            )
        ]
    )
    records = check_symbols_to_ir(symbols, ir)
    warnings = [r for r in records if r.code == XREF_SYMBOL_DROPPED]
    assert len(warnings) == 1
    assert warnings[0].entity_ref == "icon_dropped"


def test_symbols_to_ir_empty_ok() -> None:
    symbols = _make_symbols(symbol_ids=[])
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001")])
    assert check_symbols_to_ir(symbols, ir) == []


# --- Boundary 4: PageIRV1 → RenderPageV1 ---


def test_ir_to_render_valid() -> None:
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001", children=[TextInline(text="hi")])])
    render = _make_render(block_ids=["p0001.b001"])
    assert check_ir_to_render(ir, render) == []


def test_ir_to_render_missing_block() -> None:
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001", children=[TextInline(text="hi")])])
    render = _make_render(block_ids=[])
    records = check_ir_to_render(ir, render)
    warnings = [r for r in records if r.code == XREF_IR_TO_RENDER]
    assert len(warnings) == 1
    assert warnings[0].entity_ref == "p0001.b001"


def test_ir_to_render_non_translatable_skipped() -> None:
    from atr_schemas.page_ir_v1 import DividerBlock

    ir = _make_ir(blocks=[DividerBlock(block_id="p0001.b001")])
    render = _make_render(block_ids=[])
    records = check_ir_to_render(ir, render)
    assert all(r.code != XREF_IR_TO_RENDER for r in records)


def test_ir_to_render_dangling_figure_asset() -> None:
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001", children=[TextInline(text="hi")])])
    render = _make_render(
        block_ids=["p0001.b001"],
        figure_blocks=[
            RenderFigureBlock(id="p0001.b002", asset_id="missing_asset"),
        ],
    )
    records = check_ir_to_render(ir, render)
    errors = [r for r in records if r.code == XREF_RENDER_ASSET]
    assert len(errors) == 1
    assert errors[0].entity_ref == "missing_asset"


def test_ir_to_render_figure_asset_present() -> None:
    ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001", children=[TextInline(text="hi")])])
    render = _make_render(
        block_ids=["p0001.b001"],
        figures={"img_001": RenderFigure(src="images/img_001.png")},
        figure_blocks=[
            RenderFigureBlock(id="p0001.b002", asset_id="img_001"),
        ],
    )
    records = check_ir_to_render(ir, render)
    assert all(r.code != XREF_RENDER_ASSET for r in records)


# --- Boundary 5: RenderPageV1 → Published Bundle ---


def test_render_to_publish_valid(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    (release_dir / "pages").mkdir(parents=True)
    (release_dir / "pages" / "p0001.json").write_text("{}")
    (release_dir / "images").mkdir()
    (release_dir / "images" / "fig.png").write_text("")

    render = _make_render(
        block_ids=["p0001.b001"],
        figures={"fig1": RenderFigure(src="images/fig.png")},
    )
    records = check_render_to_publish(render, release_dir, "p0001", "test_doc")
    assert records == []


def test_render_to_publish_missing_page(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    (release_dir / "pages").mkdir(parents=True)

    render = _make_render(block_ids=["p0001.b001"])
    records = check_render_to_publish(render, release_dir, "p0001", "test_doc")
    errors = [r for r in records if r.code == XREF_RENDER_TO_PUBLISH]
    assert len(errors) == 1
    assert errors[0].entity_ref == "p0001"


def test_render_to_publish_missing_figure(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    (release_dir / "pages").mkdir(parents=True)
    (release_dir / "pages" / "p0001.json").write_text("{}")

    render = _make_render(
        block_ids=["p0001.b001"],
        figures={"fig1": RenderFigure(src="images/missing.png")},
    )
    records = check_render_to_publish(render, release_dir, "p0001", "test_doc")
    errors = [r for r in records if r.code == XREF_RENDER_TO_PUBLISH]
    assert len(errors) == 1
    assert errors[0].entity_ref == "fig1"


def test_render_to_publish_empty_src_skipped(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    (release_dir / "pages").mkdir(parents=True)
    (release_dir / "pages" / "p0001.json").write_text("{}")

    render = _make_render(
        block_ids=["p0001.b001"],
        figures={"fig1": RenderFigure(src="")},
    )
    records = check_render_to_publish(render, release_dir, "p0001", "test_doc")
    assert records == []


# --- Aggregator ---


def test_run_cross_stage_checks_aggregates() -> None:
    native = _make_native(words=[_word("w001")])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="hello", source_word_ids=["w001", "w999"])],
            )
        ]
    )
    records = run_cross_stage_checks(
        PageArtifacts(page_id="p0001", document_id="test_doc", native=native, ir=ir)
    )
    assert len(records) == 1
    assert records[0].code == XREF_NATIVE_WORD


def test_run_cross_stage_checks_skips_missing() -> None:
    records = run_cross_stage_checks(PageArtifacts(page_id="p0001", document_id="test_doc"))
    assert records == []


def test_run_cross_stage_checks_multiple_boundaries() -> None:
    native = _make_native(words=[_word("w001")])
    symbols = _make_symbols(symbol_ids=["icon_a"])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="hello", source_word_ids=["w001"]),
                    IconInline(symbol_id="icon_a"),
                ],
            )
        ]
    )
    render = _make_render(block_ids=["p0001.b001"])
    records = run_cross_stage_checks(
        PageArtifacts(
            page_id="p0001",
            document_id="test_doc",
            native=native,
            symbols=symbols,
            ir=ir,
            render=render,
        )
    )
    assert records == []
