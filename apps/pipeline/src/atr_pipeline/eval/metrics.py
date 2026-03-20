"""Evaluation metric protocol and built-in metric implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atr_pipeline.eval.models import GoldenPageSpec, MetricResult
from atr_schemas.page_ir_v1 import IconInline, PageIRV1


@runtime_checkable
class EvalMetric(Protocol):
    """Protocol for evaluation metrics."""

    @property
    def name(self) -> str: ...

    def evaluate(self, page_ir: PageIRV1, spec: GoldenPageSpec) -> MetricResult: ...


class BlockCountDelta:
    """Measures difference between actual and expected block count."""

    @property
    def name(self) -> str:
        return "block_count_delta"

    def evaluate(self, page_ir: PageIRV1, spec: GoldenPageSpec) -> MetricResult:
        actual = len(page_ir.blocks)
        expected = spec.block_count
        delta = actual - expected
        return MetricResult(
            metric_name=self.name,
            page_id=spec.page_id,
            value=float(actual),
            expected=float(expected),
            passed=delta == 0,
            detail=f"actual={actual} expected={expected} delta={delta}",
        )


class SymbolCount:
    """Counts inline icon/symbol nodes vs expected count."""

    @property
    def name(self) -> str:
        return "symbol_count"

    def evaluate(self, page_ir: PageIRV1, spec: GoldenPageSpec) -> MetricResult:
        actual = 0
        for block in page_ir.blocks:
            if not hasattr(block, "children"):
                continue
            for child in block.children:
                if isinstance(child, IconInline):
                    actual += 1
        expected = spec.symbol_count
        return MetricResult(
            metric_name=self.name,
            page_id=spec.page_id,
            value=float(actual),
            expected=float(expected),
            passed=actual == expected,
            detail=f"actual={actual} expected={expected}",
        )


class BlockTypeCoverage:
    """Checks that all expected block types appear in the page IR."""

    @property
    def name(self) -> str:
        return "block_type_coverage"

    def evaluate(self, page_ir: PageIRV1, spec: GoldenPageSpec) -> MetricResult:
        actual_types = {block.type for block in page_ir.blocks}
        expected_types = set(spec.block_types)
        if not expected_types:
            return MetricResult(
                metric_name=self.name,
                page_id=spec.page_id,
                value=1.0,
                expected=1.0,
                passed=True,
                detail="no expected types specified",
            )
        covered = expected_types & actual_types
        coverage = len(covered) / len(expected_types)
        missing = sorted(expected_types - actual_types)
        return MetricResult(
            metric_name=self.name,
            page_id=spec.page_id,
            value=coverage,
            expected=1.0,
            passed=coverage == 1.0,
            detail=f"coverage={coverage:.2f} missing={missing}" if missing else "all types present",
        )


class ReadingOrderAccuracy:
    """Compares actual reading order against expected order."""

    @property
    def name(self) -> str:
        return "reading_order_accuracy"

    def evaluate(self, page_ir: PageIRV1, spec: GoldenPageSpec) -> MetricResult:
        expected = spec.reading_order
        actual = page_ir.reading_order
        if not expected:
            return MetricResult(
                metric_name=self.name,
                page_id=spec.page_id,
                value=1.0,
                expected=1.0,
                passed=True,
                detail="no expected reading order specified",
            )
        if not actual:
            return MetricResult(
                metric_name=self.name,
                page_id=spec.page_id,
                value=0.0,
                expected=1.0,
                passed=False,
                detail="no reading order in IR",
            )
        matches = sum(1 for a, e in zip(actual, expected, strict=False) if a == e)
        max_len = max(len(actual), len(expected))
        accuracy = matches / max_len if max_len > 0 else 1.0
        return MetricResult(
            metric_name=self.name,
            page_id=spec.page_id,
            value=accuracy,
            expected=1.0,
            passed=accuracy == 1.0,
            detail=f"accuracy={accuracy:.2f} matched={matches}/{max_len}",
        )


def get_default_metrics() -> list[EvalMetric]:
    """Return the default set of evaluation metrics."""
    return [BlockCountDelta(), SymbolCount(), BlockTypeCoverage(), ReadingOrderAccuracy()]
