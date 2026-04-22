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

    def test_error_when_source_map_page_id_mismatches(self, export_dir: Path) -> None:
        from _export_validation import validate_export_completeness

        render_data = {
            "page": {"id": "p0001", "title": "OK"},
            "blocks": [],
            "figures": {},
            "source_map": {"page_id": "p8888", "block_refs": []},
        }
        (export_dir / "data" / "render_page.p0001.json").write_text(json.dumps(render_data))
        pages = [{"page_id": "p0001", "title": "OK"}]
        errors = validate_export_completeness(export_dir / "data", pages)
        assert len(errors) == 1
        assert "source_map.page_id" in errors[0]
        assert "p8888" in errors[0]


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


def _write_render_page(
    data_dir: Path,
    pid: str,
    *,
    presentation_mode: str,
    blocks: list[dict] | None = None,
) -> None:
    """Write a minimal render_page.{pid}.json fixture for guard tests."""
    payload = {
        "page": {"id": pid, "title": f"Test {pid}"},
        "presentation_mode": presentation_mode,
        "blocks": blocks if blocks is not None else [],
        "figures": {},
    }
    (data_dir / f"render_page.{pid}.json").write_text(json.dumps(payload))


def _paragraph(pid: str, idx: int, text: str) -> dict:
    """Build a RenderParagraph-shape block matching the live render_page schema."""
    return {
        "kind": "paragraph",
        "id": f"{pid}.b{idx:03d}",
        "children": [{"kind": "text", "text": text, "marks": []}],
    }


def _figure(pid: str, idx: int) -> dict:
    return {
        "kind": "figure",
        "id": f"{pid}.f{idx:03d}",
        "asset_id": f"{pid}.img{idx:04d}",
        "children": [],
    }


