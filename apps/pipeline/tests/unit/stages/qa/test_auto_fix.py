"""Tests for QA auto-fix patch generation."""

from __future__ import annotations

from atr_pipeline.stages.qa.auto_fix import generate_patches_for_page
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import AutoFix, QARecordV1
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def _page(blocks: list[RenderParagraphBlock]) -> RenderPageV1:
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", title="Test", source_page_number=1),
        blocks=blocks,
        source_map=RenderSourceMap(page_id="p0001", block_refs=[]),
    )


def _para(block_id: str, text: str) -> RenderParagraphBlock:
    return RenderParagraphBlock(
        id=block_id,
        children=[RenderTextInline(text=text)],
    )


def _record(
    code: str,
    entity_ref: str,
    fixer: str,
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.p0001.test.{entity_ref}",
        layer=QALayer.RENDER,
        severity=Severity.WARNING,
        code=code,
        document_id="test",
        page_id="p0001",
        entity_ref=entity_ref,
        message="test",
        auto_fix=AutoFix(available=True, fixer=fixer),
    )


# ── Remove decorative ────────────────────────────────────────────────


class TestRemoveDecorative:
    def test_strips_asset_token(self) -> None:
        page = _page([_para("b1", "Используйте AM0308 для атаки")])
        records = [_record("DECORATIVE_ICON_LEAKED", "b1", "remove_decorative")]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        assert len(patch.operations) == 1
        op = patch.operations[0]
        assert op.op == "replace"
        assert op.path == "/blocks/0/children/0/text"
        assert "AM0308" not in str(op.value)

    def test_strips_private_use_glyph(self) -> None:
        page = _page([_para("b1", "Текст \ue001 после")])
        records = [_record("DECORATIVE_ICON_LEAKED", "b1", "remove_decorative")]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        op = patch.operations[0]
        assert "\ue001" not in str(op.value)

    def test_no_patch_for_clean_text(self) -> None:
        page = _page([_para("b1", "Clean text")])
        records = [_record("DECORATIVE_ICON_LEAKED", "b1", "remove_decorative")]

        patch = generate_patches_for_page(records, page)

        assert patch is None

    def test_no_patch_when_no_fixable_records(self) -> None:
        page = _page([_para("b1", "AM0308 here")])
        record = QARecordV1(
            qa_id="qa.p0001.test.b1",
            layer=QALayer.RENDER,
            severity=Severity.WARNING,
            code="DECORATIVE_ICON_LEAKED",
            document_id="test",
            page_id="p0001",
            entity_ref="b1",
            message="test",
        )
        patch = generate_patches_for_page([record], page)

        assert patch is None


# ── Delete duplicate ──────────────────────────────────────────────────


class TestDeleteDuplicate:
    def test_generates_delete_op(self) -> None:
        page = _page([_para("b1", "same text"), _para("b2", "same text")])
        records = [_record("DUPLICATE_CONTENT", "b2", "delete_duplicate")]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        assert len(patch.operations) == 1
        op = patch.operations[0]
        assert op.op == "delete"
        assert op.path == "/blocks/1"

    def test_multiple_deletes_highest_index_first(self) -> None:
        page = _page(
            [
                _para("b1", "same"),
                _para("b2", "same"),
                _para("b3", "other"),
                _para("b4", "other"),
            ]
        )
        records = [
            _record("DUPLICATE_CONTENT", "b2", "delete_duplicate"),
            _record("DUPLICATE_CONTENT", "b4", "delete_duplicate"),
        ]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        assert len(patch.operations) == 2
        assert patch.operations[0].path == "/blocks/3"
        assert patch.operations[1].path == "/blocks/1"


# ── Split paragraph ──────────────────────────────────────────────────


class TestSplitParagraph:
    def test_splits_at_sentence_boundary(self) -> None:
        long_text = "First sentence here. Second sentence here."
        page = _page([_para("b1", long_text)])
        records = [_record("PARAGRAPH_TOO_LONG", "b1", "split_paragraph")]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        assert len(patch.operations) == 2
        assert patch.operations[0].op == "replace"
        assert patch.operations[0].path == "/blocks/0/children"
        assert patch.operations[1].op == "insert"
        assert patch.operations[1].path == "/blocks/1"
        new_block = patch.operations[1].value
        assert isinstance(new_block, dict)
        assert new_block["id"] == "b1_split"

    def test_no_split_without_sentence_boundary(self) -> None:
        page = _page([_para("b1", "no sentence boundaries just one long run")])
        records = [_record("PARAGRAPH_TOO_LONG", "b1", "split_paragraph")]

        patch = generate_patches_for_page(records, page)

        assert patch is None

    def test_preserves_text_content_after_split(self) -> None:
        text = "Начало предложения. Конец предложения."
        page = _page([_para("b1", text)])
        records = [_record("PARAGRAPH_TOO_LONG", "b1", "split_paragraph")]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        first_children = patch.operations[0].value
        second_block = patch.operations[1].value
        assert isinstance(first_children, list)
        assert isinstance(second_block, dict)
        first_text = "".join(c["text"] for c in first_children)
        second_text = "".join(c["text"] for c in second_block["children"])
        # Boundary whitespace is consumed by the split
        assert first_text == "Начало предложения."
        assert second_text == "Конец предложения."


# ── Mixed fixers ─────────────────────────────────────────────────────


class TestMixedFixers:
    def test_replace_before_structural(self) -> None:
        """Text replacements appear before structural ops."""
        page = _page(
            [
                _para("b1", "Token AM0308 here"),
                _para("b2", "same text"),
                _para("b3", "same text"),
            ]
        )
        records = [
            _record("DECORATIVE_ICON_LEAKED", "b1", "remove_decorative"),
            _record("DUPLICATE_CONTENT", "b3", "delete_duplicate"),
        ]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        assert patch.operations[0].op == "replace"
        assert patch.operations[1].op == "delete"

    def test_patch_metadata(self) -> None:
        page = _page([_para("b1", "AM0308 test")])
        records = [_record("DECORATIVE_ICON_LEAKED", "b1", "remove_decorative")]

        patch = generate_patches_for_page(records, page)

        assert patch is not None
        assert patch.patch_id.startswith("auto-fix-p0001-")
        assert patch.author == "qa-auto-fix"
