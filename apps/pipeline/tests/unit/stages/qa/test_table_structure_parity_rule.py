"""Tests for the table_structure_parity QA rule (S5U-736).

The rule asserts EN<->RU structural parity for ``TableBlock`` instances
across paired source/target IR pages.  Five fixture cases per the
S5U-736 acceptance criteria:

1. Happy path — EN structured table (2+ rows, 2+ cells each) with full
   RU parity emits no records.
2. Failure — RU table with a missing row triggers
   ``TABLE_PARITY_ROW_COUNT_MISMATCH``.
3. Failure — row with mismatched cell count triggers
   ``TABLE_PARITY_CELL_COUNT_MISMATCH``.
4. Failure — ``is_header`` flag drift triggers
   ``TABLE_PARITY_HEADER_FLAG_DRIFT`` (row-level and cell-level
   variants).
5. Skip — EN table with all cells ``translatable=False`` and no RU
   counterpart at the same ``block_id`` is allowed (silent).
"""

from __future__ import annotations

import copy

from atr_pipeline.stages.qa.rules.table_structure_parity_rule import (
    evaluate_table_structure_parity,
)
from atr_schemas.enums import LanguageCode, QALayer, Severity
from atr_schemas.page_ir_v1 import (
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TextInline,
)


def _cell(
    block_id: str, text: str, *, header: bool = False, translatable: bool = True
) -> TableCellBlock:
    return TableCellBlock(
        block_id=block_id,
        header=header,
        translatable=translatable,
        children=[TextInline(text=text)],
    )


def _row(block_id: str, cells: list[TableCellBlock], *, header: bool = False) -> TableRowBlock:
    return TableRowBlock(block_id=block_id, header=header, cells=cells)


def _table(block_id: str, rows: list[TableRowBlock], *, translatable: bool = True) -> TableBlock:
    return TableBlock(
        block_id=block_id,
        translatable=translatable,
        children=list(rows),  # type: ignore[arg-type]
    )


def _page(lang: LanguageCode, blocks: list[TableBlock]) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        language=lang,
        blocks=list(blocks),  # type: ignore[arg-type]
        reading_order=[b.block_id for b in blocks],
    )


def _structured_2x2(block_id: str, lang_text_prefix: str) -> TableBlock:
    """Build a structured table with one header row + one body row, two cells each."""
    return _table(
        block_id=block_id,
        rows=[
            _row(
                f"{block_id}.r0",
                [
                    _cell(f"{block_id}.r0.c0", f"{lang_text_prefix}-h0", header=True),
                    _cell(f"{block_id}.r0.c1", f"{lang_text_prefix}-h1", header=True),
                ],
                header=True,
            ),
            _row(
                f"{block_id}.r1",
                [
                    _cell(f"{block_id}.r1.c0", f"{lang_text_prefix}-b0"),
                    _cell(f"{block_id}.r1.c1", f"{lang_text_prefix}-b1"),
                ],
            ),
        ],
    )


def test_happy_path_parity_silent() -> None:
    """Fixture 1 — EN structured 2-row x 2-cell table with full RU parity
    emits zero records.

    Three-input discipline:
        happy = this test (silent),
        failure = test_missing_row_emits_row_count_mismatch (row drop fires),
        adversarial = test_skip_case_non_translatable_table_silent (silent
            in a different shape — RU absent but EN non-translatable).
    """
    en = _page(LanguageCode.EN, [_structured_2x2("p0001.b001", "en")])
    ru = _page(LanguageCode.RU, [_structured_2x2("p0001.b001", "ru")])
    assert evaluate_table_structure_parity(en, ru) == []


def test_missing_row_emits_row_count_mismatch() -> None:
    """Fixture 2 — RU table with a missing row triggers
    TABLE_PARITY_ROW_COUNT_MISMATCH at ERROR severity.
    """
    en_table = _structured_2x2("p0001.b001", "en")
    ru_table = _structured_2x2("p0001.b001", "ru")
    # Drop the body row from RU.
    ru_table = _table(
        block_id=ru_table.block_id,
        rows=[c for c in ru_table.children if isinstance(c, TableRowBlock)][:1],
    )
    en = _page(LanguageCode.EN, [en_table])
    ru = _page(LanguageCode.RU, [ru_table])

    records = evaluate_table_structure_parity(en, ru)
    assert len(records) == 1
    rec = records[0]
    assert rec.code == "TABLE_PARITY_ROW_COUNT_MISMATCH"
    assert rec.severity == Severity.ERROR
    assert rec.layer == QALayer.STRUCTURE
    assert rec.entity_ref == "p0001.b001"
    assert rec.expected == {"rows": 2}
    assert rec.actual == {"rows": 1}


