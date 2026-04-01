"""Smoke test: extraction_ladder runs end-to-end from a clean checkout."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.eval.bench_runner import run_benchmark_ladder
from atr_pipeline.store.artifact_store import ArtifactStore

REPO_ROOT = Path(__file__).resolve().parents[5]


def _noop_store_factory(document_id: str) -> ArtifactStore:
    """Factory that always raises — fixtures should satisfy all lookups."""
    raise FileNotFoundError(document_id)


class TestCleanCheckoutSmoke:
    """Verify the default ladder passes without any artifacts/ directory."""

    def test_extraction_ladder_all_pass(self) -> None:
        report = run_benchmark_ladder(
            ladder_name="extraction_ladder",
            store_factory=_noop_store_factory,
            repo_root=REPO_ROOT,
        )
        assert report.passed, (
            f"Ladder failed from clean checkout. "
            f"Frontier: {report.frontier_checkpoint}, "
            f"failing: {[c.name for c in report.checkpoints if not c.passed]}"
        )
        assert report.highest_passing == 7
        assert len(report.checkpoints) == 7
        assert all(c.passed for c in report.checkpoints)

    def test_no_regressions_without_baseline(self) -> None:
        report = run_benchmark_ladder(
            ladder_name="extraction_ladder",
            store_factory=_noop_store_factory,
            repo_root=REPO_ROOT,
        )
        assert report.regressions == []

    def test_deterministic_across_runs(self) -> None:
        r1 = run_benchmark_ladder(
            ladder_name="extraction_ladder",
            store_factory=_noop_store_factory,
            repo_root=REPO_ROOT,
        )
        r2 = run_benchmark_ladder(
            ladder_name="extraction_ladder",
            store_factory=_noop_store_factory,
            repo_root=REPO_ROOT,
        )
        assert r1.passed == r2.passed
        assert r1.highest_passing == r2.highest_passing
        for c1, c2 in zip(r1.checkpoints, r2.checkpoints, strict=True):
            assert c1.order == c2.order
            assert c1.passed == c2.passed
