"""Schema roundtrip tests: serialize -> deserialize -> compare for all core v1 models."""

import json

from atr_schemas import (
    ConfidenceMetrics,
    NativePageV1,
    PageDimensions,
    PageIRV1,
    ProvenanceRef,
    QARecordV1,
    QAState,
    QASummaryV1,
    Rect,
    RenderPageV1,
    SourceManifestV1,
)
from atr_schemas.enums import LanguageCode, QALayer, Severity
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.render_page_v1 import (
    RenderHeadingBlock,
    RenderIconInline,
    RenderPageMeta,
    RenderParagraphBlock,
    RenderTextInline,
)
from atr_schemas.source_manifest_v1 import PageEntry


def _roundtrip(model_instance: object) -> None:
    """Serialize to JSON and deserialize back, assert equality."""
    model_cls = type(model_instance)
    json_str = model_cls.model_validate(model_instance).model_dump_json()
    parsed = json.loads(json_str)
    restored = model_cls.model_validate(parsed)
    assert restored == model_instance


def test_source_manifest_roundtrip() -> None:
    manifest = SourceManifestV1(
        document_id="ato_core_v1_1",
        source_pdf_sha256="abc123",
        page_count=1,
        pages=[PageEntry(page_id="p0001", page_number=1)],
    )
    _roundtrip(manifest)


def test_native_page_roundtrip() -> None:
    from atr_schemas.native_page_v1 import ImageBlockEvidence, WordEvidence

    page = NativePageV1(
        document_id="ato_core_v1_1",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=595.2, height=841.8),
        words=[
            WordEvidence(
                word_id="w001",
                text="Attack",
                bbox=Rect(x0=58.2, y0=74.1, x1=120.0, y1=92.6),
            )
        ],
        image_blocks=[
            ImageBlockEvidence(
                image_id="img001",
                bbox=Rect(x0=108.0, y0=119.0, x1=122.0, y1=133.0),
                width_px=14,
                height_px=14,
            )
        ],
    )
    _roundtrip(page)


def test_page_ir_roundtrip() -> None:
    ir = PageIRV1(
        document_id="ato_core_v1_1",
        page_id="p0042",
        page_number=42,
        language=LanguageCode.EN,
        dimensions_pt=PageDimensions(width=595.2, height=841.8),
        blocks=[
            HeadingBlock(
                block_id="p0042.b001",
                level=2,
                children=[TextInline(text="Attack Test", lang=LanguageCode.EN)],
            ),
            ParagraphBlock(
                block_id="p0042.b002",
                children=[
                    TextInline(text="Gain 1 ", lang=LanguageCode.EN),
                    IconInline(symbol_id="sym.progress", instance_id="syminst.p0042.01"),
                    TextInline(text=" Progress.", lang=LanguageCode.EN),
                ],
            ),
        ],
        reading_order=["p0042.b001", "p0042.b002"],
        confidence=ConfidenceMetrics(native_text_coverage=0.99),
        qa_state=QAState(blocking=False, errors=0, warnings=0),
        provenance=ProvenanceRef(extractor="pymupdf", version="1"),
    )
    _roundtrip(ir)


def test_page_ir_discriminated_union() -> None:
    """Verify block and inline discriminated unions work from raw dicts."""
    raw = {
        "schema_version": "page_ir.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 1,
        "language": "en",
        "blocks": [
            {
                "type": "heading",
                "block_id": "p0001.b001",
                "level": 1,
                "children": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "paragraph",
                "block_id": "p0001.b002",
                "children": [
                    {"type": "text", "text": "Get 1 "},
                    {"type": "icon", "symbol_id": "sym.progress"},
                    {"type": "text", "text": " Progress."},
                ],
            },
        ],
    }
    ir = PageIRV1.model_validate(raw)
    assert len(ir.blocks) == 2
    heading = ir.blocks[0]
    assert isinstance(heading, HeadingBlock)
    paragraph = ir.blocks[1]
    assert isinstance(paragraph, ParagraphBlock)
    assert len(paragraph.children) == 3
    assert isinstance(paragraph.children[1], IconInline)
    assert paragraph.children[1].symbol_id == "sym.progress"


