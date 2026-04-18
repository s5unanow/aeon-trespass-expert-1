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


def _write_summary(
    artifact_root: Path,
    doc_id: str,
    filename: str,
    *,
    edition: str,
    run_id: str,
    record_refs: list[str],
) -> Path:
    """Seed one QASummaryV1 artifact under the canonical layout."""
    summary = {
        "schema_version": "qa_summary.v1",
        "document_id": doc_id,
        "run_id": run_id,
        "edition": edition,
        "counts": {"info": 0, "warning": 0, "error": len(record_refs), "critical": 0},
        "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "blocking": False,
        "record_refs": record_refs,
        "review_pack_ref": "",
    }
    path = artifact_root / doc_id / "qa" / "document" / doc_id / filename
    _write(path, summary)
    return path


def test_export_qa_selects_summary_matching_edition(qa_module: ModuleType, tmp_path: Path) -> None:
    """Regression for S5U-610: EN and RU summaries coexisting must not cross-contaminate.

    Seed both an EN and a RU summary in the same artifact directory, with RU
    *newer* (larger mtime) than EN. Export for edition="en" must pick the EN
    payload, not the newer RU one. This asserts that mtime-only selection
    (the pre-fix behavior) would fail this test.
    """
    doc_id = "test_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id

    en_rec = {
        "schema_version": "qa_record.v1",
        "qa_id": "qa.p0003.en_rule",
        "layer": "structure",
        "severity": "warning",
        "code": "PARAGRAPH_TOO_LONG",
        "document_id": doc_id,
        "page_id": "p0003",
        "entity_ref": "p0003.b001",
        "message": "EN finding",
    }
    ru_rec = {
        "schema_version": "qa_record.v1",
        "qa_id": "qa.p0004.ru_rule",
        "layer": "terminology",
        "severity": "error",
        "code": "UNTRANSLATED",
        "document_id": doc_id,
        "page_id": "p0004",
        "entity_ref": "p0004.b002",
        "message": "RU finding",
    }
    en_ref = f"{doc_id}/qa_record.v1/page/p0003/en_rec.json"
    ru_ref = f"{doc_id}/qa_record.v1/page/p0004/ru_rec.json"
    _write(artifact_root / en_ref, en_rec)
    _write(artifact_root / ru_ref, ru_rec)

    en_summary_path = _write_summary(
        artifact_root,
        doc_id,
        "en_summary.json",
        edition="en",
        run_id="run_en",
        record_refs=[en_ref],
    )
    ru_summary_path = _write_summary(
        artifact_root,
        doc_id,
        "ru_summary.json",
        edition="ru",
        run_id="run_ru",
        record_refs=[ru_ref],
    )

    # Force RU to be newer than EN so mtime-only selection would pick RU.
    import os

    os.utime(en_summary_path, (1_700_000_000, 1_700_000_000))
    os.utime(ru_summary_path, (1_800_000_000, 1_800_000_000))

    # Export EN — must pick the EN summary despite RU being newer.
    count_en = qa_module.export_qa(artifact_root, doc_id, "en", doc_public)
    assert count_en == 1
    en_out = json.loads((doc_public / "en" / "data" / "qa_summary.json").read_text())
    en_records = json.loads((doc_public / "en" / "data" / "qa_records.json").read_text())
    assert en_out["run_id"] == "run_en"
    assert en_out["edition"] == "en"
    assert {r["code"] for r in en_records["records"]} == {"PARAGRAPH_TOO_LONG"}

    # Export RU — must pick the RU summary.
    count_ru = qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)
    assert count_ru == 1
    ru_out = json.loads((doc_public / "ru" / "data" / "qa_summary.json").read_text())
    ru_records = json.loads((doc_public / "ru" / "data" / "qa_records.json").read_text())
    assert ru_out["run_id"] == "run_ru"
    assert ru_out["edition"] == "ru"
    assert {r["code"] for r in ru_records["records"]} == {"UNTRANSLATED"}


def test_export_qa_falls_back_to_untagged_when_no_match(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """Legacy summaries (no `edition` field) are still picked when no tagged summary exists."""
    doc_id = "legacy_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    _seed_artifacts(artifact_root, doc_id)  # seeds a summary without `edition`

    count = qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)
    assert count == 2


def test_export_qa_skips_untagged_when_other_edition_is_tagged(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """If an EN-tagged summary exists, a RU export must NOT fall back to an
    untagged summary — that would reintroduce the S5U-610 cross-contamination.
    """
    doc_id = "mixed_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id

    rec = {
        "schema_version": "qa_record.v1",
        "qa_id": "qa.p0001.only",
        "layer": "structure",
        "severity": "warning",
        "code": "ANY",
        "document_id": doc_id,
        "page_id": "p0001",
        "entity_ref": "p0001.b000",
        "message": "x",
    }
    ref = f"{doc_id}/qa_record.v1/page/p0001/r.json"
    _write(artifact_root / ref, rec)

    _write_summary(
        artifact_root, doc_id, "en.json", edition="en", run_id="run_en", record_refs=[ref]
    )
    # Seed an untagged summary too — it must be ignored when RU is requested
    # and an EN-tagged summary is present.
    _write(
        artifact_root / doc_id / "qa" / "document" / doc_id / "legacy.json",
        {
            "schema_version": "qa_summary.v1",
            "document_id": doc_id,
            "run_id": "run_legacy",
            "edition": "",
            "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
            "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
            "blocking": False,
            "record_refs": [],
            "review_pack_ref": "",
        },
    )

    count = qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)
    assert count == 0
    assert not (doc_public / "ru" / "data" / "qa_summary.json").exists()


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
