"""Tests for the benchmark ladder runner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from atr_pipeline.eval.bench_models import BenchmarkReport, CheckpointResult
from atr_pipeline.eval.bench_runner import run_benchmark_ladder
from atr_pipeline.eval.config_loader import load_golden_set
from atr_pipeline.store.artifact_store import ArtifactStore

REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURES = REPO_ROOT / "packages" / "fixtures" / "sample_documents"


def _populate_store(
    store_root: Path,
    golden_set_name: str,
    document_id: str,
) -> None:
    """Copy expected IR fixtures into a tmp_path-based artifact store."""
    gs = load_golden_set(golden_set_name, repo_root=REPO_ROOT)
    for page_spec in gs.pages:
        ir_path = FIXTURES / document_id / "expected" / f"page_ir.en.{page_spec.page_id}.json"
        dest = store_root / document_id / "page_ir.v1.en" / "page" / page_spec.page_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "golden.json").write_text(ir_path.read_text())


def _make_store_factory(
    store_root: Path,
    populated_docs: set[str],
) -> Callable[[str], ArtifactStore]:
    """Build a store factory that raises for unpopulated docs."""

    def factory(document_id: str) -> ArtifactStore:
        if document_id not in populated_docs:
            raise FileNotFoundError(document_id)
        return ArtifactStore(store_root)

    return factory


# ── Minimal two-checkpoint ladder for unit tests ──────────────────────

MINI_LADDER = "extraction_ladder"  # uses real config, subset via populated docs


class TestAllPass:
    """All checkpoints pass when all fixtures are populated."""

    def test_all_seven_pass(self, tmp_path: Path) -> None:
        gs_names = [
            ("core", "walking_skeleton"),
            ("multi_column", "multi_column"),
            ("icon_dense", "icon_dense"),
            ("table_callout", "table_callout"),
            ("figure_caption", "figure_caption"),
            ("hard_route", "hard_route"),
            ("furniture_repetition", "furniture_repetition"),
        ]
        doc_ids: set[str] = set()
        for gs_name, doc_id in gs_names:
            _populate_store(tmp_path, gs_name, doc_id)
            doc_ids.add(doc_id)

        factory = _make_store_factory(tmp_path, doc_ids)
        report = run_benchmark_ladder(
            ladder_name=MINI_LADDER,
            store_factory=factory,
            repo_root=REPO_ROOT,
        )
        assert report.passed
        assert report.frontier_checkpoint is None
        assert report.regressions == []
        assert report.highest_passing == 7
        assert len(report.checkpoints) == 7
        assert all(c.passed for c in report.checkpoints)


class TestFrontierDetection:
    """Frontier is the first (lowest-order) failing checkpoint."""

    def test_missing_doc_skips_checkpoint(self, tmp_path: Path) -> None:
        # Only populate walking_skeleton — multi_column will fail (no store).
        _populate_store(tmp_path, "core", "walking_skeleton")
        factory = _make_store_factory(tmp_path, {"walking_skeleton"})

        report = run_benchmark_ladder(
            ladder_name=MINI_LADDER,
            store_factory=factory,
            repo_root=REPO_ROOT,
            use_fixtures=False,
        )
        assert not report.passed
        assert report.highest_passing == 1
        # Frontier is the first non-skipped failure or first skip
        assert report.checkpoints[0].passed
        assert not report.checkpoints[1].passed

    def test_frontier_marked_on_first_failure(self, tmp_path: Path) -> None:
        _populate_store(tmp_path, "core", "walking_skeleton")
        factory = _make_store_factory(tmp_path, {"walking_skeleton"})

        report = run_benchmark_ladder(
            ladder_name=MINI_LADDER,
            store_factory=factory,
            repo_root=REPO_ROOT,
            use_fixtures=False,
        )
        non_passing = [c for c in report.checkpoints if not c.passed]
        assert len(non_passing) > 0
        assert report.frontier_checkpoint is not None


class TestBaselineRegression:
    """Regression detection compares against a baseline report."""

    def test_regression_detected(self, tmp_path: Path) -> None:
        # Baseline: checkpoints 1 and 2 passed.
        baseline = BenchmarkReport(
            ladder_name=MINI_LADDER,
            timestamp="2026-01-01T00:00:00Z",
            checkpoints=[
                CheckpointResult(order=1, name="walking_skeleton", golden_set="core", passed=True),
                CheckpointResult(
                    order=2, name="multi_column", golden_set="multi_column", passed=True
                ),
            ],
            highest_passing=2,
            passed=True,
        )

        # Current run: only walking_skeleton populated → multi_column fails.
        _populate_store(tmp_path, "core", "walking_skeleton")
        factory = _make_store_factory(tmp_path, {"walking_skeleton"})

        report = run_benchmark_ladder(
            ladder_name=MINI_LADDER,
            store_factory=factory,
            repo_root=REPO_ROOT,
            baseline=baseline,
            use_fixtures=False,
        )
        assert not report.passed
        # Checkpoint 2 passed in baseline but fails now → regression.
        assert 2 in report.regressions

    def test_no_regression_without_baseline(self, tmp_path: Path) -> None:
        _populate_store(tmp_path, "core", "walking_skeleton")
        factory = _make_store_factory(tmp_path, {"walking_skeleton"})

        report = run_benchmark_ladder(
            ladder_name=MINI_LADDER,
            store_factory=factory,
            repo_root=REPO_ROOT,
            use_fixtures=False,
        )
        assert report.regressions == []

    def test_no_regression_when_baseline_also_failed(self, tmp_path: Path) -> None:
        baseline = BenchmarkReport(
            ladder_name=MINI_LADDER,
            timestamp="2026-01-01T00:00:00Z",
            checkpoints=[
                CheckpointResult(order=1, name="walking_skeleton", golden_set="core", passed=True),
                CheckpointResult(
                    order=2, name="multi_column", golden_set="multi_column", passed=False
                ),
            ],
            highest_passing=1,
            passed=False,
        )

        _populate_store(tmp_path, "core", "walking_skeleton")
        factory = _make_store_factory(tmp_path, {"walking_skeleton"})

        report = run_benchmark_ladder(
            ladder_name=MINI_LADDER,
            store_factory=factory,
            repo_root=REPO_ROOT,
            baseline=baseline,
            use_fixtures=False,
        )
        # Checkpoint 2 also failed in baseline → not a regression.
        assert 2 not in report.regressions


class TestEmptyLadder:
    """Edge case: ladder with no checkpoints."""

    def test_empty_ladder_passes(self, tmp_path: Path) -> None:
        ladder_dir = tmp_path / "configs" / "benchmarks"
        ladder_dir.mkdir(parents=True)
        (ladder_dir / "empty.toml").write_text(
            'schema_version = 1\nname = "empty"\ndescription = ""\n'
        )
        factory = _make_store_factory(tmp_path, set())

        report = run_benchmark_ladder(
            ladder_name="empty",
            store_factory=factory,
            repo_root=tmp_path,
        )
        assert report.passed
        assert report.checkpoints == []
        assert report.highest_passing == 0


class TestDeterminism:
    """Two runs with identical inputs produce identical results."""

    def test_same_inputs_same_result(self, tmp_path: Path) -> None:
        _populate_store(tmp_path, "core", "walking_skeleton")
        factory = _make_store_factory(tmp_path, {"walking_skeleton"})

        r1 = run_benchmark_ladder(
            ladder_name=MINI_LADDER, store_factory=factory, repo_root=REPO_ROOT, use_fixtures=False
        )
        r2 = run_benchmark_ladder(
            ladder_name=MINI_LADDER, store_factory=factory, repo_root=REPO_ROOT, use_fixtures=False
        )
        # Compare everything except timestamp.
        assert r1.passed == r2.passed
        assert r1.frontier_checkpoint == r2.frontier_checkpoint
        assert r1.highest_passing == r2.highest_passing
        assert r1.regressions == r2.regressions
        assert len(r1.checkpoints) == len(r2.checkpoints)
        for c1, c2 in zip(r1.checkpoints, r2.checkpoints, strict=True):
            assert c1.order == c2.order
            assert c1.passed == c2.passed
            assert c1.name == c2.name
