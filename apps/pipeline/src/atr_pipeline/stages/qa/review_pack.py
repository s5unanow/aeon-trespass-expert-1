"""Review-pack generation for QA findings that require human inspection."""

from __future__ import annotations

from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.review_pack_v1 import ReviewFinding, ReviewPackV1
from atr_schemas.waiver_v1 import WaiverV1


def build_review_pack(
    *,
    document_id: str,
    run_id: str,
    records: list[QARecordV1],
    block_on: set[str],
) -> ReviewPackV1:
    """Build a review pack from QA records.

    Includes all unwaived blocking findings with pre-filled waiver
    templates that a human reviewer can approve.
    """
    total = len(records)
    waived = sum(1 for r in records if r.waived)
    blocking_records = [r for r in records if r.severity.value in block_on and not r.waived]

    findings = [
        ReviewFinding(
            record=r,
            waiver_template=_make_waiver_template(r),
        )
        for r in blocking_records
    ]

    return ReviewPackV1(
        document_id=document_id,
        run_id=run_id,
        total_findings=total,
        blocking_findings=len(blocking_records),
        waived_findings=waived,
        findings=findings,
    )


def _make_waiver_template(record: QARecordV1) -> WaiverV1:
    """Create a pre-filled waiver template for a QA record."""
    return WaiverV1(
        waiver_id=f"waiver.{record.qa_id}",
        code=record.code,
        page_id=record.page_id,
        reason="",
        approved_by="",
    )