def test_render_page_roundtrip() -> None:
    render = RenderPageV1(
        page=RenderPageMeta(id="p0042", title="Проверка атаки", source_page_number=42),
        blocks=[
            RenderHeadingBlock(
                id="p0042.b001",
                level=2,
                children=[
                    RenderTextInline(text="Проверка атаки"),
                ],
            ),
            RenderParagraphBlock(
                id="p0042.b002",
                children=[
                    RenderTextInline(text="Получите 1 "),
                    RenderIconInline(symbol_id="sym.progress", alt="Прогресс"),
                    RenderTextInline(text=" Прогресс."),
                ],
            ),
        ],
        glossary_mentions=["concept.progress"],
    )
    _roundtrip(render)


def test_qa_record_roundtrip() -> None:
    record = QARecordV1(
        qa_id="qa.p0042.icon.01",
        layer=QALayer.ICON_SYMBOL,
        severity=Severity.ERROR,
        code="INLINE_SYMBOL_COUNT_MISMATCH",
        document_id="ato_core_v1_1",
        page_id="p0042",
        message="Icon count mismatch",
        expected={"count": 1},
        actual={"count": 0},
    )
    _roundtrip(record)


def test_qa_summary_roundtrip() -> None:
    summary = QASummaryV1(
        document_id="ato_core_v1_1",
        run_id="run_001",
        blocking=False,
    )
    _roundtrip(summary)


def test_asset_roundtrip() -> None:
    from atr_schemas.asset_v1 import AssetV1
    from atr_schemas.enums import AssetKind

    asset = AssetV1(
        asset_id="asset.inline.p0042.07",
        kind=AssetKind.INLINE_SYMBOL,
        source_page_id="p0042",
        bbox=Rect(x0=108.0, y0=119.0, x1=122.0, y1=133.0),
        sha256="abc123",
    )
    _roundtrip(asset)


def test_layout_page_roundtrip() -> None:
    from atr_schemas.layout_page_v1 import LayoutPageV1, LayoutZone

    layout = LayoutPageV1(
        document_id="test",
        page_id="p0001",
        zones=[
            LayoutZone(
                zone_id="z001",
                kind="body",
                bbox=Rect(x0=50, y0=50, x1=545, y1=790),
            )
        ],
    )
    _roundtrip(layout)


def test_concept_registry_roundtrip() -> None:
    from atr_schemas.concept_registry_v1 import (
        ConceptRegistryV1,
        ConceptSource,
        ConceptTarget,
        ConceptV1,
    )

    registry = ConceptRegistryV1(
        version="glossary.2026-03-15.1",
        concepts=[
            ConceptV1(
                concept_id="concept.progress",
                kind="icon_term",
                source=ConceptSource(lemma="Progress", aliases=["progress token"]),
                target=ConceptTarget(
                    lemma="Прогресс",
                    allowed_surface_forms=["Прогресс", "Прогресса"],
                ),
                icon_binding="sym.progress",
                forbidden_targets=["Продвижение"],
            )
        ],
    )
    _roundtrip(registry)


def test_glossary_payload_roundtrip() -> None:
    from atr_schemas.glossary_payload_v1 import GlossaryEntryV1, GlossaryPayloadV1

    payload = GlossaryPayloadV1(
        document_id="test",
        entries=[
            GlossaryEntryV1(
                concept_id="concept.progress",
                preferred_term="Прогресс",
                source_term="Progress",
                icon_binding="sym.progress",
            )
        ],
    )
    _roundtrip(payload)


def test_search_docs_roundtrip() -> None:
    from atr_schemas.search_docs_v1 import SearchDocEntry, SearchDocsV1

    docs = SearchDocsV1(
        document_id="test",
        docs=[
            SearchDocEntry(
                page_id="p0001",
                title="Проверка атаки",
                text="Получите 1 Прогресс",
                normalized_terms=["получить", "прогресс"],
            )
        ],
    )
    _roundtrip(docs)


def test_run_manifest_roundtrip() -> None:
    from atr_schemas.run_manifest_v1 import RunManifestV1

    manifest = RunManifestV1(run_id="run_001", pipeline_version="0.1.0")
    _roundtrip(manifest)


def test_build_manifest_roundtrip() -> None:
    from atr_schemas.build_manifest_v1 import BuildManifestV1

    manifest = BuildManifestV1(
        build_id="build_001",
        document_id="test",
        content_version="v1.abc123",
    )
    _roundtrip(manifest)


def test_patch_set_roundtrip() -> None:
    from atr_schemas.patch_set_v1 import PatchOperation, PatchSetV1

    patches = PatchSetV1(
        patch_id="patch_001",
        target_artifact_ref="test/page_ir.v1/page/p0001/abc.json",
        operations=[
            PatchOperation(op="replace", path="/blocks/0/children/0/text", value="Fixed text")
        ],
        reason="Manual correction",
        author="reviewer",
    )
    _roundtrip(patches)