class TestValidatePresentationModePayloadConsistency:
    """S5U-699 — the must-refuse gate on (facsimile mode) ∧ (substantial blocks)."""

    def test_article_mode_with_many_blocks_is_ignored(self, tmp_path: Path) -> None:
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # Article-mode pages are out of scope — this validator only guards
        # the facsimile-side mismatch.
        blocks = [_paragraph("p0042", i, "Long readable paragraph " * 20) for i in range(40)]
        _write_render_page(data_dir, "p0042", presentation_mode="article", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert errors == []

    def test_facsimile_with_no_blocks_passes(self, tmp_path: Path) -> None:
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # Genuine facsimile-only page (e.g. p0001 cover): empty blocks list.
        _write_render_page(data_dir, "p0001", presentation_mode="facsimile", blocks=[])
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert errors == []

    def test_facsimile_under_both_thresholds_passes(self, tmp_path: Path) -> None:
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 5 short paragraphs (≤10 non-figure blocks, ≤400 chars) — genuinely
        # quiet facsimile page, no allowlist needed.
        blocks = [_paragraph("p0040", i, "short") for i in range(5)]
        _write_render_page(data_dir, "p0040", presentation_mode="facsimile", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert errors == []

    def test_facsimile_figure_only_never_trips(self, tmp_path: Path) -> None:
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 100 figure blocks, 0 non-figure, 0 text chars — legitimate image-
        # dominant page. Adversarial input: payload list is long but every
        # block is kind=figure, so neither threshold fires.
        blocks = [_figure("p0001", i) for i in range(100)]
        _write_render_page(data_dir, "p0001", presentation_mode="facsimile", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert errors == []

    def test_facsimile_with_substantial_payload_blocks_publish(self, tmp_path: Path) -> None:
        """The S5U-699 core case: p0075-shaped payload must fail without an override."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 44 non-figure blocks, ~940 chars — p0075 shape.
        blocks = [_paragraph("p0075", i, "Guaranteed Loot " * 2) for i in range(44)]
        _write_render_page(data_dir, "p0075", presentation_mode="facsimile", blocks=blocks)

        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert len(errors) == 1
        msg = errors[0]
        assert "p0075" in msg
        assert "presentation_mode=facsimile" in msg
        assert "44 non-figure blocks" in msg
        assert "article mode" in msg
        assert "page_overrides.p0075" in msg

    def test_facsimile_with_substantial_payload_allowlisted_passes(self, tmp_path: Path) -> None:
        """Explicit TOML override silences the guard for genuinely image-dominant pages."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # p0007 is configured facsimile-by-override with ~50 caption blocks
        # that are only meaningful alongside the raster. The allowlist suppresses
        # the guard for exactly this case.
        blocks = [_paragraph("p0007", i, "Caption text") for i in range(51)]
        _write_render_page(data_dir, "p0007", presentation_mode="facsimile", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, ["p0007"])
        assert errors == []

    def test_facsimile_just_over_block_threshold_fails(self, tmp_path: Path) -> None:
        """Boundary: >10 non-figure blocks trips even with trivial text."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 11 blocks, each 1 char — block-count gate fires, char-count does not.
        blocks = [_paragraph("p0666", i, "x") for i in range(11)]
        _write_render_page(data_dir, "p0666", presentation_mode="facsimile", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert len(errors) == 1
        assert "11 non-figure blocks" in errors[0]

    def test_facsimile_just_over_char_threshold_fails(self, tmp_path: Path) -> None:
        """Boundary: >400 text chars trips even with few blocks."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 1 block, 401 chars — char-count gate fires, block-count does not.
        blocks = [_paragraph("p0667", 0, "x" * 401)]
        _write_render_page(data_dir, "p0667", presentation_mode="facsimile", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert len(errors) == 1
        assert "401 text chars" in errors[0]
        assert "1 non-figure blocks" in errors[0]

    def test_facsimile_at_thresholds_passes(self, tmp_path: Path) -> None:
        """Boundary (strict `>`): exactly 10 blocks / 400 chars must pass."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # 10 blocks of 40 chars each = 400 chars, 10 non-figure blocks.
        blocks = [_paragraph("p0668", i, "x" * 40) for i in range(10)]
        _write_render_page(data_dir, "p0668", presentation_mode="facsimile", blocks=blocks)
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert errors == []

    def test_malformed_render_json_is_surfaced(self, tmp_path: Path) -> None:
        """G1 degenerate — a malformed file must fail the guard, not be ignored."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "render_page.p0099.json").write_text("{ not valid json")
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert len(errors) == 1
        assert "p0099" in errors[0]
        assert "could not read render file" in errors[0]

    def test_non_list_blocks_field_is_surfaced(self, tmp_path: Path) -> None:
        """Defensive: ``blocks`` that isn't a list is reported (payload corruption)."""
        from _export_validation import validate_presentation_mode_payload_consistency

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        payload = {
            "page": {"id": "p0500", "title": "corrupt"},
            "presentation_mode": "facsimile",
            "blocks": "oops",
            "figures": {},
        }
        (data_dir / "render_page.p0500.json").write_text(json.dumps(payload))
        errors = validate_presentation_mode_payload_consistency(data_dir, [])
        assert len(errors) == 1
        assert "not a list" in errors[0]

    def test_run_export_validation_fails_when_presentation_guard_fires(
        self, tmp_path: Path
    ) -> None:
        """Integration: mismatch at this layer must drive run_export_validation to False."""
        from _export_validation import run_export_validation

        edition_dir = tmp_path / "doc" / "en"
        data_dir = edition_dir / "data"
        data_dir.mkdir(parents=True)

        # Minimal manifest-on-disk pairing so completeness check passes.
        blocks = [_paragraph("p0075", i, "Guaranteed Loot " * 2) for i in range(44)]
        payload = {
            "page": {"id": "p0075", "title": "Tree of Knowledge"},
            "presentation_mode": "facsimile",
            "blocks": blocks,
            "figures": {},
        }
        (data_dir / "render_page.p0075.json").write_text(json.dumps(payload))
        (edition_dir / "manifest.json").write_text(
            json.dumps({"document_id": "doc", "pages": [{"page_id": "p0075", "title": "x"}]})
        )

        pages = [{"page_id": "p0075", "title": "Tree of Knowledge"}]
        # No allowlist -> must fail.
        assert run_export_validation(edition_dir, pages, []) is False
        # With allowlist -> must pass (other checks stay green).
        assert run_export_validation(edition_dir, pages, ["p0075"]) is True