def test_mismatched_cell_count_emits_cell_count_mismatch() -> None:
    """Fixture 3 — row with mismatched cell count triggers
    TABLE_PARITY_CELL_COUNT_MISMATCH and no spurious header-drift dive.
    """
    en_table = _structured_2x2("p0001.b001", "en")
    ru_table = _structured_2x2("p0001.b001", "ru")
    # Drop the second cell from RU's body row.
    ru_rows = [c for c in ru_table.children if isinstance(c, TableRowBlock)]
    ru_rows[1] = _row(
        ru_rows[1].block_id,
        ru_rows[1].cells[:1],
        header=ru_rows[1].header,
    )
    ru_table = _table(block_id=ru_table.block_id, rows=ru_rows)

    en = _page(LanguageCode.EN, [en_table])
    ru = _page(LanguageCode.RU, [ru_table])

    records = evaluate_table_structure_parity(en, ru)
    assert len(records) == 1
    rec = records[0]
    assert rec.code == "TABLE_PARITY_CELL_COUNT_MISMATCH"
    assert rec.severity == Severity.ERROR
    assert rec.entity_ref == "p0001.b001.r1"
    assert rec.expected == {"cells": 2}
    assert rec.actual == {"cells": 1}


def test_row_header_flag_drift_emits_finding() -> None:
    """Fixture 4a — RU row's ``header`` flag drifts from EN; the rule
    emits TABLE_PARITY_HEADER_FLAG_DRIFT scoped to the row block_id.
    """
    en_table = _structured_2x2("p0001.b001", "en")
    ru_table = _structured_2x2("p0001.b001", "ru")
    ru_rows = [c for c in ru_table.children if isinstance(c, TableRowBlock)]
    ru_rows[0] = _row(ru_rows[0].block_id, ru_rows[0].cells, header=False)  # was True
    ru_table = _table(block_id=ru_table.block_id, rows=ru_rows)

    en = _page(LanguageCode.EN, [en_table])
    ru = _page(LanguageCode.RU, [ru_table])

    records = evaluate_table_structure_parity(en, ru)
    drift = [r for r in records if r.code == "TABLE_PARITY_HEADER_FLAG_DRIFT"]
    assert len(drift) >= 1
    row_drift = [r for r in drift if r.entity_ref == "p0001.b001.r0"]
    assert len(row_drift) == 1
    assert row_drift[0].expected == {"header": True}
    assert row_drift[0].actual == {"header": False}


def test_cell_header_flag_drift_emits_finding() -> None:
    """Fixture 4b — RU cell's ``header`` flag drifts from EN while the
    enclosing row's flag agrees; the rule emits one cell-scoped
    TABLE_PARITY_HEADER_FLAG_DRIFT and no row-scoped finding.
    """
    en_table = _structured_2x2("p0001.b001", "en")
    ru_table = copy.deepcopy(en_table)  # identical shape, then mutate one cell flag.
    ru_rows = [c for c in ru_table.children if isinstance(c, TableRowBlock)]
    ru_rows[1].cells[0] = _cell(
        ru_rows[1].cells[0].block_id,
        "ru-b0",
        header=True,  # EN body cell was header=False
        translatable=ru_rows[1].cells[0].translatable,
    )

    en = _page(LanguageCode.EN, [en_table])
    ru = _page(LanguageCode.RU, [ru_table])

    records = evaluate_table_structure_parity(en, ru)
    drift = [r for r in records if r.code == "TABLE_PARITY_HEADER_FLAG_DRIFT"]
    assert len(drift) == 1
    assert drift[0].entity_ref == "p0001.b001.r1.c0"
    assert drift[0].expected == {"header": False}
    assert drift[0].actual == {"header": True}


