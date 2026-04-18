"""Tests for the confidence-band QA rule."""

from __future__ import annotations

import pytest

from atr_pipeline.eval.confidence_policy import (
    BandAction,
    ConfidenceBand,
    ConfidenceBandPolicy,
)
from atr_pipeline.stages.qa.rules.confidence_band_rule import evaluate_confidence_band
from atr_schemas.common import ConfidenceMetrics
from atr_schemas.enums import LanguageCode, QALayer, Severity
from atr_schemas.page_ir_v1 import PageIRV1


def _policy() -> ConfidenceBandPolicy:
    """Mirror the shipped configs/qa/confidence_bands.toml."""
    return ConfidenceBandPolicy(
        version=1,
        bands=[
            ConfidenceBand(
                name="primary",
                min_confidence=0.85,
                max_confidence=1.0,
                action=BandAction.PRIMARY,
            ),
            ConfidenceBand(
                name="hard_route",
                min_confidence=0.60,
                max_confidence=0.85,
                action=BandAction.HARD_ROUTE,
            ),
            ConfidenceBand(
                name="qa_required",
                min_confidence=0.30,
                max_confidence=0.60,
                action=BandAction.QA_REQUIRED,
            ),
            ConfidenceBand(
                name="publish_blocking",
                min_confidence=0.0,
                max_confidence=0.30,
                action=BandAction.PUBLISH_BLOCKING,
            ),
        ],
    )


def _page(confidence: float | None) -> PageIRV1:
    metrics = (
        ConfidenceMetrics(
            native_text_coverage=confidence,
            reading_order_score=confidence,
            symbol_score=confidence,
            page_confidence=confidence,
        )
        if confidence is not None
        else None
    )
    return PageIRV1(
        document_id="doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        confidence=metrics,
    )


def test_primary_band_emits_no_record() -> None:
    records = evaluate_confidence_band(_page(0.95), _policy())
    assert records == []


def test_hard_route_band_emits_info_record() -> None:
    records = evaluate_confidence_band(_page(0.70), _policy())
    assert len(records) == 1
    record = records[0]
    assert record.layer is QALayer.CONFIDENCE
    assert record.severity is Severity.INFO
    assert record.code == "CONFIDENCE_HARD_ROUTE"
    assert record.page_id == "p0001"


def test_qa_required_band_emits_warning_record() -> None:
    records = evaluate_confidence_band(_page(0.45), _policy())
    assert len(records) == 1
    record = records[0]
    assert record.severity is Severity.WARNING
    assert record.code == "CONFIDENCE_QA_REQUIRED"


def test_publish_blocking_band_emits_critical_record() -> None:
    records = evaluate_confidence_band(_page(0.10), _policy())
    assert len(records) == 1
    record = records[0]
    assert record.severity is Severity.CRITICAL
    assert record.code == "CONFIDENCE_PUBLISH_BLOCKING"


def test_missing_confidence_skipped() -> None:
    records = evaluate_confidence_band(_page(None), _policy())
    assert records == []


def test_boundary_matches_lower_band() -> None:
    """Confidence exactly on a boundary belongs to the upper band ([min, max))."""
    # 0.85 is the boundary between hard_route and primary — primary owns it.
    assert evaluate_confidence_band(_page(0.85), _policy()) == []
    # 0.30 is the boundary between publish_blocking and qa_required — qa_required owns it.
    records = evaluate_confidence_band(_page(0.30), _policy())
    assert len(records) == 1
    assert records[0].code == "CONFIDENCE_QA_REQUIRED"


def test_confidence_above_one_rejected_by_metrics() -> None:
    """``ConfidenceMetrics`` validates 0..1; values outside raise upstream."""
    with pytest.raises(ValueError):
        _page(1.5)


def test_policy_change_flips_action_for_same_page() -> None:
    """Same page + different band policy produces different QA records.

    This proves AC #1 from S5U-588: runtime behavior changes when the
    confidence-band config changes.
    """
    page = _page(0.25)

    # With the shipped policy, 0.25 falls in publish_blocking → CRITICAL.
    default_records = evaluate_confidence_band(page, _policy())
    assert len(default_records) == 1
    assert default_records[0].severity is Severity.CRITICAL
    assert default_records[0].code == "CONFIDENCE_PUBLISH_BLOCKING"

    # Loosened policy that covers [0, 0.60) with qa_required.
    loosened = ConfidenceBandPolicy(
        version=1,
        bands=[
            ConfidenceBand(
                name="primary",
                min_confidence=0.60,
                max_confidence=1.0,
                action=BandAction.PRIMARY,
            ),
            ConfidenceBand(
                name="qa_required",
                min_confidence=0.0,
                max_confidence=0.60,
                action=BandAction.QA_REQUIRED,
            ),
        ],
    )
    loosened_records = evaluate_confidence_band(page, loosened)
    assert len(loosened_records) == 1
    assert loosened_records[0].severity is Severity.WARNING
    assert loosened_records[0].code == "CONFIDENCE_QA_REQUIRED"
