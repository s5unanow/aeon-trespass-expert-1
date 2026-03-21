"""Pydantic models for the full-document extraction audit report."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageAuditResult(BaseModel):
    """Diagnostic summary for a single page."""

    page_id: str
    block_count: int = 0
    symbol_count: int = 0
    unresolved_symbol_count: int = 0
    fallback_block_count: int = 0
    hard_page: bool = False
    recommended_route: str = ""
    invariant_issue_counts: dict[str, int] = Field(default_factory=dict)
    reading_order_failure: bool = False


class AuditReport(BaseModel):
    """Full-document extraction audit report.

    This report is diagnostic and non-blocking by default.
    It covers every page in the document, not just golden pages.
    """

    document_id: str
    timestamp: str
    page_count: int = 0
    pages_audited: int = 0
    pages_missing_ir: int = 0
    pages: list[PageAuditResult] = Field(default_factory=list)

    # Aggregate issue counts by invariant code
    total_issue_counts: dict[str, int] = Field(default_factory=dict)
    # Page lists by diagnostic category
    fallback_route_pages: list[str] = Field(default_factory=list)
    hard_pages: list[str] = Field(default_factory=list)
    invariant_failure_pages: list[str] = Field(default_factory=list)
    reading_order_failure_pages: list[str] = Field(default_factory=list)

    # Baseline comparison
    baseline_snapshot_id: str | None = None
    baseline_delta: dict[str, float] | None = None

    # Non-blocking by design
    blocking: bool = False
    passed: bool = True
