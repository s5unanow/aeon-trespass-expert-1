"""Tests for ``stages/qa/metrics.py`` (S5U-597).

``compute_qa_metrics`` is O(records) aggregation. Coverage:

- Empty record set on a document with pages → all-zero metrics,
  clean_page_rate = 1.0, avg_findings_per_page = 0.0.
- ``pages_total == 0`` edge case → both ratios stay 0.0 (no divide-by-zero).
- Waived records flow only into ``waived_count`` and are excluded from
  distribution tallies.
- ``blocking_count`` matches active records whose severity is in ``block_on``.
- ``findings_by_code_top10`` truncates to 10 entries, desc by count.
- Records whose ``page_id`` is not in the iterated page set still
  contribute to distributions but don't inflate ``pages_with_findings``.
"""

from __future__ import annotations

from atr_pipeline.stages.qa.metrics import compute_qa_metrics, format_metrics_digest
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1


def _make_record(
    *,
    code: str = "X",
    layer: QALayer = QALayer.STRUCTURE,
    severity: Severity = Severity.WARNING,
    page_id: str | None = "p0001",
    waived: bool = False,
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{page_id}.{code}",
        layer=layer,
        severity=severity,
        code=code,
        page_id=page_id,
        waived=waived,
    )


def test_compute_metrics_empty_records_clean_pages() -> None:
    """Zero records over N pages -> clean_page_rate == 1.0."""
    m = compute_qa_metrics(
        document_id="doc",
        run_id="run1",
        edition="ru",
        page_ids=["p0001", "p0002", "p0003"],
        records=[],
        block_on={"error", "critical"},
    )
    assert m.pages_total == 3
    assert m.pages_with_findings == 0
    assert m.clean_page_rate == 1.0
    assert m.avg_findings_per_page == 0.0
    assert m.waived_count == 0
    assert m.blocking_count == 0
    assert m.findings_by_layer == {}
    assert m.findings_by_code_top10 == []


def test_compute_metrics_zero_pages_no_divide_by_zero() -> None:
    """pages_total == 0 -> ratios stay 0.0 instead of raising."""
    m = compute_qa_metrics(
        document_id="doc",
        run_id="",
        edition="",
        page_ids=[],
        records=[],
        block_on={"error", "critical"},
    )
    assert m.pages_total == 0
    assert m.clean_page_rate == 0.0
    assert m.avg_findings_per_page == 0.0


def test_compute_metrics_counts_severity_and_layer() -> None:
    """Active records flow into severity + layer + blocking tallies."""
    records = [
        _make_record(code="A", severity=Severity.WARNING, layer=QALayer.STRUCTURE),
        _make_record(code="A", severity=Severity.WARNING, layer=QALayer.STRUCTURE),
        _make_record(code="B", severity=Severity.ERROR, layer=QALayer.TERMINOLOGY),
        _make_record(code="C", severity=Severity.CRITICAL, layer=QALayer.EXTRACTION),
        _make_record(code="D", severity=Severity.INFO, layer=QALayer.USER_FEEDBACK),
    ]
    m = compute_qa_metrics(
        document_id="doc",
        run_id="run1",
        edition="en",
        page_ids=["p0001"],
        records=records,
        block_on={"error", "critical"},
    )
    assert m.findings_by_severity.info == 1
    assert m.findings_by_severity.warning == 2
    assert m.findings_by_severity.error == 1
    assert m.findings_by_severity.critical == 1
    assert m.findings_by_layer == {
        "structure": 2,
        "terminology": 1,
        "extraction": 1,
        "user_feedback": 1,
    }
    assert m.blocking_count == 2  # error + critical
    assert m.avg_findings_per_page == 5.0


def test_compute_metrics_waived_excluded_from_distributions() -> None:
    """Waived records only bump waived_count; never distribution fields."""
    records = [
        _make_record(code="A", severity=Severity.ERROR, waived=True),
        _make_record(code="A", severity=Severity.ERROR, waived=True),
        _make_record(code="B", severity=Severity.WARNING, waived=False),
    ]
    m = compute_qa_metrics(
        document_id="doc",
        run_id="",
        edition="",
        page_ids=["p0001"],
        records=records,
        block_on={"error", "critical"},
    )
    assert m.waived_count == 2
    assert m.blocking_count == 0  # the two blocking-severity records are waived
    assert m.findings_by_severity.warning == 1
    assert m.findings_by_severity.error == 0
    assert m.findings_by_layer == {"structure": 1}


def test_compute_metrics_top10_truncation() -> None:
    """More than 10 distinct codes -> top10 truncated, desc-count ordered."""
    records: list[QARecordV1] = []
    # Seed 12 codes with decreasing counts (C01: 12 records, C12: 1 record).
    for i in range(12):
        code = f"C{i:02d}"
        for _ in range(12 - i):
            records.append(_make_record(code=code, severity=Severity.WARNING))
    m = compute_qa_metrics(
        document_id="doc",
        run_id="",
        edition="",
        page_ids=["p0001"],
        records=records,
        block_on=set(),
    )
    assert len(m.findings_by_code_top10) == 10
    # top entry is the most common
    assert m.findings_by_code_top10[0].code == "C00"
    assert m.findings_by_code_top10[0].count == 12
    # truncated out of view
    codes_in_top = {entry.code for entry in m.findings_by_code_top10}
    assert "C10" not in codes_in_top
    assert "C11" not in codes_in_top
    # desc ordering
    counts = [e.count for e in m.findings_by_code_top10]
    assert counts == sorted(counts, reverse=True)


def test_compute_metrics_pages_with_findings_bounded_by_page_set() -> None:
    """Records with page_id outside the iterated page set don't inflate the coverage count."""
    records = [
        _make_record(code="A", page_id="p0001", severity=Severity.WARNING),
        _make_record(code="A", page_id="p0099", severity=Severity.WARNING),  # stray
    ]
    m = compute_qa_metrics(
        document_id="doc",
        run_id="",
        edition="",
        page_ids=["p0001", "p0002"],
        records=records,
        block_on=set(),
    )
    # Only p0001 counts toward pages_with_findings (p0099 isn't in the set).
    assert m.pages_with_findings == 1
    assert m.clean_page_rate == 0.5
    # But the record still contributes to distribution tallies.
    assert m.findings_by_severity.warning == 2


def test_format_metrics_digest_includes_key_fields() -> None:
    """Digest must include pages/clean_rate/avg/severity/blocking/waived."""
    m = compute_qa_metrics(
        document_id="doc",
        run_id="",
        edition="",
        page_ids=["p0001", "p0002"],
        records=[_make_record(code="A", severity=Severity.ERROR)],
        block_on={"error", "critical"},
    )
    digest = format_metrics_digest(m)
    assert "pages=2" in digest
    assert "clean_rate=" in digest
    assert "avg=" in digest
    assert "error=1" in digest
    assert "blocking=1" in digest
    assert "waived=0" in digest
