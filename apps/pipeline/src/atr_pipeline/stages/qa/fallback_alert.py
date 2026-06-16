"""Run-level translation provider-fallback alert (S5U-1226).

The translate stage records ``fallback_used`` + ``primary_error`` per page in
the ``translation_meta.v1`` artifact. This module loads those payloads back,
aggregates them via :func:`stages.qa.metrics.compute_fallback_summary`, and —
when the run-level fallback rate exceeds the configured threshold — emits a
single document-scope ``TRANSLATION_FALLBACK_RATE_HIGH`` QA record so a silent
whole-run provider downgrade surfaces in the QA report instead of being buried
in per-page metadata.

Severity is configurable (``QAConfig.fallback_rate_severity``, WARNING by
default) so a draft build is surfaced but not newly *blocked* unless the
operator opts into a blocking severity.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from atr_pipeline.stages.qa.metrics import compute_fallback_summary
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_metrics_v1 import FallbackSummary
from atr_schemas.qa_record_v1 import QARecordV1

CODE_FALLBACK_RATE_HIGH = "TRANSLATION_FALLBACK_RATE_HIGH"

_SEVERITY_LOOKUP: dict[str, Severity] = {
    "info": Severity.INFO,
    "warning": Severity.WARNING,
    "error": Severity.ERROR,
    "critical": Severity.CRITICAL,
}


def load_translation_metas(
    store: ArtifactStore,
    document_id: str,
    page_ids: Iterable[str],
) -> list[dict[str, object]]:
    """Load every available ``translation_meta.v1`` payload for *page_ids*.

    Pages without a translation_meta artifact (e.g. a source-only EN run, or a
    page that was never translated) are silently skipped — they are not part of
    the fallback-rate denominator. Returns the raw dicts so the metrics
    aggregator (``compute_fallback_summary``) can read ``fallback_used`` /
    ``primary_error`` without a tight schema coupling to the meta payload.
    """
    metas: list[dict[str, object]] = []
    for page_id in page_ids:
        data = store.load_latest_json(
            document_id=document_id,
            schema_family="translation_meta.v1",
            scope="page",
            entity_id=page_id,
        )
        if data is not None:
            metas.append(data)
    return metas


def coerce_fallback_severity(raw: str) -> Severity:
    """Map the configured severity string onto a ``Severity`` enum.

    Defaults to WARNING for an unrecognized value so a config typo degrades to
    a surfaced-but-non-blocking finding rather than vanishing.
    """
    return _SEVERITY_LOOKUP.get(raw.strip().lower(), Severity.WARNING)


def build_fallback_records(
    *,
    document_id: str,
    summary: FallbackSummary,
    threshold: float,
    severity: Severity,
) -> list[QARecordV1]:
    """Emit a ``TRANSLATION_FALLBACK_RATE_HIGH`` record when the run's
    fallback rate strictly exceeds *threshold*.

    Returns an empty list when the rate is at or below the threshold, or when
    no page has a translation_meta artifact (rate is 0.0 in that case). The
    record carries the rate as ``actual`` and the threshold as ``expected`` so
    downstream tooling can compare without re-parsing the message, and folds
    the distinct primary errors into the message for operator diagnosis.
    """
    if summary.pages_with_meta == 0 or summary.fallback_rate <= threshold:
        return []

    errors_suffix = ""
    if summary.primary_errors:
        joined = "; ".join(summary.primary_errors)
        errors_suffix = f" Primary errors: {joined}"

    message = (
        f"{summary.fallback_pages}/{summary.pages_with_meta} pages "
        f"({summary.fallback_rate:.1%}) used the fallback translation provider, "
        f"exceeding the {threshold:.1%} threshold — the run is a whole-document "
        f"quality degradation.{errors_suffix}"
    )
    record = QARecordV1(
        qa_id=f"qa.{document_id}.translation.fallback_rate",
        layer=QALayer.TERMINOLOGY,
        severity=severity,
        code=CODE_FALLBACK_RATE_HIGH,
        document_id=document_id,
        page_id=None,
        entity_ref=None,
        message=message,
        expected=threshold,
        actual=summary.fallback_rate,
    )
    return [record]


def apply_fallback_alert(
    *,
    store: ArtifactStore,
    document_id: str,
    page_ids: Iterable[str],
    threshold: float,
    severity: str,
    logger: logging.Logger,
    all_records: list[QARecordV1],
) -> FallbackSummary:
    """Load translation_meta for *page_ids*, aggregate it, log the operator
    alert, and append any over-threshold QA record to *all_records* in place.

    Takes primitives (not the StageContext) so this module stays within the
    ``stages`` import layer — it must not depend on ``runner``. Returns the
    ``FallbackSummary`` the caller threads into ``qa_metrics.v1``. The appended
    record list is empty in the common healthy case (rate at or below
    *threshold*) or when no page carries a translation_meta artifact. Appending
    before waivers/blocking lets the record flow through the same
    severity/blocking machinery as any other finding.
    """
    metas = load_translation_metas(store, document_id, page_ids)
    summary = compute_fallback_summary(metas)
    records = build_fallback_records(
        document_id=document_id,
        summary=summary,
        threshold=threshold,
        severity=coerce_fallback_severity(severity),
    )
    logger.info(
        "Translation fallback: %d/%d pages (%.1f%%) used the fallback provider",
        summary.fallback_pages,
        summary.pages_with_meta,
        summary.fallback_rate * 100,
    )
    for r in records:
        logger.warning("QA %s: %s", r.severity.value, r.message)
    all_records.extend(records)
    return summary
