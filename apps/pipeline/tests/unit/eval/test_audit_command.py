"""Tests for the audit CLI command."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config import load_document_config
from atr_schemas.resolved_page_v1 import ResolvedBlock, ResolvedPageV1

runner = CliRunner()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _write_resolved(artifacts_root: Path, doc_id: str, page_id: str) -> None:
    """Write a synthetic resolved page artifact."""
    resolved = ResolvedPageV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=1,
        blocks=[
            ResolvedBlock(block_id=f"{page_id}.b001", block_type="paragraph"),
            ResolvedBlock(block_id=f"{page_id}.b002", block_type="heading"),
        ],
        main_flow_order=[f"{page_id}.b001", f"{page_id}.b002"],
    )
    art_dir = artifacts_root / doc_id / "resolved_page.v1" / "page" / page_id
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "test.json").write_text(resolved.model_dump_json())


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_audit_help() -> None:
    """audit --help works."""
    result = runner.invoke(app, ["audit", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    assert "--doc" in help_text
    assert "--output-json" in help_text
    assert "--baseline" in help_text


def test_audit_basic(tmp_path: Path) -> None:
    """audit runs and prints summary."""
    artifacts = tmp_path / "artifacts"
    _write_resolved(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.audit_cmd.load_document_config",
        return_value=patched_config,
    ):
        result = runner.invoke(app, ["audit", "--doc", "walking_skeleton"])

    output = _strip_ansi(result.output)
    assert result.exit_code == 0
    assert "Audit: walking_skeleton" in output
    assert "DIAGNOSTIC" in output


def test_audit_output_json(tmp_path: Path) -> None:
    """audit writes JSON report when --output-json is specified."""
    artifacts = tmp_path / "artifacts"
    _write_resolved(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    output_json = tmp_path / "audit_report.json"

    with patch(
        "atr_pipeline.cli.commands.audit_cmd.load_document_config",
        return_value=patched_config,
    ):
        result = runner.invoke(
            app,
            [
                "audit",
                "--doc",
                "walking_skeleton",
                "--output-json",
                str(output_json),
            ],
        )

    assert result.exit_code == 0
    assert output_json.exists()
    report = json.loads(output_json.read_text())
    assert report["document_id"] == "walking_skeleton"
    assert report["passed"] is True
    assert report["blocking"] is False


def test_audit_page_filter(tmp_path: Path) -> None:
    """audit respects --pages filter."""
    artifacts = tmp_path / "artifacts"
    _write_resolved(artifacts, "walking_skeleton", "p0001")
    _write_resolved(artifacts, "walking_skeleton", "p0002")
    _write_resolved(artifacts, "walking_skeleton", "p0003")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    output_json = tmp_path / "audit_report.json"

    with patch(
        "atr_pipeline.cli.commands.audit_cmd.load_document_config",
        return_value=patched_config,
    ):
        result = runner.invoke(
            app,
            [
                "audit",
                "--doc",
                "walking_skeleton",
                "--pages",
                "p0001,p0003",
                "--output-json",
                str(output_json),
            ],
        )

    assert result.exit_code == 0
    report = json.loads(output_json.read_text())
    assert report["pages_audited"] == 2
    page_ids = {p["page_id"] for p in report["pages"]}
    assert page_ids == {"p0001", "p0003"}


def test_audit_never_exits_nonzero(tmp_path: Path) -> None:
    """audit always exits 0 (non-blocking diagnostic)."""
    artifacts = tmp_path / "artifacts"
    # Write a page with a dangling flow ref
    resolved = ResolvedPageV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        blocks=[ResolvedBlock(block_id="p0001.b001", block_type="paragraph")],
        main_flow_order=["p0001.b001", "nonexistent"],
    )
    art_dir = artifacts / "walking_skeleton" / "resolved_page.v1" / "page" / "p0001"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "test.json").write_text(resolved.model_dump_json())

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.audit_cmd.load_document_config",
        return_value=patched_config,
    ):
        result = runner.invoke(app, ["audit", "--doc", "walking_skeleton"])

    # Even with invariant failures, audit should exit 0
    assert result.exit_code == 0
