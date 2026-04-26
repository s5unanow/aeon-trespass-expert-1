"""QA rule: EN<->RU TableBlock structural parity (S5U-736).

S5U-734 (PR #328) added per-cell translation segments and a
re-materializer that stitches translated cells back into
``TableRowBlock`` / ``TableCellBlock`` on the RU side.  The structural
round-trip path now works, but there is no dedicated QA rule that
asserts EN<->RU structural parity at the table level.  Without this
rule, a future re-materializer regression (dropped row, collapsed
cells, header-flag drift) would pass CI silently.

This rule iterates EN<->RU block pairs of ``block_type == "table"`` by
``block_id`` and emits findings for the four invariants:

1. ``MISSING_RU_TABLE`` — every EN ``TableBlock`` that contains at
   least one translatable child must have a corresponding RU
   ``TableBlock`` at the same ``block_id``.  The "translatable" filter
   is what makes the skip-case work: an EN table whose cells are all
   ``translatable=False`` is allowed to have no RU counterpart (the
   translation planner emits no segments for it, so the re-materializer
   never produces one).
2. ``ROW_COUNT_MISMATCH`` — row counts match between EN and RU,
   excluding rows where **all** cells are ``translatable=False`` on
   both sides (those are pass-through rows that may legitimately be
   absent on the RU side).
3. ``CELL_COUNT_MISMATCH`` — for each paired row, cell counts match.
4. ``HEADER_FLAG_DRIFT`` — ``header`` flag on rows and cells agrees.

Severity is ``ERROR`` (block_publish_on default) so the QA gate refuses
to publish a document with a structural drift between EN and RU table
shape.
"""

from __future__ import annotations

from atr_schemas.enums import QALayer, Severity
from atr_schemas.page_ir_v1 import (
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
)
from atr_schemas.qa_record_v1 import QARecordV1


def _index_tables(page_ir: PageIRV1) -> dict[str, TableBlock]:
    """Return a ``block_id -> TableBlock`` map for all tables on a page."""
    return {block.block_id: block for block in page_ir.blocks if isinstance(block, TableBlock)}


def _structured_rows(table: TableBlock) -> list[TableRowBlock]:
    """Return only the ``TableRowBlock`` children, ignoring legacy flat inlines.

    The S5U-704 ``TableBlock`` schema mixes flat inlines and structured
    rows; this rule only meaningfully compares the structured form.
    """
    return [c for c in table.children if isinstance(c, TableRowBlock)]


def _all_cells_non_translatable(row: TableRowBlock) -> bool:
    """A row is "pass-through" iff every cell is marked ``translatable=False``.

    The S5U-734 translation planner emits no segments for such cells, so
    the re-materializer never produces them on the RU side.  The row
    count comparison must exclude these rows on both sides to avoid a
    false-positive parity failure on the legitimate skip-case.
    """
    if not row.cells:
        # An empty row carries no translatable content by definition.
        return True
    return all(not cell.translatable for cell in row.cells)


def _has_any_translatable_content(table: TableBlock) -> bool:
    """Return True iff the EN table has any translatable cell or inline.

    Used to decide whether a missing RU counterpart is a real defect
    (EN had translatable content but RU produced nothing) vs the
    documented skip-case (EN was entirely pass-through, so the planner
    emits no segments and the re-materializer never builds an RU
    table).
    """
    if not table.translatable:
        return False
    for child in table.children:
        if isinstance(child, TableRowBlock):
            for cell in child.cells:
                if cell.translatable:
                    return True
        else:
            # Legacy flat inlines are translatable as a unit if the
            # parent table is; the per-inline schema does not carry a
            # translatable flag, so we conservatively treat their
            # presence (with table.translatable True) as translatable
            # content.
            return True
    return False


def _filter_translatable_rows(rows: list[TableRowBlock]) -> list[TableRowBlock]:
    """Drop rows where every cell is ``translatable=False``."""
    return [r for r in rows if not _all_cells_non_translatable(r)]


_QA_ID_SUFFIX_BY_CODE: dict[str, str] = {
    "TABLE_PARITY_MISSING_RU_TABLE": "missing",
    "TABLE_PARITY_ROW_COUNT_MISMATCH": "row_count",
    "TABLE_PARITY_CELL_COUNT_MISMATCH": "cell_count",
    "TABLE_PARITY_HEADER_FLAG_DRIFT": "header_drift",
}


def _record(
    *,
    page_id: str,
    document_id: str,
    code: str,
    entity_ref: str,
    message: str,
    expected: object | None = None,
    actual: object | None = None,
) -> QARecordV1:
    """Construct a ``QARecordV1`` with the rule's fixed layer/severity.

    ``qa_id`` is derived deterministically from ``page_id`` + a per-code
    suffix + ``entity_ref`` so callers don't have to thread the ``qa_id``
    string through every emit site.
    """
    suffix = _QA_ID_SUFFIX_BY_CODE.get(code, code.lower())
    return QARecordV1(
        qa_id=f"qa.{page_id}.table_parity.{suffix}.{entity_ref}",
        layer=QALayer.STRUCTURE,
        severity=Severity.ERROR,
        code=code,
        document_id=document_id,
        page_id=page_id,
        entity_ref=entity_ref,
        message=message,
        expected=expected,
        actual=actual,
    )


