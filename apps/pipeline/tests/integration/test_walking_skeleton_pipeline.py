"""Integration test: walking skeleton end-to-end pipeline.

This test proves the architecture by running the full chain:
  source PDF -> ingest -> extract -> symbols -> structure -> translate -> render -> QA
"""

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.services.llm.mock_translator import MockTranslator
from atr_pipeline.services.pdf.rasterizer import render_page_png
from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_pipeline.stages.qa.rules.icon_count_rule import evaluate_icon_count
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_pipeline.stages.structure.block_builder import build_page_ir_simple
from atr_pipeline.stages.symbols.catalog_loader import load_symbol_catalog
from atr_pipeline.stages.symbols.matcher import match_symbols
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.validator import validate_translation
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import PageIRV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_walking_skeleton_end_to_end(tmp_path: Path) -> None:  # noqa: PLR0915
    """Full pipeline from PDF to QA-passing render page."""
    repo = _repo_root()
    config = load_document_config("walking_skeleton", repo_root=repo)

    # 1. Extract native evidence
    native = extract_native_page(
        config.source_pdf_path, page_number=1, document_id="walking_skeleton"
    )
    assert len(native.words) >= 3
    word_texts = [w.text for w in native.words]
    assert "Attack" in word_texts

    # 2. Rasterize and match symbols
    png_bytes = render_page_png(config.source_pdf_path, 1, dpi=config.extraction.layout.dpi)
    raster_path = tmp_path / "p0001.png"
    raster_path.write_bytes(png_bytes)

    catalog = load_symbol_catalog(config.symbol_catalog_path)  # type: ignore[arg-type]
    symbols = match_symbols(native, raster_path, catalog, repo_root=repo)
    assert len(symbols.matches) == 1
    assert symbols.matches[0].symbol_id == "sym.progress"

    # 3. Build English PageIR
    en_ir = build_page_ir_simple(native, symbols)
    assert en_ir.language == LanguageCode.EN
    assert len(en_ir.blocks) == 2
    assert en_ir.blocks[0].type == "heading"
    assert en_ir.blocks[1].type == "paragraph"

    # Check inline icon is in paragraph
    para = en_ir.blocks[1]
    icon_nodes = [c for c in para.children if c.type == "icon"]
    assert len(icon_nodes) == 1
    assert icon_nodes[0].symbol_id == "sym.progress"  # type: ignore[union-attr]

    # 4. Plan translation
    batch = build_translation_batch(en_ir)
    assert len(batch.segments) == 2

    # 5. Mock translate
    translator = MockTranslator()
    response = translator.translate_batch(batch)
    result = response.result
    assert len(result.segments) == 2
    assert response.meta.provider == "mock"

    # 6. Validate translation
    errors = validate_translation(batch, result)
    assert errors == [], f"Translation validation failed: {errors}"

    # 7. Build Russian PageIR from translation result
    ru_blocks = []
    for seg in result.segments:
        source_block = next(b for b in en_ir.blocks if b.block_id == seg.segment_id)
        if source_block.type == "heading":
            from atr_schemas.page_ir_v1 import HeadingBlock

            ru_blocks.append(
                HeadingBlock(block_id=seg.segment_id, level=2, children=list(seg.target_inline))
            )
        else:
            from atr_schemas.page_ir_v1 import ParagraphBlock

            ru_blocks.append(
                ParagraphBlock(block_id=seg.segment_id, children=list(seg.target_inline))
            )

    ru_ir = PageIRV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        dimensions_pt=en_ir.dimensions_pt,
        blocks=ru_blocks,  # type: ignore[arg-type]
        reading_order=en_ir.reading_order,
    )

    # Check icon survives in Russian IR
    ru_para = ru_ir.blocks[1]
    ru_icons = [c for c in ru_para.children if c.type == "icon"]
    assert len(ru_icons) == 1

    # 8. Build render page
    render = build_render_page(ru_ir)
    assert render.page.title == "Проверка атаки"
    assert len(render.blocks) == 2

    # Check icon in render
    render_para = render.blocks[1]
    render_icons = [c for c in render_para.children if c.kind == "icon"]  # type: ignore[union-attr]
    assert len(render_icons) == 1

    # 9. QA: icon count parity
    qa_records = evaluate_icon_count(en_ir, ru_ir, render)
    assert qa_records == [], f"QA failed: {[r.message for r in qa_records]}"

    # Verify glossary mentions
    assert "concept.progress" in render.glossary_mentions