def test_skip_case_non_translatable_table_silent() -> None:
    """Fixture 5 — EN table with every cell ``translatable=False`` and no
    matching RU table at the same block_id emits zero records (the
    re-materializer is allowed to skip such tables).
    """
    en_table = _table(
        block_id="p0001.b002",
        rows=[
            _row(
                "p0001.b002.r0",
                [
                    _cell("p0001.b002.r0.c0", "code", translatable=False),
                    _cell("p0001.b002.r0.c1", "OK", translatable=False),
                ],
            ),
        ],
    )
    en = _page(LanguageCode.EN, [en_table])
    ru = _page(LanguageCode.RU, [])  # no RU counterpart at all
    assert evaluate_table_structure_parity(en, ru) == []


def test_missing_ru_table_with_translatable_content_fires() -> None:
    """Adversarial — EN has translatable content but no RU counterpart at
    the same block_id; the rule emits TABLE_PARITY_MISSING_RU_TABLE.

    Distinguishes the skip-case (which is silent) from the bug shape.
    """
    en = _page(LanguageCode.EN, [_structured_2x2("p0001.b001", "en")])
    ru = _page(LanguageCode.RU, [])

    records = evaluate_table_structure_parity(en, ru)
    assert len(records) == 1
    rec = records[0]
    assert rec.code == "TABLE_PARITY_MISSING_RU_TABLE"
    assert rec.severity == Severity.ERROR
    assert rec.entity_ref == "p0001.b001"


def test_non_translatable_row_excluded_from_row_count() -> None:
    """A row whose every cell is ``translatable=False`` is excluded from
    the row-count comparison on both sides — the planner skips emitting
    segments for such rows so the RU re-materializer legitimately
    produces a shorter table.
    """
    en_table = _table(
        block_id="p0001.b001",
        rows=[
            _row(
                "p0001.b001.r0",
                [
                    _cell("p0001.b001.r0.c0", "h0", header=True),
                    _cell("p0001.b001.r0.c1", "h1", header=True),
                ],
                header=True,
            ),
            _row(
                "p0001.b001.r1",
                [
                    _cell("p0001.b001.r1.c0", "code", translatable=False),
                    _cell("p0001.b001.r1.c1", "OK", translatable=False),
                ],
            ),
            _row(
                "p0001.b001.r2",
                [
                    _cell("p0001.b001.r2.c0", "b0"),
                    _cell("p0001.b001.r2.c1", "b1"),
                ],
            ),
        ],
    )
    # RU re-materializer drops the non-translatable middle row.
    ru_table = _table(
        block_id="p0001.b001",
        rows=[
            _row(
                "p0001.b001.r0",
                [
                    _cell("p0001.b001.r0.c0", "ru-h0", header=True),
                    _cell("p0001.b001.r0.c1", "ru-h1", header=True),
                ],
                header=True,
            ),
            _row(
                "p0001.b001.r2",
                [
                    _cell("p0001.b001.r2.c0", "ru-b0"),
                    _cell("p0001.b001.r2.c1", "ru-b1"),
                ],
            ),
        ],
    )
    en = _page(LanguageCode.EN, [en_table])
    ru = _page(LanguageCode.RU, [ru_table])
    assert evaluate_table_structure_parity(en, ru) == []


def test_non_table_blocks_ignored() -> None:
    """A page containing no TableBlock entries emits zero records."""
    en = PageIRV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[],
        reading_order=[],
    )
    ru = PageIRV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        blocks=[],
        reading_order=[],
    )
    assert evaluate_table_structure_parity(en, ru) == []


def test_page_id_mismatch_returns_empty() -> None:
    """Defensive — the QA stage feeds matched (en, ru) by page_id; a
    page_id mismatch indicates an upstream bug, not a parity defect, so
    the rule returns no records.
    """
    en = _page(LanguageCode.EN, [_structured_2x2("p0001.b001", "en")])
    ru = PageIRV1(
        document_id="test_doc",
        page_id="p0002",
        page_number=2,
        language=LanguageCode.RU,
        blocks=[],
        reading_order=[],
    )
    assert evaluate_table_structure_parity(en, ru) == []
