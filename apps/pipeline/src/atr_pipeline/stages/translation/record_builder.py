"""Shared QA-record construction helpers for the translation validator.

Extracted from ``validator.py`` (S5U-871) so the validator and the
segment-coverage check can share record construction without a module import
cycle and without pushing ``validator.py`` past the 400-line ceiling.
"""

from __future__ import annotations

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1

_SEVERITY_LOOKUP: dict[str, Severity] = {
    "info": Severity.INFO,
    "warning": Severity.WARNING,
    "error": Severity.ERROR,
    "critical": Severity.CRITICAL,
}


def coerce_severity(raw: str, default: Severity = Severity.WARNING) -> Severity:
    """Map a validation-policy severity string onto a ``Severity`` enum."""
    return _SEVERITY_LOOKUP.get(raw.strip().lower(), default)


def normalize_segment_id(segment_id: str) -> str:
    """Canonical key for matching requested vs returned segment ids.

    The request side builds ``segment_id`` from internal ``block_id`` values
    (or synthesized ``group.<page>.<n>`` group ids) that never carry leading or
    trailing whitespace by construction. To stay robust against a model echoing
    a padded id back (``"  blk_002  "``), matching strips surrounding
    whitespace. Block ids are case-sensitive identifiers, so case is **not**
    folded — lowercasing would risk false collisions between distinct ids.
    """
    return segment_id.strip()


class RecordContext:
    """Document/page coordinates reused by every finding on a page."""

    __slots__ = ("document_id", "page_id")

    def __init__(self, document_id: str, page_id: str | None) -> None:
        self.document_id = document_id
        self.page_id = page_id


def make_record(
    rec_ctx: RecordContext,
    *,
    qa_id: str,
    code: str,
    severity: Severity,
    entity_ref: str | None,
    message: str,
    values: tuple[object, object] = (None, None),
) -> QARecordV1:
    """Construct a ``QARecordV1`` with the translation validator defaults.

    ``values`` is an ``(expected, actual)`` tuple, collapsed into a single
    keyword argument to keep the parameter count small.
    """
    expected, actual = values
    return QARecordV1(
        qa_id=qa_id,
        layer=QALayer.TERMINOLOGY,
        severity=severity,
        code=code,
        document_id=rec_ctx.document_id,
        page_id=rec_ctx.page_id,
        entity_ref=entity_ref,
        message=message,
        expected=expected,
        actual=actual,
    )


def qa_id(page_id: str | None, segment_id: str, suffix: str) -> str:
    """Build a stable ``qa_id`` for a translation finding."""
    page_part = page_id or "doc"
    return f"qa.{page_part}.translation.{segment_id}.{suffix}"
