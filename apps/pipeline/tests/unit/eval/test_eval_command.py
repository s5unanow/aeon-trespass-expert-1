"""Tests for the eval CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config import load_document_config
from atr_schemas.page_ir_v1 import HeadingBlock, IconInline, PageIRV1, ParagraphBlock

runner = CliRunner()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _write_golden_ir(artifacts_root: Path, document_id: str, page_id: str) -> None:
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
    ir_dir = artifacts_root / document_id / "page_ir.v1.en" / "page" / page_id
    ir_dir.mkdir(parents=True, exist_ok=True)
    (ir_dir / "test.json").write_text(json.dumps(json.loads(ir.model_dump_json()), indent=2))


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_eval_help() -> None:
    """eval --help works."""
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "golden-set" in _strip_ansi(result.output)


def test_eval_doc_is_optional() -> None:
    """eval accepts --golden-set without --doc (doc inferred from golden set)."""
    result = runner.invoke(app, ["eval", "--help"])
    # --doc should not be marked as required in help output
    help_text = _strip_ansi(result.output)
    assert "--doc" in help_text
    # Verify we can invoke with just --golden-set (will fail on golden set lookup, not arg parse)
    result = runner.invoke(app, ["eval", "--golden-set", "nonexistent"])
    # Should fail because golden set doesn't exist, NOT because --doc is missing
    assert result.exit_code != 0
    assert "Missing option" not in _strip_ansi(result.output)


def test_eval_golden_set_all_accepted_without_doc(tmp_path: Path) -> None:
    """eval --golden-set all runs without --doc."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with (
        patch(
            "atr_pipeline.cli.commands.eval_cmd.load_document_config",
            return_value=patched_config,
        ),
        patch(
            "atr_pipeline.cli.commands.eval_cmd.discover_golden_sets",
            return_value=["core"],
        ),
    ):
        result = runner.invoke(app, ["eval", "--golden-set", "all"])

    output = _strip_ansi(result.output)
    assert "Missing option" not in output
    assert "Running 1 golden set(s)" in output


def test_eval_missing_golden_set() -> None:
    """eval with non-existent golden set fails."""
    result = runner.invoke(
        app, ["eval", "--golden-set", "nonexistent", "--doc", "walking_skeleton"]
    )
    assert result.exit_code != 0


