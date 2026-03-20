"""Tests for golden fixture definitions and eval harness integration.

Validates that:
- All golden set configs load correctly
- All expected page IR JSON files parse as valid PageIRV1
- Golden set specs are consistent with expected IR files
- Coverage matrix references valid fixture documents
- The eval harness runs against synthetic IR matching golden specs
- Furniture repetition fixture asserts cross-page consistency
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atr_pipeline.eval.config_loader import discover_golden_sets, load_golden_set
from atr_pipeline.eval.runner import run_evaluation
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1

REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURES = REPO_ROOT / "packages" / "fixtures" / "sample_documents"

# All golden fixture document IDs (excluding walking_skeleton which has its own tests)
GOLDEN_FIXTURE_IDS = [
    "multi_column",
    "icon_dense",
    "table_callout",
    "figure_caption",
    "hard_route",
    "furniture_repetition",
]


def _expected_irs(doc_id: str) -> list[Path]:
    """Find all expected page IR files for a fixture document."""
    expected_dir = FIXTURES / doc_id / "expected"
    return sorted(expected_dir.glob("page_ir.en.*.json"))


class TestGoldenSetConfigs:
    """All golden set TOML configs load and are well-formed."""

    def test_discover_finds_all_golden_sets(self) -> None:
        names = discover_golden_sets(repo_root=REPO_ROOT)
        for doc_id in GOLDEN_FIXTURE_IDS:
            assert doc_id in names, f"golden set {doc_id} not discovered"

    @pytest.mark.parametrize("doc_id", GOLDEN_FIXTURE_IDS)
    def test_golden_set_loads(self, doc_id: str) -> None:
        gs = load_golden_set(doc_id, repo_root=REPO_ROOT)
        assert gs.name == doc_id
        assert gs.document_id == doc_id
        assert len(gs.pages) > 0

    @pytest.mark.parametrize("doc_id", GOLDEN_FIXTURE_IDS)
    def test_golden_set_pages_have_specs(self, doc_id: str) -> None:
        gs = load_golden_set(doc_id, repo_root=REPO_ROOT)
        for page in gs.pages:
            assert page.block_count >= 0
            assert len(page.block_types) == page.block_count
            assert len(page.reading_order) == page.block_count


class TestExpectedIRValidity:
    """All expected page IR JSON files parse as valid PageIRV1."""

    @pytest.mark.parametrize("doc_id", GOLDEN_FIXTURE_IDS)
    def test_expected_irs_exist(self, doc_id: str) -> None:
        irs = _expected_irs(doc_id)
        assert len(irs) > 0, f"no expected IRs for {doc_id}"

    @pytest.mark.parametrize("doc_id", GOLDEN_FIXTURE_IDS)
    def test_expected_irs_parse(self, doc_id: str) -> None:
        for ir_path in _expected_irs(doc_id):
            data = json.loads(ir_path.read_text())
            ir = PageIRV1.model_validate(data)
            assert ir.document_id == doc_id


class TestGoldenSpecConsistency:
    """Golden set specs match the expected IR files."""

    @pytest.mark.parametrize("doc_id", GOLDEN_FIXTURE_IDS)
    def test_spec_matches_ir(self, doc_id: str) -> None:
        gs = load_golden_set(doc_id, repo_root=REPO_ROOT)
        for page_spec in gs.pages:
            ir_path = FIXTURES / doc_id / "expected" / f"page_ir.en.{page_spec.page_id}.json"
            assert ir_path.exists(), f"missing IR for {page_spec.page_id}"
            ir = PageIRV1.model_validate(json.loads(ir_path.read_text()))
            assert len(ir.blocks) == page_spec.block_count
            assert len(ir.reading_order) == page_spec.block_count


class TestEvalHarnessIntegration:
    """Eval harness runs against synthetic IR matching golden specs."""

    @pytest.mark.parametrize("doc_id", GOLDEN_FIXTURE_IDS)
    def test_eval_passes_with_matching_ir(self, doc_id: str, tmp_path: Path) -> None:
        gs = load_golden_set(doc_id, repo_root=REPO_ROOT)
        store = ArtifactStore(tmp_path)
        for page_spec in gs.pages:
            ir_path = FIXTURES / doc_id / "expected" / f"page_ir.en.{page_spec.page_id}.json"
            ir_data = ir_path.read_text()
            ir_dir = tmp_path / doc_id / "page_ir.v1.en" / "page" / page_spec.page_id
            ir_dir.mkdir(parents=True, exist_ok=True)
            (ir_dir / "golden.json").write_text(ir_data)

        report = run_evaluation(
            golden_set_name=doc_id,
            document_id=doc_id,
            store=store,
            repo_root=REPO_ROOT,
        )
        assert report.passed, f"eval failed for {doc_id}: {report.aggregate}"


class TestFurnitureRepetition:
    """Furniture repetition fixture asserts cross-page consistency."""

    def test_three_pages_present(self) -> None:
        gs = load_golden_set("furniture_repetition", repo_root=REPO_ROOT)
        assert len(gs.pages) == 3

    def test_consistent_structure_across_pages(self) -> None:
        gs = load_golden_set("furniture_repetition", repo_root=REPO_ROOT)
        for page in gs.pages:
            assert page.block_count == 2
            assert page.block_types == ["heading", "paragraph"]
            assert page.symbol_count == 0

    def test_no_furniture_in_blocks(self) -> None:
        """Furniture (headers/footers) must not appear in content blocks."""
        for page_id in ("p0001", "p0002", "p0003"):
            ir_path = FIXTURES / "furniture_repetition" / "expected" / f"page_ir.en.{page_id}.json"
            ir = PageIRV1.model_validate(json.loads(ir_path.read_text()))
            for block in ir.blocks:
                if hasattr(block, "children"):
                    for child in block.children:
                        if hasattr(child, "text"):
                            assert "Chapter 4" not in child.text
                            assert "Combat Rules" not in child.text


class TestCoverageMatrix:
    """Coverage matrix references valid documents and dimensions."""

    def test_coverage_matrix_loads(self) -> None:
        import tomllib

        matrix_path = REPO_ROOT / "configs" / "golden_sets" / "coverage_matrix.toml"
        assert matrix_path.exists()
        with open(matrix_path, "rb") as f:
            matrix = tomllib.load(f)
        assert len(matrix) >= 6

    def test_all_fixtures_in_matrix(self) -> None:
        import tomllib

        matrix_path = REPO_ROOT / "configs" / "golden_sets" / "coverage_matrix.toml"
        with open(matrix_path, "rb") as f:
            matrix = tomllib.load(f)
        for doc_id in GOLDEN_FIXTURE_IDS:
            assert doc_id in matrix, f"{doc_id} missing from coverage matrix"
            entry = matrix[doc_id]
            assert "failure_modes" in entry
            assert "eval_dimensions" in entry
            assert len(entry["failure_modes"]) > 0
