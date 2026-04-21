"""QA rule: surface page-confidence band actions as QA records.

Unlike the rules in ``registry.py``, this rule requires a loaded policy and is
invoked directly from ``QAStage.run`` rather than through ``get_all_rules()`` —
the registry's ``QAPageContext`` does not carry the policy, and policy loading
is a stage-level concern.
"""

from __future__ import annotations

from atr_pipeline.eval.confidence_policy import (
    BandAction,
    ConfidenceBandPolicy,
    evaluate_page_confidence,
)
from atr_schemas.enums import QALayer, Severity
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1

CODE_HARD_ROUTE = "CONFIDENCE_HARD_ROUTE"
CODE_QA_REQUIRED = "CONFIDENCE_QA_REQUIRED"
CODE_PUBLISH_BLOCKING = "CONFIDENCE_PUBLISH_BLOCKING"

_ACTION_SEVERITY: dict[BandAction, Severity] = {
    BandAction.HARD_ROUTE: Severity.INFO,
    BandAction.QA_REQUIRED: Severity.WARNING,
    BandAction.PUBLISH_BLOCKING: Severity.CRITICAL,
}

_ACTION_CODE: dict[BandAction, str] = {
    BandAction.HARD_ROUTE: CODE_HARD_ROUTE,
    BandAction.QA_REQUIRED: CODE_QA_REQUIRED,
    BandAction.PUBLISH_BLOCKING: CODE_PUBLISH_BLOCKING,
}


def evaluate_confidence_band(
    page_ir: PageIRV1,
    policy: ConfidenceBandPolicy,
) -> list[QARecordV1]:
    """Emit a QA record when the page's confidence falls outside the primary band.

    Pages without a ``confidence`` block are skipped — the scorer populates it in
    the Structure stage, so missing values mean the page bypassed structure and
    cannot be routed by this policy.
    """
    if page_ir.confidence is None:
        return []

    result = evaluate_page_confidence(
        page_id=page_ir.page_id,
        confidence=page_ir.confidence.page_confidence,
        policy=policy,
    )
    if result.action is BandAction.PRIMARY:
        return []

    severity = _ACTION_SEVERITY[result.action]
    code = _ACTION_CODE[result.action]
    message = (
        f"Page confidence {result.confidence:.3f} in band '{result.band_name}' "
        f"→ action={result.action.value}"
    )
    return [
        QARecordV1(
            qa_id=f"qa.{page_ir.page_id}.confidence.{result.action.value}",
            layer=QALayer.CONFIDENCE,
            severity=severity,
            code=code,
            document_id=page_ir.document_id,
            page_id=page_ir.page_id,
            message=message,
            expected=f"band=primary (>= {_primary_min(policy):.2f})",
            actual={
                "page_confidence": result.confidence,
                "band": result.band_name,
                "action": result.action.value,
            },
        )
    ]


def _primary_min(policy: ConfidenceBandPolicy) -> float:
    """Return the lower bound of the primary band, or 1.0 if undefined."""
    for band in policy.bands:
        if band.action is BandAction.PRIMARY:
            return band.min_confidence
    return 1.0
