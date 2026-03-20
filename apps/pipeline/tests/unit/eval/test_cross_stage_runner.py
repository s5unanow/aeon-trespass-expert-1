"""Tests for cross-stage reference aggregation and runner orchestration."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.eval.cross_stage_refs import (
    XREF_NATIVE_WORD,
    PageArtifacts,
    run_cross_stage_checks,
)
from atr_pipeline.eval.cross_stage_runner import run_cross_stage_verification
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import NativePageV1, WordEvidence
from atr_schemas.page_ir_v1 import (
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderTextInline,
)
from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1

_DIMS = PageDimensions(width=612.0, height=792.0)
_BBOX = Rect(x0=0.0, y0=0.0, x1=100.0, y1=100.0)


def _make_native(words: list[WordEvidence] | None = None) -> NativePageV1:
    return NativePageV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        dimensions_pt=_DIMS,
        words=words or [],
    )


def _make_ir(
    blocks: list[ParagraphBlock] | None = None,
) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=blocks or [],
    )


def _make_symbols(symbol_ids: list[str] | None = None) -> SymbolMatchSetV1:
    matches = [SymbolMatch(symbol_id=sid, bbox=_BBOX, score=0.9) for sid in (symbol_ids or [])]
    return SymbolMatchSetV1(document_id="test_doc", page_id="p0001", matches=matches)


def _make_render(block_ids: list[str] | None = None) -> RenderPageV1:
    blocks = [
        RenderParagraphBlock(id=bid, children=[RenderTextInline(text="hello")])
        for bid in (block_ids or [])
    ]
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", source_page_number=1),
        blocks=blocks,
    )


def _word(wid: str) -> WordEvidence:
    return WordEvidence(word_id=wid, text="test", bbox=_BBOX)


# --- Aggregator (run_cross_stage_checks) ---


def test_aggregator_detects_error() -> None:
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


def test_aggregator_skips_missing_artifacts() -> None:
    records = run_cross_stage_checks(PageArtifacts(page_id="p0001", document_id="test_doc"))
    assert records == []


def test_aggregator_multiple_boundaries_clean() -> None:
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


# --- Runner orchestration (run_cross_stage_verification) ---


def _write_artifact(store_root: Path, doc: str, family: str, page: str, data: str) -> None:
    d = store_root / doc / family / "page" / page
    d.mkdir(parents=True, exist_ok=True)
    (d / "abc123.json").write_text(data)


def test_runner_discovers_pages_and_reports(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    native = _make_native(words=[_word("w001")])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="hello", source_word_ids=["w001"])],
            )
        ]
    )
    _write_artifact(tmp_path, "test_doc", "native_page.v1", "p0001", native.model_dump_json())
    _write_artifact(tmp_path, "test_doc", "page_ir.v1.en", "p0001", ir.model_dump_json())

    report = run_cross_stage_verification(document_id="test_doc", store=store)
    assert report.passed is True
    assert len(report.pages) == 1
    assert report.pages[0].page_id == "p0001"
    assert report.pages[0].records == []


def test_runner_reports_errors(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    native = _make_native(words=[_word("w001")])
    ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="hi", source_word_ids=["w999"])],
            )
        ]
    )
    _write_artifact(tmp_path, "test_doc", "native_page.v1", "p0001", native.model_dump_json())
    _write_artifact(tmp_path, "test_doc", "page_ir.v1.en", "p0001", ir.model_dump_json())

    report = run_cross_stage_verification(document_id="test_doc", store=store)
    assert report.passed is False
    assert report.blocking is True
    assert len(report.pages[0].records) == 1
    assert report.pages[0].records[0].code == XREF_NATIVE_WORD


def test_runner_respects_page_filter(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    native = _make_native(words=[])
    _write_artifact(tmp_path, "test_doc", "native_page.v1", "p0001", native.model_dump_json())
    _write_artifact(tmp_path, "test_doc", "native_page.v1", "p0002", native.model_dump_json())

    report = run_cross_stage_verification(
        document_id="test_doc", store=store, page_filter=["p0001"]
    )
    assert len(report.pages) == 1
    assert report.pages[0].page_id == "p0001"


def test_runner_empty_store(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    report = run_cross_stage_verification(document_id="test_doc", store=store)
    assert report.passed is True
    assert report.pages == []
