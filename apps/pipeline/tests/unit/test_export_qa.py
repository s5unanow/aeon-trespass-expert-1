"""Tests for scripts/_export_qa.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "_export_qa.py"


@pytest.fixture()
def qa_module() -> Iterator[ModuleType]:
    """Import _export_qa.py as a module."""
    spec = importlib.util.spec_from_file_location("_export_qa_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_qa_test"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_qa_test", None)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _seed_artifacts(root: Path, doc_id: str) -> None:
    """Seed a minimal artifact tree with one summary + two records."""
    rec1 = {
        "schema_version": "qa_record.v1",
        "qa_id": "qa.p0003.rule_a",
        "layer": "structure",
        "severity": "warning",
        "code": "PARAGRAPH_TOO_LONG",
        "document_id": doc_id,
        "page_id": "p0003",
        "entity_ref": "p0003.b001",
        "message": "Block has 3141 chars (max 1000)",
    }
    rec2 = {
        "schema_version": "qa_record.v1",
        "qa_id": "qa.p0004.rule_b",
        "layer": "terminology",
        "severity": "error",
        "code": "UNTRANSLATED",
        "document_id": doc_id,
        "page_id": "p0004",
        "entity_ref": "p0004.b002",
        "message": "Untranslated segment",
    }
    ref1 = f"{doc_id}/qa_record.v1/page/p0003/rec1.json"
    ref2 = f"{doc_id}/qa_record.v1/page/p0004/rec2.json"
    _write(root / ref1, rec1)
    _write(root / ref2, rec2)

    summary = {
        "schema_version": "qa_summary.v1",
        "document_id": doc_id,
        "run_id": "run_test",
        "counts": {"info": 0, "warning": 1, "error": 1, "critical": 0},
        "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "blocking": True,
        "record_refs": [ref1, ref2],
        "review_pack_ref": "",
    }
    _write(root / doc_id / "qa" / "document" / doc_id / "sum.json", summary)


def test_export_qa_writes_summary_and_records(qa_module: ModuleType, tmp_path: Path) -> None:
    doc_id = "test_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    _seed_artifacts(artifact_root, doc_id)

    count = qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)

    assert count == 2
    out_dir = doc_public / "ru" / "data"
    summary = json.loads((out_dir / "qa_summary.json").read_text())
    records_payload = json.loads((out_dir / "qa_records.json").read_text())

    assert summary["document_id"] == doc_id
    assert summary["counts"]["error"] == 1
    assert len(records_payload["records"]) == 2
    codes = {r["code"] for r in records_payload["records"]}
    assert codes == {"PARAGRAPH_TOO_LONG", "UNTRANSLATED"}


def test_export_qa_missing_summary_dir(qa_module: ModuleType, tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / "nothing"

    count = qa_module.export_qa(artifact_root, "nothing", "ru", doc_public)

    assert count == 0
    assert not (doc_public / "ru" / "data" / "qa_summary.json").exists()


def test_export_qa_is_idempotent(qa_module: ModuleType, tmp_path: Path) -> None:
    doc_id = "test_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    _seed_artifacts(artifact_root, doc_id)

    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)
    out_dir = doc_public / "ru" / "data"
    first_summary = (out_dir / "qa_summary.json").read_text()
    first_records = (out_dir / "qa_records.json").read_text()

    # Second run should be byte-identical.
    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)
    assert (out_dir / "qa_summary.json").read_text() == first_summary
    assert (out_dir / "qa_records.json").read_text() == first_records


def test_export_qa_skips_missing_record_refs(qa_module: ModuleType, tmp_path: Path) -> None:
    doc_id = "test_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id

    # Write a summary that points to a missing record — it must be skipped,
    # not cause an exception.
    summary = {
        "schema_version": "qa_summary.v1",
        "document_id": doc_id,
        "run_id": "r",
        "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "blocking": False,
        "record_refs": [f"{doc_id}/qa_record.v1/page/p9999/ghost.json"],
        "review_pack_ref": "",
    }
    _write(
        artifact_root / doc_id / "qa" / "document" / doc_id / "only.json",
        summary,
    )

    count = qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)

    assert count == 0
    records = json.loads((doc_public / "ru" / "data" / "qa_records.json").read_text())
    assert records == {"records": []}
