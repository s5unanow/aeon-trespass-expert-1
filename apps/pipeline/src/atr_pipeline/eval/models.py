"""Pydantic models for the evaluation harness."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GoldenPageSpec(BaseModel):
    """Expected properties for a single page in a golden set."""

    page_id: str
    block_count: int = Field(ge=0)
    block_types: list[str] = Field(default_factory=list)
    symbol_count: int = Field(ge=0, default=0)
    reading_order: list[str] = Field(default_factory=list)


class GoldenSetConfig(BaseModel):
    """Configuration for a golden evaluation set loaded from TOML."""

    name: str
    document_id: str
    pages: list[GoldenPageSpec] = Field(default_factory=list)


class MetricResult(BaseModel):
    """Result of a single metric evaluation on a page."""

    metric_name: str
    page_id: str
    value: float
    expected: float | None = None
    passed: bool
    detail: str = ""


class PageEvalResult(BaseModel):
    """Evaluation results for a single page."""

    page_id: str
    metrics: list[MetricResult] = Field(default_factory=list)
    passed: bool = True


class EvalReport(BaseModel):
    """Full evaluation report across all pages."""

    golden_set_name: str
    document_id: str
    timestamp: str
    pages: list[PageEvalResult] = Field(default_factory=list)
    aggregate: dict[str, float] = Field(default_factory=dict)
    passed: bool = True
