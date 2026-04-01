"""Benchmark ladder runner — executes checkpoints in order, detects regressions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atr_pipeline.eval.bench_loader import load_benchmark_ladder
from atr_pipeline.eval.bench_models import (
    BenchmarkReport,
    CheckpointResult,
    CheckpointSpec,
)
from atr_pipeline.eval.config_loader import load_golden_set
from atr_pipeline.eval.fixture_manifest import load_fixture_page_ir
from atr_pipeline.eval.models import EvalReport
from atr_pipeline.eval.runner import load_page_ir, run_evaluation
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1

logger = logging.getLogger(__name__)

StoreFactory = Callable[[str], ArtifactStore]


def run_benchmark_ladder(
    *,
    ladder_name: str,
    store_factory: StoreFactory,
    repo_root: Path | None = None,
    baseline: BenchmarkReport | None = None,
    use_fixtures: bool = True,
) -> BenchmarkReport:
    """Run a checkpointed benchmark ladder.

    Executes every checkpoint, then computes the frontier (first failure)
    and backward regressions (passed in baseline, fail now).
    """
    config = load_benchmark_ladder(ladder_name, repo_root=repo_root)
    results: list[CheckpointResult] = []

    for spec in config.checkpoints:
        result = _run_checkpoint(spec, store_factory, repo_root, use_fixtures=use_fixtures)
        results.append(result)

    _annotate_results(results, baseline)
    return _build_report(config.name, results)


def _run_checkpoint(
    spec: CheckpointSpec,
    store_factory: StoreFactory,
    repo_root: Path | None,
    *,
    use_fixtures: bool = True,
) -> CheckpointResult:
    """Run a single checkpoint against its golden set."""
    try:
        gs_config = load_golden_set(spec.golden_set, repo_root=repo_root)
    except FileNotFoundError:
        logger.warning(
            "golden set %r not found, skipping checkpoint %d", spec.golden_set, spec.order
        )
        return CheckpointResult(
            order=spec.order,
            name=spec.name,
            golden_set=spec.golden_set,
            passed=False,
            skipped=True,
            detail=f"golden set {spec.golden_set!r} not found",
        )

    document_id = gs_config.document_id

    report: EvalReport | None
    if use_fixtures:
        report = _run_with_fixtures(spec, document_id, store_factory, repo_root)
    else:
        report = _run_with_store(spec, document_id, store_factory, repo_root)

    if report is None:
        return CheckpointResult(
            order=spec.order,
            name=spec.name,
            golden_set=spec.golden_set,
            passed=False,
            skipped=True,
            detail=f"artifact store unavailable for {document_id!r}",
        )

    detail_parts: list[str] = []
    for page in report.pages:
        if not page.passed:
            failed = [m.metric_name for m in page.metrics if not m.passed]
            detail_parts.append(f"{page.page_id}: {', '.join(failed)}")

    return CheckpointResult(
        order=spec.order,
        name=spec.name,
        golden_set=spec.golden_set,
        passed=report.passed,
        detail="; ".join(detail_parts),
    )


def _make_fixture_loader(
    store_factory: StoreFactory,
    repo_root: Path | None,
) -> Callable[[str, str], PageIRV1 | None]:
    """Build a page-IR loader that reads fixtures first, then falls back to the store."""

    def _loader(document_id: str, page_id: str) -> PageIRV1 | None:
        data = load_fixture_page_ir(document_id, page_id, repo_root=repo_root)
        if data is not None:
            return PageIRV1.model_validate(data)
        try:
            store = store_factory(document_id)
        except (FileNotFoundError, KeyError):
            return None
        return load_page_ir(store, document_id, page_id)

    return _loader


def _run_with_fixtures(
    spec: CheckpointSpec,
    document_id: str,
    store_factory: StoreFactory,
    repo_root: Path | None,
) -> EvalReport:
    """Run evaluation using fixture-first page IR loading."""
    loader = _make_fixture_loader(store_factory, repo_root)
    return run_evaluation(
        golden_set_name=spec.golden_set,
        document_id=document_id,
        page_ir_loader=loader,
        repo_root=repo_root,
    )


def _run_with_store(
    spec: CheckpointSpec,
    document_id: str,
    store_factory: StoreFactory,
    repo_root: Path | None,
) -> EvalReport | None:
    """Run evaluation using the artifact store only. Returns None if store unavailable."""
    try:
        store = store_factory(document_id)
    except (FileNotFoundError, KeyError):
        logger.warning("no store for document %r, skipping", document_id)
        return None
    return run_evaluation(
        golden_set_name=spec.golden_set,
        document_id=document_id,
        store=store,
        repo_root=repo_root,
    )


def _annotate_results(
    results: list[CheckpointResult],
    baseline: BenchmarkReport | None,
) -> None:
    """Mark frontier and regression flags in-place."""
    frontier_order: int | None = None
    for r in results:
        if not r.passed and frontier_order is None:
            r.is_frontier = True
            frontier_order = r.order

    if baseline is None:
        return

    baseline_passed = {c.order for c in baseline.checkpoints if c.passed}
    for r in results:
        if not r.passed and r.order in baseline_passed:
            r.is_regression = True


def _build_report(
    ladder_name: str,
    results: list[CheckpointResult],
) -> BenchmarkReport:
    """Assemble the final BenchmarkReport from annotated results."""
    frontier: int | None = None
    regressions: list[int] = []
    highest = 0

    for r in results:
        if r.is_frontier:
            frontier = r.order
        if r.is_regression:
            regressions.append(r.order)

    # Highest consecutive passing streak from order 1.
    for r in sorted(results, key=lambda r: r.order):
        if r.passed and r.order == highest + 1:
            highest = r.order
        elif not r.passed:
            break

    all_passed = all(r.passed for r in results)

    return BenchmarkReport(
        ladder_name=ladder_name,
        timestamp=datetime.now(tz=UTC).isoformat(),
        checkpoints=results,
        frontier_checkpoint=frontier,
        regressions=regressions,
        highest_passing=highest,
        passed=all_passed,
    )
