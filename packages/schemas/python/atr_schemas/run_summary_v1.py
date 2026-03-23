"""RunSummaryV1 — flat, LLM-readable summary of a pipeline run."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunSummaryV1(BaseModel):
    """Human/LLM-readable summary written to artifact root after each run."""

    schema_version: str = Field(default="run_summary.v1", pattern=r"^run_summary\.v\d+$")
    run_id: str
    document_id: str
    status: str = ""
    edition: str = "all"
    pipeline_version: str = ""
    git_commit: str = ""
    stages_requested: list[str] = Field(default_factory=list)
    stages_completed: int = 0
    stages_failed: int = 0
    pages_total: int = 0
    pages_processed: int = 0
    pages_cached: int = 0
    pages_failed: int = 0
    page_filter: list[str] | None = None
    duration_s: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    config_hash: str = ""
    source_pdf_sha256: str = ""