def test_eval_with_output_json(tmp_path: Path) -> None:
    """eval writes JSON report when --output-json is specified."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.eval_cmd.load_document_config",
        return_value=patched_config,
    ):
        output_json = tmp_path / "report.json"
        result = runner.invoke(
            app,
            [
                "eval",
                "--golden-set",
                "core",
                "--doc",
                "walking_skeleton",
                "--output-json",
                str(output_json),
            ],
        )

    assert result.exit_code == 0, result.output
    assert output_json.exists()
    report_data = json.loads(output_json.read_text())
    assert report_data["passed"] is True


def test_eval_fail_on_threshold_passing(tmp_path: Path) -> None:
    """eval --fail-on-threshold exits 0 when all thresholds pass."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.eval_cmd.load_document_config",
        return_value=patched_config,
    ):
        result = runner.invoke(
            app,
            [
                "eval",
                "--golden-set",
                "core",
                "--doc",
                "walking_skeleton",
                "--fail-on-threshold",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "THRESHOLD" in _strip_ansi(result.output)


def test_eval_fail_on_threshold_reports_values(tmp_path: Path) -> None:
    """eval --fail-on-threshold includes threshold table in output."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.eval_cmd.load_document_config",
        return_value=patched_config,
    ):
        output_json = tmp_path / "report.json"
        result = runner.invoke(
            app,
            [
                "eval",
                "--golden-set",
                "core",
                "--doc",
                "walking_skeleton",
                "--fail-on-threshold",
                "--output-json",
                str(output_json),
            ],
        )

    assert result.exit_code == 0, result.output
    report_data = json.loads(output_json.read_text())
    assert "threshold_results" in report_data
    assert len(report_data["threshold_results"]) > 0


def test_generate_overlays_passes_pyramid_dpi() -> None:
    """_generate_overlays propagates pyramid_dpi to PageRasterProvider."""
    from atr_pipeline.cli.commands.eval_cmd import _generate_overlays
    from atr_pipeline.eval.models import EvalReport

    report = MagicMock(spec=EvalReport)
    report.pages = []
    store = MagicMock()
    custom_dpi = [150]

    with patch("atr_pipeline.services.pdf.raster_provider.PageRasterProvider") as mock_provider_cls:
        _generate_overlays(store, "doc1", report, pyramid_dpi=custom_dpi)

    mock_provider_cls.assert_called_once_with(store=store, document_id="doc1", pyramid_dpi=[150])


def test_generate_overlays_default_dpi_is_none() -> None:
    """_generate_overlays without pyramid_dpi passes None (provider uses its default)."""
    from atr_pipeline.cli.commands.eval_cmd import _generate_overlays
    from atr_pipeline.eval.models import EvalReport

    report = MagicMock(spec=EvalReport)
    report.pages = []
    store = MagicMock()

    with patch("atr_pipeline.services.pdf.raster_provider.PageRasterProvider") as mock_provider_cls:
        _generate_overlays(store, "doc1", report)

    mock_provider_cls.assert_called_once_with(store=store, document_id="doc1", pyramid_dpi=None)


def test_run_all_golden_sets_uses_atomic_write_for_output_json(tmp_path: Path) -> None:
    """S5U-625: combined eval report JSON must be written via atomic_write_text.

    Without the fix, ``Path(output_json).write_text(...)`` is called and the
    patched ``atomic_write_text`` is never invoked, so the assertion fails.
    """
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})
    output_json = tmp_path / "combined.json"

    with (
        patch(
            "atr_pipeline.cli.commands.eval_cmd.load_document_config",
            return_value=patched_config,
        ),
        patch(
            "atr_pipeline.cli.commands.eval_cmd.discover_golden_sets",
            return_value=["core"],
        ),
        patch("atr_pipeline.cli.commands.eval_cmd.atomic_write_text") as mock_atomic,
    ):
        result = runner.invoke(
            app,
            ["eval", "--golden-set", "all", "--output-json", str(output_json)],
        )

    assert result.exit_code == 0, result.output
    assert mock_atomic.call_count == 1, (
        f"Expected combined report to route through atomic_write_text; "
        f"called {mock_atomic.call_count} times"
    )
    called_path = mock_atomic.call_args.args[0]
    assert Path(called_path) == output_json
    # Body is valid JSON list of reports
    body = mock_atomic.call_args.args[1]
    parsed = json.loads(body)
    assert isinstance(parsed, list) and len(parsed) == 1


def test_generate_overlays_uses_atomic_write_for_png() -> None:
    """S5U-625: overlay PNGs must be written via atomic_write_bytes.

    Without the fix, ``out_path.write_bytes(png_bytes)`` is called and the
    patched ``atomic_write_bytes`` is never invoked.
    """
    from atr_pipeline.cli.commands.eval_cmd import _generate_overlays
    from atr_pipeline.eval.models import EvalReport

    page_result = MagicMock()
    page_result.page_id = "p0001"
    report = MagicMock(spec=EvalReport)
    report.pages = [page_result]

    store = MagicMock()
    store.root = Path("/fake/artifacts")

    provider_instance = MagicMock()
    provider_instance.get_raster.return_value = Path("/fake/raster.png")

    with (
        patch(
            "atr_pipeline.services.pdf.raster_provider.PageRasterProvider",
            return_value=provider_instance,
        ),
        patch(
            "atr_pipeline.cli.commands.eval_cmd.load_page_ir",
            return_value=MagicMock(),
        ),
        patch(
            "atr_pipeline.eval.overlay.draw_ir_overlay",
            return_value=b"\x89PNG fake overlay bytes",
        ),
        patch(
            "pathlib.Path.mkdir",
        ),
        patch("atr_pipeline.cli.commands.eval_cmd.atomic_write_bytes") as mock_atomic,
    ):
        _generate_overlays(store, "doc1", report)

    assert mock_atomic.call_count == 1, (
        f"Expected overlay PNG to route through atomic_write_bytes; "
        f"called {mock_atomic.call_count} times"
    )
    out_path = mock_atomic.call_args.args[0]
    data = mock_atomic.call_args.args[1]
    assert out_path.name == "overlay.png"
    assert data == b"\x89PNG fake overlay bytes"
