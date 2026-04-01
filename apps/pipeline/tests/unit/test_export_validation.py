"""Tests for export validation checks (_export_validation.py)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture()
def export_dir(tmp_path: Path) -> Path:
    """Create a minimal export directory with one valid page."""
    edition_dir = tmp_path / "doc" / "en"
    data_dir = edition_dir / "data"
    data_dir.mkdir(parents=True)

    render_data = {
        "page": {"id": "p0001", "title": "Attack Phase"},
        "blocks": [],
        "figures": {},
    }
    (data_dir / "render_page.p0001.json").write_text(json.dumps(render_data))

    manifest = {
        "document_id": "doc",
        "pages": [{"page_id": "p0001", "title": "Attack Phase"}],
    }
    (edition_dir / "manifest.json").write_text(json.dumps(manifest))
    return edition_dir


class TestValidateExportCompleteness:
    def test_pass_when_manifest_matches_files(self, export_dir: Path) -> None:
        from _export_validation import validate_export_completeness

        pages = [{"page_id": "p0001", "title": "Attack Phase"}]
        errors = validate_export_completeness(export_dir / "data", pages)
        assert errors == []

    def test_error_when_render_file_missing(self, export_dir: Path) -> None:
        from _export_validation import validate_export_completeness

        pages = [
            {"page_id": "p0001", "title": "Attack Phase"},
            {"page_id": "p0002", "title": "Defense Phase"},
        ]
        errors = validate_export_completeness(export_dir / "data", pages)
        assert len(errors) == 1
        assert "p0002" in errors[0]
        assert "missing" in errors[0]

    def test_error_when_orphan_render_file(self, export_dir: Path) -> None:
        from _export_validation import validate_export_completeness

        # Add an extra render file not in manifest
        (export_dir / "data" / "render_page.p0099.json").write_text("{}")
        pages = [{"page_id": "p0001", "title": "Attack Phase"}]
        errors = validate_export_completeness(export_dir / "data", pages)
        assert len(errors) == 1
        assert "p0099" in errors[0]
        assert "not in manifest" in errors[0]

    def test_empty_manifest_reports_orphans(self, export_dir: Path) -> None:
        from _export_validation import validate_export_completeness

        errors = validate_export_completeness(export_dir / "data", [])
        assert len(errors) == 1
        assert "p0001" in errors[0]

    def test_error_when_internal_page_id_mismatches(self, export_dir: Path) -> None:
        from _export_validation import validate_export_completeness

        # Overwrite render file with mismatched internal page.id
        render_data = {
            "page": {"id": "p9999", "title": "Wrong ID"},
            "blocks": [],
            "figures": {},
        }
        (export_dir / "data" / "render_page.p0001.json").write_text(json.dumps(render_data))
        pages = [{"page_id": "p0001", "title": "Attack Phase"}]
        errors = validate_export_completeness(export_dir / "data", pages)
        assert len(errors) == 1
        assert "p0001" in errors[0]
        assert "p9999" in errors[0]
        assert "internal page.id" in errors[0]


class TestValidateAssetExistence:
    def test_pass_when_no_figures(self, export_dir: Path) -> None:
        from _export_validation import validate_asset_existence

        errors = validate_asset_existence(export_dir / "data")
        assert errors == []

    def test_error_when_figure_block_references_missing_asset(self, export_dir: Path) -> None:
        from _export_validation import validate_asset_existence

        render_data = {
            "page": {"id": "p0001", "title": "Test"},
            "blocks": [{"kind": "figure", "asset_id": "img0001"}],
            "figures": {},
        }
        (export_dir / "data" / "render_page.p0001.json").write_text(json.dumps(render_data))
        errors = validate_asset_existence(export_dir / "data")
        assert any("missing asset" in e for e in errors)


class TestValidateTitleQuality:
    def test_pass_for_good_titles(self) -> None:
        from _export_validation import validate_title_quality

        pages = [
            {"page_id": "p0001", "title": "Attack Phase"},
            {"page_id": "p0002", "title": "Page 40"},
        ]
        warnings = validate_title_quality(pages)
        assert warnings == []

    def test_warn_for_garbage_titles(self) -> None:
        from _export_validation import validate_title_quality

        pages = [
            {"page_id": "p0001", "title": ""},
            {"page_id": "p0002", "title": "1"},
        ]
        warnings = validate_title_quality(pages)
        assert len(warnings) == 2


class TestRunExportValidation:
    def test_returns_true_for_valid_export(self, export_dir: Path) -> None:
        from _export_validation import run_export_validation

        manifest = json.loads((export_dir / "manifest.json").read_text())
        assert run_export_validation(export_dir, manifest["pages"]) is True

    def test_returns_false_when_completeness_fails(self, export_dir: Path) -> None:
        from _export_validation import run_export_validation

        # Manifest with extra page not on disk
        pages = [
            {"page_id": "p0001", "title": "Attack Phase"},
            {"page_id": "p0099", "title": "Ghost Page"},
        ]
        assert run_export_validation(export_dir, pages) is False
