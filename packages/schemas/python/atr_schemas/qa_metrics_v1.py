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