def _check_cell_parity(
    *,
    en_row: TableRowBlock,
    ru_row: TableRowBlock,
    document_id: str,
    page_id: str,
) -> list[QARecordV1]:
    """Compare cell count and per-cell header flags inside a paired row."""
    out: list[QARecordV1] = []
    en_count = len(en_row.cells)
    ru_count = len(ru_row.cells)
    if en_count != ru_count:
        out.append(
            _record(
                page_id=page_id,
                document_id=document_id,
                code="TABLE_PARITY_CELL_COUNT_MISMATCH",
                entity_ref=en_row.block_id,
                message=(
                    f"Row {en_row.block_id} has {en_count} cells in EN but {ru_count} cells in RU."
                ),
                expected={"cells": en_count},
                actual={"cells": ru_count},
            )
        )
        # Don't dive into per-cell flag checks when the counts disagree;
        # the zip would silently truncate and emit misleading findings.
        return out

    for en_cell, ru_cell in zip(en_row.cells, ru_row.cells, strict=False):
        if en_cell.header != ru_cell.header:
            out.append(_header_drift(en_cell, ru_cell, document_id, page_id))
    return out


def _header_drift(
    en_cell: TableCellBlock,
    ru_cell: TableCellBlock,
    document_id: str,
    page_id: str,
) -> QARecordV1:
    return _record(
        page_id=page_id,
        document_id=document_id,
        code="TABLE_PARITY_HEADER_FLAG_DRIFT",
        entity_ref=en_cell.block_id,
        message=(
            f"Cell {en_cell.block_id} header flag drift: EN={en_cell.header}, RU={ru_cell.header}."
        ),
        expected={"header": en_cell.header},
        actual={"header": ru_cell.header},
    )


def _check_row_parity(
    *,
    en_table: TableBlock,
    ru_table: TableBlock,
    document_id: str,
    page_id: str,
) -> list[QARecordV1]:
    """Compare row counts (translatable subset), header flags, and dive
    into cell-level parity for paired rows."""
    out: list[QARecordV1] = []
    en_rows_all = _structured_rows(en_table)
    ru_rows_all = _structured_rows(ru_table)
    en_rows = _filter_translatable_rows(en_rows_all)
    ru_rows = _filter_translatable_rows(ru_rows_all)

    if len(en_rows) != len(ru_rows):
        out.append(
            _record(
                page_id=page_id,
                document_id=document_id,
                code="TABLE_PARITY_ROW_COUNT_MISMATCH",
                entity_ref=en_table.block_id,
                message=(
                    f"Table {en_table.block_id} has {len(en_rows)} translatable rows "
                    f"in EN but {len(ru_rows)} translatable rows in RU "
                    f"(EN total={len(en_rows_all)}, RU total={len(ru_rows_all)})."
                ),
                expected={"rows": len(en_rows)},
                actual={"rows": len(ru_rows)},
            )
        )
        # Counts disagree — diving into per-row pairing is not meaningful;
        # the misalignment would emit a flood of secondary findings.
        return out

    for en_row, ru_row in zip(en_rows, ru_rows, strict=False):
        if en_row.header != ru_row.header:
            out.append(
                _record(
                    page_id=page_id,
                    document_id=document_id,
                    code="TABLE_PARITY_HEADER_FLAG_DRIFT",
                    entity_ref=en_row.block_id,
                    message=(
                        f"Row {en_row.block_id} header flag drift: "
                        f"EN={en_row.header}, RU={ru_row.header}."
                    ),
                    expected={"header": en_row.header},
                    actual={"header": ru_row.header},
                )
            )
        out.extend(
            _check_cell_parity(
                en_row=en_row,
                ru_row=ru_row,
                document_id=document_id,
                page_id=page_id,
            )
        )
    return out


def evaluate_table_structure_parity(
    source_ir: PageIRV1,
    target_ir: PageIRV1,
) -> list[QARecordV1]:
    """Assert EN<->RU structural parity for every ``TableBlock`` on the page.

    Pairs are matched by ``block_id``.  An EN table with no translatable
    content is allowed to have no RU counterpart (skip-case for tables
    where every cell is ``translatable=False``).  Cell-level dives are
    skipped when the parent count differs to keep the noise floor low
    on a misaligned table.
    """
    records: list[QARecordV1] = []
    if source_ir.page_id != target_ir.page_id:
        # Defensive — the QA stage feeds matched (en, ru) pairs by page_id;
        # a mismatch here is a bug upstream and not the concern of this rule.
        return records

    page_id = source_ir.page_id
    document_id = source_ir.document_id
    en_tables = _index_tables(source_ir)
    ru_tables = _index_tables(target_ir)

    for block_id, en_table in en_tables.items():
        ru_table = ru_tables.get(block_id)
        if ru_table is None:
            if _has_any_translatable_content(en_table):
                records.append(
                    _record(
                        page_id=page_id,
                        document_id=document_id,
                        code="TABLE_PARITY_MISSING_RU_TABLE",
                        entity_ref=block_id,
                        message=(
                            f"EN TableBlock {block_id} has translatable content but "
                            "no corresponding RU TableBlock at the same block_id."
                        ),
                        expected={"present": True},
                        actual={"present": False},
                    )
                )
            # Skip-case: EN table is fully non-translatable; no RU counterpart
            # is allowed by design.
            continue

        records.extend(
            _check_row_parity(
                en_table=en_table,
                ru_table=ru_table,
                document_id=document_id,
                page_id=page_id,
            )
        )
    return records
