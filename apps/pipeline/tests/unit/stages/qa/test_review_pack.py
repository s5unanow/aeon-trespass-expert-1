"""Tests for review-pack generation."""

from __future__ import annotations

from atr_pipeline.stages.qa.review_pack import build_review_pack
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1


def _record(
    code: str,
    severity: Severity = Severity.ERROR,
    page_id: str = "p0001",
    waived: bool = False,
    layer: QALayer = QALayer.RENDER,
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{page_id}.{code}",
        layer=layer,
        severity=severity,
        code=code,
        document_id="test",
        page_id=page_id,
        message=f"Test {code}",
        waived=waived,
        waiver_ref="w1" if waived else None,
    )


class TestBuildReviewPack:
    def test_empty_records(self) -> None:
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=[],
            block_on={"error", "critical"},
        )
        assert pack.total_findings == 0
        assert pack.blocking_findings == 0
        assert pack.findings == []

    def test_blocking_findings_included(self) -> None:
        records = [
            _record("LEAKED_TECHNICAL_ID", severity=Severity.ERROR),
            _record("PARAGRAPH_TOO_LONG", severity=Severity.WARNING),
        ]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        assert pack.total_findings == 2
        assert pack.blocking_findings == 1
        assert len(pack.findings) == 1
        assert pack.findings[0].record.code == "LEAKED_TECHNICAL_ID"

    def test_waived_findings_excluded_from_blocking(self) -> None:
        records = [
            _record("LEAKED_TECHNICAL_ID", severity=Severity.ERROR, waived=True),
            _record("UNTRANSLATED_TEXT", severity=Severity.ERROR),
        ]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        assert pack.blocking_findings == 1
        assert pack.waived_findings == 1
        assert pack.findings[0].record.code == "UNTRANSLATED_TEXT"

    def test_waiver_templates_pre_filled(self) -> None:
        records = [_record("LEAKED_TECHNICAL_ID", severity=Severity.ERROR)]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        template = pack.findings[0].waiver_template
        assert template.code == "LEAKED_TECHNICAL_ID"
        assert template.page_id == "p0001"
        assert template.waiver_id.startswith("waiver.")

    def test_run_id_propagated(self) -> None:
        pack = build_review_pack(
            document_id="doc1",
            run_id="test-run-123",
            records=[],
            block_on={"error"},
        )
        assert pack.run_id == "test-run-123"

    def test_qa_required_confidence_findings_included(self) -> None:
        """Confidence-band qa_required findings surface even though warning
        severity is not in block_on (S5U-588)."""
        records = [
            _record(
                "CONFIDENCE_QA_REQUIRED",
                severity=Severity.WARNING,
                layer=QALayer.CONFIDENCE,
            ),
        ]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        assert pack.blocking_findings == 0
        assert len(pack.findings) == 1
        assert pack.findings[0].record.code == "CONFIDENCE_QA_REQUIRED"

    def test_qa_required_waived_excluded(self) -> None:
        records = [
            _record(
                "CONFIDENCE_QA_REQUIRED",
                severity=Severity.WARNING,
                layer=QALayer.CONFIDENCE,
                waived=True,
            ),
        ]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        assert pack.findings == []

    def test_confidence_hard_route_not_in_pack(self) -> None:
        """Hard-route band records are informational; they do not enter the pack."""
        records = [
            _record(
                "CONFIDENCE_HARD_ROUTE",
                severity=Severity.INFO,
                layer=QALayer.CONFIDENCE,
            ),
        ]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        assert pack.findings == []

    def test_publish_blocking_goes_through_severity_gate(self) -> None:
        """Critical-severity confidence records land in the pack via the
        normal block_on path — not double-counted as qa_required."""
        records = [
            _record(
                "CONFIDENCE_PUBLISH_BLOCKING",
                severity=Severity.CRITICAL,
                layer=QALayer.CONFIDENCE,
            ),
        ]
        pack = build_review_pack(
            document_id="doc1",
            run_id="run1",
            records=records,
            block_on={"error", "critical"},
        )
        assert pack.blocking_findings == 1
        assert len(pack.findings) == 1
        assert pack.findings[0].record.code == "CONFIDENCE_PUBLISH_BLOCKING"
