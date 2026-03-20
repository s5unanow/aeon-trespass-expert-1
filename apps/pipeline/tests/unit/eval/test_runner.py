"""Tests for the evaluation runner."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.eval.runner import run_evaluation
from atr_pipeline.eval.thresholds import MetricThreshold, ThresholdConfig
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import HeadingBlock, IconInline, PageIRV1, ParagraphBlock


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _write_golden_ir(store: ArtifactStore, document_id: str, page_id: str) -> None:
    """Write a synthetic page IR that matches the core golden set."""
    ir = PageIRV1(
        document_id=document_id,
        page_id=page_id,
        page_number=1,
        language="en",
        blocks=[
            HeadingBlock(
                block_id="p0001.b001",
                children=[IconInline(symbol_id="sym_001")],
            ),
            ParagraphBlock(block_id="p0001.b002"),
        ],
        reading_order=["p0001.b001", "p0001.b002"],
    )
    ir_dir = store.root / document_id / "page_ir.v1.en" / "page" / page_id
    ir_dir.mkdir(parents=True, exist_ok=True)
    (ir_dir / "test.json").write_text(json.dumps(json.loads(ir.model_dump_json()), indent=2))


def test_run_evaluation_passing(tmp_path: Path) -> None:
    """Full evaluation with matching IR passes all metrics."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
    )

    assert report.golden_set_name == "core"
    assert report.document_id == "walking_skeleton"
    assert len(report.pages) == 1
    assert report.passed
    assert report.pages[0].passed


def test_run_evaluation_missing_ir(tmp_path: Path) -> None:
    """Evaluation with missing IR fails gracefully."""
    store = ArtifactStore(tmp_path / "artifacts")

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
    )

    assert not report.passed
    assert len(report.pages) == 1
    assert not report.pages[0].passed
    assert report.pages[0].metrics[0].metric_name == "page_ir_load"


def test_run_evaluation_page_filter(tmp_path: Path) -> None:
    """Page filter limits evaluation to specified pages."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
        page_filter=["p9999"],
    )

    assert len(report.pages) == 0
    assert report.passed


def test_run_evaluation_aggregate(tmp_path: Path) -> None:
    """Aggregate metrics are computed correctly."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
    )

    assert "overall_pass_rate" in report.aggregate
    assert report.aggregate["overall_pass_rate"] == 1.0


def test_run_evaluation_report_json_roundtrip(tmp_path: Path) -> None:
    """Report can be serialized to JSON and back."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
    )

    from atr_pipeline.eval.models import EvalReport

    roundtripped = EvalReport.model_validate_json(report.model_dump_json())
    assert roundtripped.passed == report.passed
    assert len(roundtripped.pages) == len(report.pages)


def test_run_evaluation_aggregate_has_mean(tmp_path: Path) -> None:
    """Aggregate includes _mean keys alongside _pass_rate."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
    )

    assert "reading_order_accuracy_mean" in report.aggregate
    assert "block_count_delta_mean" in report.aggregate
    assert "symbol_count_mean" in report.aggregate
    assert "block_type_coverage_mean" in report.aggregate


def test_run_evaluation_with_thresholds_pass(tmp_path: Path) -> None:
    """Evaluation with passing thresholds reports passed=True."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    config = ThresholdConfig(
        metric_thresholds=[
            MetricThreshold(name="overall_pass_rate", min=0.95, blocking=True),
        ]
    )

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
        threshold_config=config,
    )

    assert report.passed
    assert len(report.threshold_results) == 1
    assert report.threshold_results[0].passed


def test_run_evaluation_with_thresholds_fail(tmp_path: Path) -> None:
    """Evaluation with impossible threshold reports passed=False."""
    store = ArtifactStore(tmp_path / "artifacts")
    # Write IR that DOES NOT match golden -> some metrics will fail
    ir = PageIRV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        language="en",
        blocks=[HeadingBlock(block_id="p0001.b001")],
        reading_order=["p0001.b001"],
    )
    ir_dir = store.root / "walking_skeleton" / "page_ir.v1.en" / "page" / "p0001"
    ir_dir.mkdir(parents=True, exist_ok=True)
    (ir_dir / "test.json").write_text(json.dumps(json.loads(ir.model_dump_json()), indent=2))

    config = ThresholdConfig(
        metric_thresholds=[
            MetricThreshold(name="overall_pass_rate", min=1.0, blocking=True),
        ]
    )

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
        threshold_config=config,
    )

    # Some metrics fail (block_count, symbol_count) -> overall_pass_rate < 1.0
    assert not report.passed
    assert len(report.threshold_results) == 1
    assert not report.threshold_results[0].passed


def test_run_evaluation_non_blocking_threshold_does_not_fail(tmp_path: Path) -> None:
    """Non-blocking threshold failure does not set report.passed=False."""
    store = ArtifactStore(tmp_path / "artifacts")
    _write_golden_ir(store, "walking_skeleton", "p0001")

    config = ThresholdConfig(
        metric_thresholds=[
            MetricThreshold(name="nonexistent_metric", min=1.0, blocking=False),
        ]
    )

    report = run_evaluation(
        golden_set_name="core",
        document_id="walking_skeleton",
        store=store,
        repo_root=_repo_root(),
        threshold_config=config,
    )

    # Non-blocking failure -> report still passes
    assert report.passed
    assert len(report.threshold_results) == 1
    assert not report.threshold_results[0].passed
