"""QASummaryV1 — aggregated QA result for a document run."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SeverityCounts(BaseModel):
    """Counts by severity level."""

    info: int = 0
    warning: int = 0
    error: int = 0
    critical: int = 0


class QASummaryV1(BaseModel):
    """Aggregated QA summary for a document."""

    schema_version: str = Field(default="qa_summary.v1", pattern=r"^qa_summary\.v\d+$")
    document_id: str
    run_id: str = ""
    edition: str = ""
    counts: SeverityCounts = Field(default_factory=SeverityCounts)
    waived_counts: SeverityCounts = Field(default_factory=SeverityCounts)
    blocking: bool = False
    record_refs: list[str] = Field(default_factory=list)
    review_pack_ref: str = ""
    qa_metrics_ref: str = ""
    """Relative artifact-store path to the `QAMetricsV1` emitted by this run.

    Populated by ``QAStage`` (S5U-641) so the export layer can copy the
    exact metrics artifact paired with this summary instead of selecting a
    metrics file independently by mtime, which could pair a summary with
    a stale metrics artifact from an interrupted prior run. Legacy
    summaries predating S5U-641 have an empty string; exporters fall back
    to latest-match selection for those.
    """
