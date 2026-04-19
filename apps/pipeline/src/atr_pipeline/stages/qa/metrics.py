"""Compute per-run QA health metrics from the record set.

The QA stage tallies severity counts into ``QASummaryV1``; this module adds
the per-layer / per-code distributions and page coverage needed to track
QA health over time. Output is a ``QAMetricsV1`` artifact that sits
alongside ``QASummaryV1`` in the run store — it never replaces the summary.

Aggregation is a single O(records) pass. No record field is mutated.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime

from atr_schemas.enums import Severity
from atr_schemas.qa_metrics_v1 import FindingCodeCount, QAMetricsV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import SeverityCounts

TOP_CODE_LIMIT = 10


def compute_qa_metrics(
    *,
    document_id: str,
    run_id: str,
    edition: str,
    page_ids: Iterable[str],
    records: Iterable[QARecordV1],
    block_on: Iterable[str],
    timestamp: str | None = None,
) -> QAMetricsV1:
    """Fold QA records into a ``QAMetricsV1`` artifact.

    Distribution fields (``findings_by_severity`` / ``findings_by_layer`` /
    ``findings_by_code_top10`` / ``blocking_count`` / ``avg_findings_per_page``)
    reflect **active** (non-waived) records only. ``waived_count`` tallies the
    rest. ``clean_page_rate`` is the fraction of iterated pages with zero
    active findings (pages outside ``page_ids`` are not counted).

    Edge cases:
    - ``pages_total == 0`` → ``clean_page_rate`` and ``avg_findings_per_page``
      both stay at ``0.0`` (no divide-by-zero).
    - Records with a ``page_id`` not in ``page_ids`` still contribute to the
      distribution tallies but do not inflate ``pages_with_findings``.
    """
    page_id_set = set(page_ids)
    pages_total = len(page_id_set)
    block_on_set = set(block_on)

    severity_counts = SeverityCounts()
    by_layer: Counter[str] = Counter()
    by_code: Counter[str] = Counter()
    pages_with_findings: set[str] = set()
    waived_count = 0
    blocking_count = 0
    active_total = 0

    for record in records:
        if record.waived:
            waived_count += 1
            continue

        active_total += 1
        _increment_severity(severity_counts, record.severity)
        by_layer[record.layer.value] += 1
        by_code[record.code] += 1
        if record.severity.value in block_on_set:
            blocking_count += 1
        if record.page_id and record.page_id in page_id_set:
            pages_with_findings.add(record.page_id)

    clean_page_rate = (
        (pages_total - len(pages_with_findings)) / pages_total if pages_total > 0 else 0.0
    )
    avg_findings_per_page = active_total / pages_total if pages_total > 0 else 0.0

    top_codes = [
        FindingCodeCount(code=code, count=count)
        for code, count in by_code.most_common(TOP_CODE_LIMIT)
    ]

    return QAMetricsV1(
        document_id=document_id,
        run_id=run_id,
        edition=edition,
        timestamp=timestamp or datetime.now(UTC).isoformat(),
        pages_total=pages_total,
        pages_with_findings=len(pages_with_findings),
        clean_page_rate=clean_page_rate,
        findings_by_severity=severity_counts,
        findings_by_layer=dict(by_layer),
        findings_by_code_top10=top_codes,
        waived_count=waived_count,
        blocking_count=blocking_count,
        avg_findings_per_page=avg_findings_per_page,
    )


def _increment_severity(counts: SeverityCounts, severity: Severity) -> None:
    if severity == Severity.INFO:
        counts.info += 1
    elif severity == Severity.WARNING:
        counts.warning += 1
    elif severity == Severity.ERROR:
        counts.error += 1
    elif severity == Severity.CRITICAL:
        counts.critical += 1


def format_metrics_digest(metrics: QAMetricsV1) -> str:
    """Render a single-line digest suitable for CI logs / CLI output."""
    sev = metrics.findings_by_severity
    return (
        f"QA metrics: pages={metrics.pages_total} "
        f"clean_rate={metrics.clean_page_rate:.3f} "
        f"avg={metrics.avg_findings_per_page:.2f}/pg "
        f"info={sev.info} warning={sev.warning} error={sev.error} "
        f"critical={sev.critical} blocking={metrics.blocking_count} "
        f"waived={metrics.waived_count}"
    )
