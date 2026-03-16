"""Tests for render payload builders."""

from pathlib import Path

from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
from atr_pipeline.stages.render.glossary_builder import build_glossary_payload
from atr_pipeline.stages.render.nav_builder import build_nav_payload
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_pipeline.stages.render.search_builder import build_search_docs
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import HeadingBlock, IconInline, PageIRV1, ParagraphBlock, TextInline


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ru_ir() -> PageIRV1:
    return PageIRV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0001.b001",
                level=2,
                children=[TextInline(text="Проверка атаки", lang=LanguageCode.RU)],
            ),
            ParagraphBlock(
                block_id="p0001.b002",
                children=[
                    TextInline(text="Получите 1 ", lang=LanguageCode.RU),
                    IconInline(symbol_id="sym.progress", instance_id="syminst.p0001.01"),
                    TextInline(text=" Прогресс.", lang=LanguageCode.RU),
                ],
            ),
        ],
        reading_order=["p0001.b001", "p0001.b002"],
    )


def test_render_page_builder() -> None:
    """Build a render page from Russian IR."""
    ir = _make_ru_ir()
    render = build_render_page(ir)

    assert render.page.title == "Проверка атаки"
    assert render.page.source_page_number == 1
    assert len(render.blocks) == 2
    assert "concept.progress" in render.glossary_mentions


def test_glossary_builder() -> None:
    """Build glossary payload from concept registry."""
    ir = _make_ru_ir()
    render = build_render_page(ir)
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")

    glossary = build_glossary_payload("walking_skeleton", registry, [render])

    assert len(glossary.entries) == 1
    assert glossary.entries[0].concept_id == "concept.progress"
    assert glossary.entries[0].preferred_term == "Прогресс"
    assert glossary.entries[0].icon_binding == "sym.progress"


def test_search_builder() -> None:
    """Build search docs from render page."""
    ir = _make_ru_ir()
    render = build_render_page(ir)

    search = build_search_docs("walking_skeleton", [render])

    assert len(search.docs) == 1
    doc = search.docs[0]
    assert doc.page_id == "p0001"
    assert "Проверка" in doc.text
    assert len(doc.normalized_terms) > 0


def test_nav_builder() -> None:
    """Build nav payload from render pages."""
    ir = _make_ru_ir()
    render = build_render_page(ir)
    render_data = render.model_dump()

    nav = build_nav_payload("walking_skeleton", [render_data])

    assert nav["document_id"] == "walking_skeleton"
    pages = nav["pages"]
    assert len(pages) == 1  # type: ignore[arg-type]
    assert pages[0]["page_id"] == "p0001"  # type: ignore[index]


def test_concept_registry_loader() -> None:
    """Load concept registry from TOML."""
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")

    assert len(registry.concepts) >= 9  # stat icons + game terms
    # Verify a known concept loads correctly
    by_id = {c.concept_id: c for c in registry.concepts}
    c = by_id["concept.progress"]
    assert c.source.lemma == "Progress"
    assert c.target.lemma == "Прогресс"
    assert c.icon_binding == "sym.progress"
    assert "Продвижение" in c.forbidden_targets
    # Verify Triskelion stats are present
    assert "concept.danger" in by_id
    assert "concept.fate" in by_id
    assert "concept.rage" in by_id
