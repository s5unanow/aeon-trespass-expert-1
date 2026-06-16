"""S5U-1226 — run-level translation provider-fallback aggregate + alert.

Covers the two new pieces of behavior:

* ``compute_fallback_summary`` folds per-page ``translation_meta`` payloads into
  a ``FallbackSummary`` (pages_with_meta denominator, fallback_pages numerator,
  distinct/capped primary_errors).
* ``build_fallback_records`` emits a ``TRANSLATION_FALLBACK_RATE_HIGH`` QA record
  only when the rate strictly exceeds the threshold; severity is the configured
  value.

Red-before: with the S5U-1226 production code reverted these symbols do not
exist (``ImportError`` at collection time) — there is no pre-fix SHA where the
module is importable, so per ``.claude/rules/hooks.md`` the red-before evidence
is the pasted local pre-fix collection error in the PR body.
"""

from __future__ import annotations

from atr_pipeline.stages.qa.fallback_alert import (
    CODE_FALLBACK_RATE_HIGH,
    build_fallback_records,
    coerce_fallback_severity,
)
from atr_pipeline.stages.qa.metrics import (
    TOP_PRIMARY_ERROR_LIMIT,
    compute_fallback_summary,
)
from atr_schemas.enums import Severity


def _meta(fallback_used: bool, primary_error: object = None) -> dict[str, object]:
    return {"fallback_used": fallback_used, "primary_error": primary_error}


# ── compute_fallback_summary ──────────────────────────────────────────


def test_summary_no_fallback() -> None:
    summary = compute_fallback_summary([_meta(False), _meta(False), _meta(False)])
    assert summary.pages_with_meta == 3
    assert summary.fallback_pages == 0
    assert summary.fallback_rate == 0.0
    assert summary.primary_errors == []


def test_summary_partial_fallback_collects_distinct_errors() -> None:
    summary = compute_fallback_summary(
        [
            _meta(True, "agy boom A"),
            _meta(True, "agy boom A"),  # duplicate — deduped
            _meta(False),
        ]
    )
    assert summary.pages_with_meta == 3
    assert summary.fallback_pages == 2
    assert summary.fallback_rate == 2 / 3
    assert summary.primary_errors == ["agy boom A"]


def test_summary_all_fallback() -> None:
    summary = compute_fallback_summary([_meta(True, "boom"), _meta(True, "boom")])
    assert summary.fallback_pages == 2
    assert summary.pages_with_meta == 2
    assert summary.fallback_rate == 1.0


def test_summary_empty_iterable_is_zero_rate() -> None:
    """A source-only (EN) QA run passes no metas → 0.0 rate, no divide-by-zero."""
    summary = compute_fallback_summary([])
    assert summary.pages_with_meta == 0
    assert summary.fallback_pages == 0
    assert summary.fallback_rate == 0.0


def test_summary_primary_errors_capped() -> None:
    metas = [_meta(True, f"err-{i}") for i in range(TOP_PRIMARY_ERROR_LIMIT + 3)]
    summary = compute_fallback_summary(metas)
    assert summary.fallback_pages == TOP_PRIMARY_ERROR_LIMIT + 3
    assert len(summary.primary_errors) == TOP_PRIMARY_ERROR_LIMIT


def test_summary_ignores_blank_and_non_string_primary_error() -> None:
    summary = compute_fallback_summary(
        [_meta(True, ""), _meta(True, "   "), _meta(True, 42), _meta(True, None)]
    )
    assert summary.fallback_pages == 4
    assert summary.primary_errors == []


# ── build_fallback_records ────────────────────────────────────────────


def test_record_emitted_above_threshold() -> None:
    summary = compute_fallback_summary([_meta(True, "agy boom"), _meta(False)])
    records = build_fallback_records(
        document_id="doc1",
        summary=summary,
        threshold=0.25,
        severity=Severity.WARNING,
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.code == CODE_FALLBACK_RATE_HIGH
    assert rec.severity is Severity.WARNING
    assert rec.page_id is None
    assert rec.document_id == "doc1"
    assert rec.expected == 0.25
    assert rec.actual == 0.5
    assert "agy boom" in rec.message
    assert "1/2" in rec.message


def test_no_record_at_or_below_threshold() -> None:
    """Rate exactly equal to the threshold does not fire (strict >)."""
    summary = compute_fallback_summary([_meta(True, "boom"), _meta(False)])
    assert summary.fallback_rate == 0.5
    records = build_fallback_records(
        document_id="doc1",
        summary=summary,
        threshold=0.5,
        severity=Severity.WARNING,
    )
    assert records == []


def test_no_record_when_no_meta() -> None:
    summary = compute_fallback_summary([])
    records = build_fallback_records(
        document_id="doc1",
        summary=summary,
        threshold=0.0,
        severity=Severity.WARNING,
    )
    assert records == []


def test_configured_error_severity_is_honored() -> None:
    summary = compute_fallback_summary([_meta(True, "boom")])
    records = build_fallback_records(
        document_id="doc1",
        summary=summary,
        threshold=0.0,
        severity=coerce_fallback_severity("error"),
    )
    assert len(records) == 1
    assert records[0].severity is Severity.ERROR


def test_coerce_severity_defaults_to_warning_on_garbage() -> None:
    assert coerce_fallback_severity("nonsense") is Severity.WARNING
    assert coerce_fallback_severity("CRITICAL") is Severity.CRITICAL
