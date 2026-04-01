"""Evaluation orchestrator — loads artifacts, runs metrics, builds report."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atr_pipeline.eval.comparator import compare_blocks
from atr_pipeline.eval.config_loader import load_golden_set
from atr_pipeline.eval.metrics import get_default_metrics
from atr_pipeline.eval.models import (
    EvalReport,
    GoldenPageSpec,
    GoldenSetConfig,
    MetricResult,
    PageEvalResult,
)
from atr_pipeline.eval.thresholds import ThresholdConfig, ThresholdResult, check_thresholds
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1

logger = logging.getLogger(__name__)

PageIRLoader = Callable[[str, str], PageIRV1 | None]
"""Callback: (document_id, page_id) → PageIRV1 | None."""


def run_evaluation(
    *,
    golden_set_name: str,
    document_id: str,
    store: ArtifactStore | None = None,
    repo_root: Path | None = None,
    page_filter: list[str] | None = None,
    threshold_config: ThresholdConfig | None = None,
    page_ir_loader: PageIRLoader | None = None,
) -> EvalReport:
    """Run the full evaluation pipeline.

    Args:
        golden_set_name: Name of the golden set config (e.g. "core").
        document_id: Document to evaluate.
        store: Artifact store to load IR from (optional if page_ir_loader given).
        repo_root: Repository root for locating configs.
        page_filter: Optional list of page IDs to evaluate.
        page_ir_loader: Optional callback to load page IR instead of store.

    Returns:
        EvalReport with per-page and aggregate results.
    """
    if store is None and page_ir_loader is None:
        msg = "Either store or page_ir_loader must be provided"
        raise ValueError(msg)

    golden = load_golden_set(golden_set_name, repo_root=repo_root)
    metrics = get_default_metrics()
    pages_to_eval = _filter_pages(golden, page_filter)

    page_results: list[PageEvalResult] = []

    for spec in pages_to_eval:
        if page_ir_loader is not None:
            page_ir = page_ir_loader(document_id, spec.page_id)
        else:
            assert store is not None  # narrowing for mypy
            page_ir = load_page_ir(store, document_id, spec.page_id)
        if page_ir is None:
            logger.warning("page IR missing: page_id=%s doc=%s", spec.page_id, document_id)
            page_results.append(
                PageEvalResult(
                    page_id=spec.page_id,
                    metrics=[
                        MetricResult(
                            metric_name="page_ir_load",
                            page_id=spec.page_id,
                            value=0.0,
                            expected=1.0,
                            passed=False,
                            detail="page IR not found in artifact store",
                        )
                    ],
                    passed=False,
                )
            )
            continue

        page_metrics = [m.evaluate(page_ir, spec) for m in metrics]
        block_types = _build_expected_block_types(spec)
        if block_types:
            comparison = compare_blocks(page_ir, block_types)
            page_metrics.append(
                MetricResult(
                    metric_name="block_diff",
                    page_id=spec.page_id,
                    value=float(comparison.match_count),
                    expected=float(len(block_types)),
                    passed=comparison.all_match,
                    detail=f"match={comparison.match_count} missing={comparison.missing_count} "
                    f"extra={comparison.extra_count} mismatch={comparison.mismatch_count}",
                )
            )

        page_passed = all(m.passed for m in page_metrics)
        page_results.append(
            PageEvalResult(page_id=spec.page_id, metrics=page_metrics, passed=page_passed)
        )

    aggregate = _compute_aggregate(page_results)

    threshold_results: list[ThresholdResult] = []
    if threshold_config is not None:
        threshold_results = check_thresholds(aggregate, threshold_config)

    all_pages_passed = all(p.passed for p in page_results)
    if threshold_config is not None:
        blocking_failed = any(not t.passed and t.blocking for t in threshold_results)
        all_passed = all_pages_passed and not blocking_failed
    else:
        all_passed = all_pages_passed

    return EvalReport(
        golden_set_name=golden.name,
        document_id=document_id,
        timestamp=datetime.now(tz=UTC).isoformat(),
        pages=page_results,
        aggregate=aggregate,
        threshold_results=threshold_results,
        passed=all_passed,
    )


def _filter_pages(
    golden: GoldenSetConfig,
    page_filter: list[str] | None,
) -> list[GoldenPageSpec]:
    """Filter golden pages by page_filter if provided."""
    if page_filter is None:
        return golden.pages
    filter_set = set(page_filter)
    return [p for p in golden.pages if p.page_id in filter_set]


def load_page_ir(store: ArtifactStore, document_id: str, page_id: str) -> PageIRV1 | None:
    """Load the latest EN page IR from the artifact store."""
    data = store.load_latest_json(
        document_id=document_id, schema_family="page_ir.v1.en", scope="page", entity_id=page_id
    )
    return PageIRV1.model_validate(data) if data else None


def _build_expected_block_types(spec: GoldenPageSpec) -> dict[str, str]:
    """Build block_id -> block_type mapping from golden spec.

    Uses reading_order for block IDs and block_types for types.
    """
    if not spec.reading_order or not spec.block_types:
        return {}
    if len(spec.reading_order) != len(spec.block_types):
        logger.warning(
            "golden spec length mismatch: reading_order=%d block_types=%d for %s",
            len(spec.reading_order),
            len(spec.block_types),
            spec.page_id,
        )
    return dict(zip(spec.reading_order, spec.block_types, strict=False))


def _compute_aggregate(page_results: list[PageEvalResult]) -> dict[str, float]:
    """Compute aggregate metrics across all pages.

    Emits two keys per metric:
      {metric_name}_pass_rate — fraction of pages that pass
      {metric_name}_mean     — mean of the metric value across pages
    Plus overall_pass_rate across all metric checks.
    """
    if not page_results:
        return {}
    pass_lists: dict[str, list[float]] = {}
    value_lists: dict[str, list[float]] = {}
    for page in page_results:
        for m in page.metrics:
            if m.metric_name not in pass_lists:
                pass_lists[m.metric_name] = []
                value_lists[m.metric_name] = []
            pass_lists[m.metric_name].append(1.0 if m.passed else 0.0)
            value_lists[m.metric_name].append(m.value)

    aggregate: dict[str, float] = {}
    for name in sorted(pass_lists):
        passes = pass_lists[name]
        values = value_lists[name]
        aggregate[f"{name}_pass_rate"] = sum(passes) / len(passes)
        aggregate[f"{name}_mean"] = sum(values) / len(values)

    total_metrics = sum(len(p.metrics) for p in page_results)
    total_passed = sum(1 for p in page_results for m in p.metrics if m.passed)
    aggregate["overall_pass_rate"] = total_passed / total_metrics if total_metrics > 0 else 0.0

    return aggregate
