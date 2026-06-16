"""QAMetricsV1 — per-run QA health metrics artifact.

Sits alongside ``QASummaryV1`` in the run artifacts. The summary is the
authoritative severity tally and blocking flag; metrics add per-layer /
per-code distributions and page coverage so CI logs and future dashboards
can track QA health over time without re-parsing every record.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.qa_summary_v1 import SeverityCounts


class FindingCodeCount(BaseModel):
    """Count of QA findings grouped by rule code."""

    code: str
    count: int = 0


class FallbackSummary(BaseModel):
    """Run-level translation provider-fallback aggregate (S5U-1226).

    The translate stage records ``fallback_used`` + ``primary_error`` per page
    in the ``translation_meta.v1`` artifact; the QA stage folds those into this
    aggregate so a whole-run quality degradation ("N/M pages used the fallback
    provider") is visible in the persisted QA metrics instead of being buried
    in per-page metadata. ``pages_with_meta`` is the denominator — only pages
    that actually have a translation_meta artifact count toward the rate, so a
    source-only (EN) QA run reports ``pages_with_meta == 0`` and a 0.0 rate.
    """

    pages_with_meta: int = 0
    """Pages that have a ``translation_meta.v1`` artifact (the rate denominator)."""

    fallback_pages: int = 0
    """Subset of ``pages_with_meta`` whose winning provider was the fallback."""

    fallback_rate: float = 0.0
    """``fallback_pages / pages_with_meta`` (0.0 when the denominator is 0)."""

    primary_errors: list[str] = Field(default_factory=list)
    """Distinct primary-provider error strings observed across fallback pages,
    capped to keep the artifact bounded. Empty when no page fell back."""


class QAMetricsV1(BaseModel):
    """Per-run QA metrics artifact.

    All distribution fields (by-severity / by-layer / by-code) reflect
    **active** (non-waived) records only. Waived records are tallied
    separately in ``waived_count`` so health reporting isn't inflated by
    intentionally-suppressed findings.
    """

    schema_version: str = Field(default="qa_metrics.v1", pattern=r"^qa_metrics\.v\d+$")
    document_id: str
    run_id: str = ""
    edition: str = ""
    timestamp: str = ""
    pages_total: int = 0
    pages_with_findings: int = 0
    clean_page_rate: float = 0.0
    findings_by_severity: SeverityCounts = Field(default_factory=SeverityCounts)
    findings_by_layer: dict[str, int] = Field(default_factory=dict)
    findings_by_code_top10: list[FindingCodeCount] = Field(default_factory=list)
    waived_count: int = 0
    blocking_count: int = 0
    avg_findings_per_page: float = 0.0
    translation_fallback: FallbackSummary = Field(default_factory=FallbackSummary)
    """Run-level translation provider-fallback aggregate (S5U-1226)."""
