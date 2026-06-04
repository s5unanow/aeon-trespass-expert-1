"""Tests for the shared blocking-QA release gate (S5U-870).

The gate is a fail-closed safety gate (`.claude/rules/guards.md` Rule G1): it
refuses by default and treats degenerate inputs (no QA summary; blocking
summary whose records can't be loaded) as refusals, never "pass by absent
state". Waiver semantics (`not r.waived`) and the `block_on` config are
preserved. The single escape hatch is the explicit `review_only` flag.

Red-before: branch base 2b078bc — `qa_gate.py` does not exist there, so every
test below errors at import/collection on the pre-fix tree.
"""

from __future__ import annotations

import pytest

from atr_pipeline.stages.publish.qa_gate import (
    QAGateError,
    QAGateResult,
    evaluate_qa_gate,
)
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1

BLOCK_ON = {"error", "critical"}


def _record(
    *,
    code: str = "SOME_CODE",
    severity: Severity = Severity.ERROR,
    page_id: str | None = "p0001",
    waived: bool = False,
) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{code}.{page_id}",
        layer=QALayer.STRUCTURE,
        severity=severity,
        code=code,
        page_id=page_id,
        waived=waived,
    )


def _summary(*, blocking: bool, review_pack_ref: str = "", run_id: str = "run_x") -> QASummaryV1:
    return QASummaryV1(
        document_id="doc1",
        run_id=run_id,
        blocking=blocking,
        review_pack_ref=review_pack_ref,
    )


class TestAllow:
    def test_non_blocking_summary_allows(self) -> None:
        result = evaluate_qa_gate(
            context="Publish",
            summary=_summary(blocking=False, review_pack_ref="rp/ref.json"),
            records=[],
            block_on=BLOCK_ON,
            review_only=False,
        )
        assert isinstance(result, QAGateResult)
        assert result.blocking is False
        assert result.is_draft is False
        assert result.review_pack_ref == "rp/ref.json"

    def test_non_blocking_with_review_only_still_not_draft(self) -> None:
        """review_only on a non-blocking run does not mark a draft."""
        result = evaluate_qa_gate(
            context="Export",
            summary=_summary(blocking=False),
            records=[],
            block_on=BLOCK_ON,
            review_only=True,
        )
        assert result.is_draft is False
        assert result.blocking is False


class TestRefuse:
    def test_blocking_refuses_by_default(self) -> None:
        records = [_record(code="GLUED_TEXT", page_id="p0007", severity=Severity.ERROR)]
        with pytest.raises(QAGateError) as exc:
            evaluate_qa_gate(
                context="Publish",
                summary=_summary(blocking=True),
                records=records,
                block_on=BLOCK_ON,
                review_only=False,
            )
        msg = str(exc.value)
        assert "GLUED_TEXT" in msg
        assert "p0007" in msg
        assert "review-only" in msg.lower()

    def test_blocking_refusal_names_multiple_codes_and_pages(self) -> None:
        records = [
            _record(code="CODE_A", page_id="p0001", severity=Severity.ERROR),
            _record(code="CODE_B", page_id="p0002", severity=Severity.CRITICAL),
        ]
        with pytest.raises(QAGateError) as exc:
            evaluate_qa_gate(
                context="Export",
                summary=_summary(blocking=True),
                records=records,
                block_on=BLOCK_ON,
                review_only=False,
            )
        msg = str(exc.value)
        assert "CODE_A" in msg and "CODE_B" in msg
        assert "p0001" in msg and "p0002" in msg


class TestReviewOnlyEscapeHatch:
    def test_blocking_with_review_only_produces_draft(self) -> None:
        records = [_record(code="DEAD_REF", page_id="p0003", severity=Severity.CRITICAL)]
        result = evaluate_qa_gate(
            context="Publish",
            summary=_summary(blocking=True, review_pack_ref="rp/pack.json"),
            records=records,
            block_on=BLOCK_ON,
            review_only=True,
        )
        assert result.is_draft is True
        assert result.blocking is True
        assert result.review_only is True
        assert result.blocking_codes == ["DEAD_REF"]
        assert result.blocking_pages == ["p0003"]
        assert result.review_pack_ref == "rp/pack.json"


class TestWaiverSemantics:
    def test_waived_blocking_severity_record_not_named(self) -> None:
        """A waived error record must not appear in the named blocking codes.

        ``summary.blocking`` would be False in production for an all-waived run,
        but we pass blocking=True here to prove the per-record predicate also
        honors ``not r.waived`` when naming codes/pages.
        """
        records = [
            _record(code="WAIVED_ONE", page_id="p0009", severity=Severity.ERROR, waived=True),
            _record(code="LIVE_ONE", page_id="p0010", severity=Severity.ERROR, waived=False),
        ]
        with pytest.raises(QAGateError) as exc:
            evaluate_qa_gate(
                context="Publish",
                summary=_summary(blocking=True),
                records=records,
                block_on=BLOCK_ON,
                review_only=False,
            )
        msg = str(exc.value)
        assert "LIVE_ONE" in msg
        assert "WAIVED_ONE" not in msg

    def test_below_block_on_severity_not_named(self) -> None:
        """A warning record (below block_on) is not named as blocking."""
        records = [
            _record(code="WARN_ONLY", page_id="p0011", severity=Severity.WARNING),
            _record(code="ERR_ONE", page_id="p0012", severity=Severity.ERROR),
        ]
        with pytest.raises(QAGateError) as exc:
            evaluate_qa_gate(
                context="Export",
                summary=_summary(blocking=True),
                records=records,
                block_on=BLOCK_ON,
                review_only=False,
            )
        msg = str(exc.value)
        assert "ERR_ONE" in msg
        assert "WARN_ONLY" not in msg

    def test_empty_block_on_config_honored(self) -> None:
        """With block_on empty, an error record yields no named blocking codes.

        This documents that the gate honors the (mis)config rather than
        hardcoding error/critical — naming is config-driven.
        """
        records = [_record(code="ERR_ONE", page_id="p0013", severity=Severity.ERROR)]
        with pytest.raises(QAGateError) as exc:
            evaluate_qa_gate(
                context="Export",
                summary=_summary(blocking=True),
                records=records,
                block_on=set(),
                review_only=False,
            )
        # No code matches an empty block_on → degraded "records missing" message.
        assert "ERR_ONE" not in str(exc.value)


class TestFailClosed:
    def test_missing_summary_refuses_even_without_review_only(self) -> None:
        """G1: no resolvable QA summary → refuse, do not pass by absent state."""
        with pytest.raises(QAGateError, match="no QA summary"):
            evaluate_qa_gate(
                context="Publish",
                summary=None,
                records=[],
                block_on=BLOCK_ON,
                review_only=False,
                run_id="run_missing",
            )

    def test_missing_summary_refuses_even_with_review_only(self) -> None:
        """review_only does not rescue an unverifiable run — still refuses."""
        with pytest.raises(QAGateError, match="no QA summary"):
            evaluate_qa_gate(
                context="Export",
                summary=None,
                records=[],
                block_on=BLOCK_ON,
                review_only=True,
                run_id="run_missing",
            )

    def test_blocking_summary_with_no_loadable_records_still_refuses(self) -> None:
        """G1: blocking=True but records empty → refuse, naming the degraded state."""
        with pytest.raises(QAGateError, match="record artifacts missing"):
            evaluate_qa_gate(
                context="Publish",
                summary=_summary(blocking=True),
                records=[],
                block_on=BLOCK_ON,
                review_only=False,
            )
