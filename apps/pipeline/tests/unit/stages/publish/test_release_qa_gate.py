"""Tests for the ``atr release`` QA gate (S5U-893).

S5U-870 extracted a shared ``evaluate_qa_gate`` so the three bundle paths
(PublishStage, ``make export``, ``atr release``) agree on QA enforcement, but
``atr release`` was left on its own legacy ``_check_qa_gate`` that treated a
**missing** QA summary as "warning, skip the gate" and proceeded — diverging
from the other two paths, which fail closed (raise ``QAGateError``) when no
summary is resolvable. These tests pin the harmonized behaviour:

* no summary -> FAILS CLOSED (``typer.Exit``), matching PublishStage/export;
* blocking summary -> still refuses;
* clean summary -> still releases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.exceptions import Exit

from atr_pipeline.cli.commands.release import _check_qa_gate

_BLOCK_ON = {"error", "critical"}


def _write_artifact(artifact_root: Path, ref: str, data: dict[str, object]) -> None:
    """Write a JSON artifact at the given ref path."""
    path = artifact_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _qa_summary(*, blocking: bool, record_refs: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": "qa_summary.v1",
        "document_id": "doc1",
        "run_id": "run_1",
        "blocking": blocking,
        "record_refs": record_refs or [],
    }


def _qa_record(*, code: str, severity: str, page_id: str) -> dict[str, object]:
    return {
        "schema_version": "qa_record.v1",
        "qa_id": f"qa-{code}",
        "layer": "structure",
        "severity": severity,
        "code": code,
        "document_id": "doc1",
        "page_id": page_id,
    }


def test_no_summary_fails_closed(tmp_path: Path) -> None:
    """A run with no QA summary ref refuses the release (fail-closed).

    This is the S5U-893 divergence: pre-fix ``_check_qa_gate`` echoed a warning
    and returned (proceeding with the release). Post-fix it routes through the
    shared gate, which raises ``QAGateError`` on ``summary is None``, so the CLI
    exits non-zero — matching PublishStage and ``make export``.
    """
    run_data: dict[str, str | None] = {
        "run_id": "run_1",
        "qa_summary_ref": None,
        "run_manifest_ref": "doc1/run_manifest.v1/run/run_1/m.json",
    }
    with pytest.raises(Exit) as excinfo:
        _check_qa_gate(tmp_path, run_data, block_on=_BLOCK_ON)
    assert excinfo.value.exit_code == 1


def test_empty_summary_ref_fails_closed(tmp_path: Path) -> None:
    """An empty-string ``qa_summary_ref`` (not just ``None``) also fails closed."""
    run_data: dict[str, str | None] = {
        "run_id": "run_1",
        "qa_summary_ref": "",
        "run_manifest_ref": "doc1/run_manifest.v1/run/run_1/m.json",
    }
    with pytest.raises(Exit):
        _check_qa_gate(tmp_path, run_data, block_on=_BLOCK_ON)


def test_unreadable_summary_artifact_fails_closed(tmp_path: Path) -> None:
    """A summary ref that points at a missing/unreadable artifact fails closed.

    The ref exists in the run row but the artifact is gone on disk; the loader
    degrades to ``None`` (after logging), and the shared gate then refuses —
    never "pass by absent state" (Rule G1).
    """
    run_data: dict[str, str | None] = {
        "run_id": "run_1",
        "qa_summary_ref": "doc1/qa.v1/document/doc1/missing.json",
        "run_manifest_ref": "doc1/run_manifest.v1/run/run_1/m.json",
    }
    with pytest.raises(Exit):
        _check_qa_gate(tmp_path, run_data, block_on=_BLOCK_ON)


def test_blocking_summary_refuses(tmp_path: Path) -> None:
    """A blocking QA summary still refuses the release (unchanged behaviour)."""
    artifact_root = tmp_path / "artifacts"
    record_ref = "doc1/qa_record.v1/record/r1.json"
    _write_artifact(
        artifact_root,
        record_ref,
        _qa_record(code="ERR_X", severity="error", page_id="p0007"),
    )
    summary_ref = "doc1/qa.v1/document/doc1/summary.json"
    _write_artifact(
        artifact_root,
        summary_ref,
        _qa_summary(blocking=True, record_refs=[record_ref]),
    )
    run_data: dict[str, str | None] = {
        "run_id": "run_1",
        "qa_summary_ref": summary_ref,
        "run_manifest_ref": "doc1/run_manifest.v1/run/run_1/m.json",
    }
    with pytest.raises(Exit) as excinfo:
        _check_qa_gate(artifact_root, run_data, block_on=_BLOCK_ON)
    assert excinfo.value.exit_code == 1


def test_clean_summary_releases(tmp_path: Path) -> None:
    """A non-blocking QA summary allows the release to proceed (no exit)."""
    artifact_root = tmp_path / "artifacts"
    summary_ref = "doc1/qa.v1/document/doc1/summary.json"
    _write_artifact(
        artifact_root,
        summary_ref,
        _qa_summary(blocking=False),
    )
    run_data: dict[str, str | None] = {
        "run_id": "run_1",
        "qa_summary_ref": summary_ref,
        "run_manifest_ref": "doc1/run_manifest.v1/run/run_1/m.json",
    }
    # Must NOT raise: the gate passes for a clean run.
    _check_qa_gate(artifact_root, run_data, block_on=_BLOCK_ON)