def test_symbol_catalog_roundtrip() -> None:
    from atr_schemas.symbol_catalog_v1 import SymbolCatalogV1, SymbolEntry

    catalog = SymbolCatalogV1(
        catalog_id="test",
        version="1.0",
        symbols=[SymbolEntry(symbol_id="sym.progress", label="Progress", match_threshold=0.93)],
    )
    _roundtrip(catalog)


def test_symbol_match_set_roundtrip() -> None:
    from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1

    matches = SymbolMatchSetV1(
        document_id="test",
        page_id="p0001",
        matches=[
            SymbolMatch(
                symbol_id="sym.progress",
                bbox=Rect(x0=130, y0=112, x1=146, y1=128),
                score=0.95,
            )
        ],
    )
    _roundtrip(matches)


def test_translation_batch_roundtrip() -> None:
    from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment

    batch = TranslationBatchV1(
        batch_id="tr.p0001.01",
        segments=[
            TranslationSegment(
                segment_id="p0001.b001",
                block_type="heading",
                source_inline=[TextInline(text="Attack Test")],
            )
        ],
    )
    _roundtrip(batch)


def test_translation_result_roundtrip() -> None:
    from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1

    result = TranslationResultV1(
        batch_id="tr.p0001.01",
        segments=[
            TranslatedSegment(
                segment_id="p0001.b001",
                target_inline=[TextInline(text="Проверка атаки")],
            )
        ],
    )
    _roundtrip(result)


def test_rule_chunk_roundtrip() -> None:
    from atr_schemas.common import NormRect
    from atr_schemas.rule_chunk_v1 import GlossaryConcept, RuleChunkV1

    chunk = RuleChunkV1(
        rule_chunk_id="rc.ato_core_v1_1.en.p0042.01",
        document_id="ato_core_v1_1",
        edition="en",
        page_id="p0042",
        source_page_number=42,
        section_path=["Chapter 5", "Attack Test"],
        block_ids=["p0042.b001", "p0042.b002"],
        canonical_anchor_id="rule.chunk.0042.01",
        language=LanguageCode.EN,
        text="Gain 1 Progress.",
        normalized_text="gain 1 progress",
        glossary_concepts=[GlossaryConcept(concept_id="concept.progress", surface_form="Progress")],
        symbol_ids=["sym.progress"],
        deep_link="/documents/ato_core_v1_1/en/p0042#anchor=rule.chunk.0042.01",
        facsimile_bbox_refs=[NormRect(x0=0.1, y0=0.2, x1=0.9, y1=0.3)],
    )
    _roundtrip(chunk)


def test_rule_chunk_minimal_roundtrip() -> None:
    from atr_schemas.rule_chunk_v1 import RuleChunkV1

    chunk = RuleChunkV1(
        rule_chunk_id="rc.test.en.p0001.01",
        document_id="test",
        edition="en",
        page_id="p0001",
        source_page_number=1,
        canonical_anchor_id="rule.chunk.0001.01",
        language=LanguageCode.EN,
        text="A simple rule.",
    )
    _roundtrip(chunk)


def test_assistant_citation_roundtrip() -> None:
    from atr_schemas.assistant_citation_v1 import AssistantCitationV1

    citation = AssistantCitationV1(
        document_id="ato_core_v1_1",
        edition="en",
        page_id="p0042",
        source_page_number=42,
        canonical_anchor_id="rule.chunk.0042.01",
        deep_link="/documents/ato_core_v1_1/en/p0042#anchor=rule.chunk.0042.01",
        quote_snippet="Gain 1 Progress.",
        relevance_reason="Directly answers the attack test resolution step.",
    )
    _roundtrip(citation)


def test_assistant_pack_roundtrip() -> None:
    from atr_schemas.assistant_pack_v1 import AssistantPackV1

    pack = AssistantPackV1(
        document_id="ato_core_v1_1",
        edition="en",
        chunks_count=150,
        index_path="assistant/ato_core_v1_1/en/assistant_index.sqlite",
        chunks_path="assistant/ato_core_v1_1/en/rule_chunks.json",
        build_id="build_001",
        generated_at="2026-03-27T08:00:00Z",
        pipeline_version="0.2.0",
    )
    _roundtrip(pack)
