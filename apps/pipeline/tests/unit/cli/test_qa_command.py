"""Tests for the QA CLI command summary output."""

from __future__ import annotations

from atr_pipeline.cli.commands.qa import _print_summary
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1


def _record(
    code: str,
    severity: Severity,
    waived: bool = False,
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.p0001.test.{code}",
        layer=QALayer.RENDER,
        severity=severity,
        code=code,
        document_id="test",
        page_id="p0001",
        message=f"Test {code}",
        waived=waived,
        waiver_ref="w1" if waived else None,
    )


def test_print_summary_empty(capsys: object) -> None:
    """No records prints clean message."""
    _print_summary([])
    captured = capsys.readouterr()  # type: ignore[union-attr]
    assert "all checks clean" in captured.out


def test_print_summary_with_records(capsys: object) -> None:
    """Records produce a summary table."""
    records = [
        _record("PARAGRAPH_TOO_LONG", Severity.WARNING),
        _record("PARAGRAPH_TOO_LONG", Severity.WARNING),
        _record("LEAKED_TECHNICAL_ID", Severity.ERROR),
    ]
    _print_summary(records)
    captured = capsys.readouterr()  # type: ignore[union-attr]
    assert "PARAGRAPH_TOO_LONG" in captured.out
    assert "LEAKED_TECHNICAL_ID" in captured.out
    assert "TOTAL" in captured.out
    assert "3" in captured.out


def test_print_summary_shows_severity(capsys: object) -> None:
    """Table includes severity labels."""
    records = [_record("DEAD_PAGE_REF", Severity.WARNING)]
    _print_summary(records)
    captured = capsys.readouterr()  # type: ignore[union-attr]
    assert "warning" in captured.out


def test_print_summary_shows_waived(capsys: object) -> None:
    """Waived findings shown in separate section."""
    records = [
        _record("LEAKED_TECHNICAL_ID", Severity.ERROR, waived=True),
        _record("PARAGRAPH_TOO_LONG", Severity.WARNING),
    ]
    _print_summary(records)
    captured = capsys.readouterr()  # type: ignore[union-attr]
    assert "Waived: 1 finding(s)" in captured.out
    assert "PARAGRAPH_TOO_LONG" in captured.out


def test_print_summary_all_waived(capsys: object) -> None:
    """All findings waived shows only waiver section."""
    records = [
        _record("LEAKED_TECHNICAL_ID", Severity.ERROR, waived=True),
    ]
    _print_summary(records)
    captured = capsys.readouterr()  # type: ignore[union-attr]
    assert "Waived: 1 finding(s)" in captured.out
    assert "TOTAL" not in captured.out
