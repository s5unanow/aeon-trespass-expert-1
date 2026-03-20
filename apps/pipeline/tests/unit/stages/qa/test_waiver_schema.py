"""Tests for waiver and review-pack schema models."""

from __future__ import annotations

from atr_schemas.review_pack_v1 import ReviewFinding, ReviewPackV1
from atr_schemas.waiver_v1 import WaiverSetV1, WaiverV1


class TestWaiverV1:
    def test_basic_waiver(self) -> None:
        w = WaiverV1(
            waiver_id="w1",
            code="LEAKED_TECHNICAL_ID",
            reason="Known false positive",
            approved_by="reviewer@example.com",
        )
        assert w.waiver_id == "w1"
        assert w.page_id is None

    def test_page_specific_waiver(self) -> None:
        w = WaiverV1(
            waiver_id="w2",
            code="PARAGRAPH_TOO_LONG",
            page_id="p0042",
            reason="Intentional long paragraph",
            approved_by="reviewer@example.com",
        )
        assert w.page_id == "p0042"

    def test_roundtrip(self) -> None:
        w = WaiverV1(
            waiver_id="w1",
            code="X",
            reason="test",
            approved_by="a",
            approved_at="2026-03-20T00:00:00Z",
        )
        data = w.model_dump()
        w2 = WaiverV1.model_validate(data)
        assert w == w2


class TestWaiverSetV1:
    def test_empty_set(self) -> None:
        ws = WaiverSetV1(document_id="doc1")
        assert ws.waivers == []
        assert ws.schema_version == "waiver_set.v1"

    def test_set_with_waivers(self) -> None:
        ws = WaiverSetV1(
            document_id="doc1",
            waivers=[
                WaiverV1(waiver_id="w1", code="X", reason="r", approved_by="a"),
            ],
        )
        assert len(ws.waivers) == 1


class TestReviewPackV1:
    def test_empty_pack(self) -> None:
        pack = ReviewPackV1(document_id="doc1")
        assert pack.findings == []
        assert pack.schema_version == "review_pack.v1"

    def test_roundtrip(self) -> None:
        from atr_schemas.enums import QALayer, Severity
        from atr_schemas.qa_record_v1 import QARecordV1

        record = QARecordV1(
            qa_id="qa.p0001.TEST",
            layer=QALayer.RENDER,
            severity=Severity.ERROR,
            code="TEST",
        )
        template = WaiverV1(
            waiver_id="waiver.qa.p0001.TEST",
            code="TEST",
            reason="",
            approved_by="",
        )
        pack = ReviewPackV1(
            document_id="doc1",
            run_id="run1",
            total_findings=1,
            blocking_findings=1,
            findings=[ReviewFinding(record=record, waiver_template=template)],
        )
        data = pack.model_dump()
        pack2 = ReviewPackV1.model_validate(data)
        assert pack2.blocking_findings == 1
        assert len(pack2.findings) == 1
