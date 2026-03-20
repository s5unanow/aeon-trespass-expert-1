"""Tests for QA waiver loading and matching."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.waiver_v1 import WaiverSetV1, WaiverV1


def _record(
    code: str,
    severity: Severity = Severity.ERROR,
    page_id: str = "p0001",
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{page_id}.{code}",
        layer=QALayer.RENDER,
        severity=severity,
        code=code,
        document_id="test",
        page_id=page_id,
        message=f"Test {code}",
    )


def _waiver(
    code: str,
    page_id: str | None = None,
    waiver_id: str = "w1",
) -> WaiverV1:
    return WaiverV1(
        waiver_id=waiver_id,
        code=code,
        page_id=page_id,
        reason="Approved by reviewer",
        approved_by="test@example.com",
    )


class TestApplyWaivers:
    def test_no_waivers_returns_unchanged(self) -> None:
        records = [_record("LEAKED_TECHNICAL_ID")]
        result = apply_waivers(records, [])
        assert len(result) == 1
        assert result[0].waived is False

    def test_matching_code_waives_record(self) -> None:
        records = [_record("LEAKED_TECHNICAL_ID")]
        waivers = [_waiver("LEAKED_TECHNICAL_ID")]
        result = apply_waivers(records, waivers)
        assert result[0].waived is True
        assert result[0].waiver_ref == "w1"

    def test_non_matching_code_leaves_unwaived(self) -> None:
        records = [_record("UNTRANSLATED_TEXT")]
        waivers = [_waiver("LEAKED_TECHNICAL_ID")]
        result = apply_waivers(records, waivers)
        assert result[0].waived is False

    def test_page_specific_waiver_matches_correct_page(self) -> None:
        records = [
            _record("LEAKED_TECHNICAL_ID", page_id="p0001"),
            _record("LEAKED_TECHNICAL_ID", page_id="p0002"),
        ]
        waivers = [_waiver("LEAKED_TECHNICAL_ID", page_id="p0001")]
        result = apply_waivers(records, waivers)
        assert result[0].waived is True
        assert result[1].waived is False

    def test_global_waiver_matches_all_pages(self) -> None:
        records = [
            _record("LEAKED_TECHNICAL_ID", page_id="p0001"),
            _record("LEAKED_TECHNICAL_ID", page_id="p0002"),
        ]
        waivers = [_waiver("LEAKED_TECHNICAL_ID", page_id=None)]
        result = apply_waivers(records, waivers)
        assert all(r.waived for r in result)

    def test_multiple_waivers_for_different_codes(self) -> None:
        records = [
            _record("LEAKED_TECHNICAL_ID"),
            _record("UNTRANSLATED_TEXT"),
            _record("PARAGRAPH_TOO_LONG", severity=Severity.WARNING),
        ]
        waivers = [
            _waiver("LEAKED_TECHNICAL_ID", waiver_id="w1"),
            _waiver("UNTRANSLATED_TEXT", waiver_id="w2"),
        ]
        result = apply_waivers(records, waivers)
        assert result[0].waived is True
        assert result[0].waiver_ref == "w1"
        assert result[1].waived is True
        assert result[1].waiver_ref == "w2"
        assert result[2].waived is False


class TestLoadWaivers:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_waivers(tmp_path, "nonexistent")
        assert result == []

    def test_loads_waivers_from_json(self, tmp_path: Path) -> None:
        waiver_set = WaiverSetV1(
            document_id="test_doc",
            waivers=[_waiver("LEAKED_TECHNICAL_ID")],
        )
        waiver_file = tmp_path / "test_doc.json"
        waiver_file.write_text(
            json.dumps(waiver_set.model_dump(), indent=2),
            encoding="utf-8",
        )
        result = load_waivers(tmp_path, "test_doc")
        assert len(result) == 1
        assert result[0].code == "LEAKED_TECHNICAL_ID"
