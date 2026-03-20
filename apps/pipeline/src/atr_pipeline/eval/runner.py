"""Evaluation orchestrator — loads artifacts, runs metrics, builds report."""

from __future__ import annotations

import json
import logging
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
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1

logger = logging.getLogger(__name__)


def run_evaluation(
    *,
    golden_set_name: str,
    document_id: str,
    store: ArtifactStore,
    repo_root: Path | None = None,
    page_filter: list[str] | None = None,
) -> EvalReport:
    """Run the full evaluation pipeline.

    Args:
        golden_set_name: Name of the golden set config (e.g. "core").
        document_id: Document to evaluate.
        store: Artifact store to load IR from.
        repo_root: Repository root for locating configs.
        page_filter: Optional list of page IDs to evaluate.

    Returns:
        EvalReport with per-page and aggregate results.
    """
    golden = load_golden_set(golden_set_name, repo_root=repo_root)
    metrics = get_default_metrics()
    pages_to_eval = _filter_pages(golden, page_filter)

    page_results: list[PageEvalResult] = []

    for spec in pages_to_eval:
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
    all_passed = all(p.passed for p in page_results)

    return EvalReport(
        golden_set_name=golden.name,
        document_id=document_id,
        timestamp=datetime.now(tz=UTC).isoformat(),
        pages=page_results,
        aggregate=aggregate,
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
    page_dir = store.root / document_id / "page_ir.v1.en" / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return PageIRV1.model_validate(json.loads(jsons[-1].read_text()))


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
    """Compute aggregate metrics across all pages."""
    if not page_results:
        return {}
    all_metrics: dict[str, list[float]] = {}
    for page in page_results:
        for m in page.metrics:
            if m.metric_name not in all_metrics:
                all_metrics[m.metric_name] = []
            all_metrics[m.metric_name].append(1.0 if m.passed else 0.0)

    aggregate: dict[str, float] = {}
    for name, values in sorted(all_metrics.items()):
        aggregate[f"{name}_pass_rate"] = sum(values) / len(values)

    total_metrics = sum(len(p.metrics) for p in page_results)
    total_passed = sum(1 for p in page_results for m in p.metrics if m.passed)
    aggregate["overall_pass_rate"] = total_passed / total_metrics if total_metrics > 0 else 0.0

    return aggregate
