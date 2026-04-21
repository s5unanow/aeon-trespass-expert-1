"""Regression tests for S5U-689 — public QA bundle must strip internal fields.

These tests guard the ``scripts/_export_qa.py`` projection boundary: the
published ``qa_summary.json`` and ``qa_records.json`` must not contain any
of the internal-only fields named in the Linear issue's
"Semantically-equivalent threats" section. They are a narrow, purpose-built
regression gate — the behavioral export tests live in
``test_export_qa.py`` and ``test_export_to_web.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from atr_schemas.public_qa_record_set_v1 import PublicQARecordSetV1, PublicQARecordV1
from atr_schemas.public_qa_summary_v1 import PublicQASummaryV1
from atr_schemas.qa_record_v1 import AutoFix, QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1, SeverityCounts

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "_export_qa.py"

# S5U-689 Semantically-equivalent threats — summary-level leakage.
SUMMARY_INTERNAL_FIELDS = {
    "run_id",
    "record_refs",
    "review_pack_ref",
    "qa_metrics_ref",
}

# S5U-689 Semantically-equivalent threats — record-level leakage.
RECORD_INTERNAL_FIELDS = {
    "auto_fix",
    "evidence_refs",
    "waiver_ref",
    # The record-level schema_version is internal artifact provenance; the
    # public record set carries a single top-level schema_version instead.
    "schema_version",
    "document_id",
    "expected",
    "actual",
}


@pytest.fixture()
def qa_module() -> Iterator[ModuleType]:
    """Import _export_qa.py as a module."""
    spec = importlib.util.spec_from_file_location("_export_qa_public_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_qa_public_test"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_qa_public_test", None)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _seed_full_artifacts(root: Path, doc_id: str) -> None:
    """Seed internal QA artifacts populating every internal field.

    This exercises the projection: if a field is present on the internal
    side but should be dropped on the public side, the assertions below
    will fail without the projection.
    """
    rec_with_internals = {
        "schema_version": "qa_record.v1",
        "qa_id": "qa.p0003.leaky",
        "layer": "structure",
        "severity": "warning",
        "code": "PARAGRAPH_TOO_LONG",
        "document_id": doc_id,
        "page_id": "p0003",
        "entity_ref": "p0003.b001",
        "message": "Block has 3141 chars (max 1000)",
        "expected": {"max_chars": 1000},
        "actual": {"chars": 3141},
        "auto_fix": {"available": True, "fixer": "split_paragraph"},
        "evidence_refs": [f"{doc_id}/evidence/p0003/b001.json"],
        "waived": False,
        "waiver_ref": f"{doc_id}/waivers/w-001.json",
    }
    rec_ref = f"{doc_id}/qa_record.v1/page/p0003/leaky.json"
    _write(root / rec_ref, rec_with_internals)

    summary = {
        "schema_version": "qa_summary.v1",
        "document_id": doc_id,
        "run_id": "run_leaky_123",
        "edition": "ru",
        "counts": {"info": 0, "warning": 1, "error": 0, "critical": 0},
        "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "blocking": False,
        "record_refs": [rec_ref],
        "review_pack_ref": f"{doc_id}/review_pack.v1/document/{doc_id}/pack.json",
        "qa_metrics_ref": f"{doc_id}/qa_metrics.v1/document/{doc_id}/m.json",
    }
    _write(root / doc_id / "qa" / "document" / doc_id / "sum.json", summary)


def test_public_bundle_omits_internal_summary_fields(qa_module: ModuleType, tmp_path: Path) -> None:
    """Guard for the S5U-689 summary-level threat enumeration.

    Red-before confirmation: pre-fix behavior (``scripts/_export_qa.py``
    at main HEAD 0bb1344 writes ``summary = json.loads(latest.read_text())``
    verbatim). Running this test against that script fails on the first
    ``assert field not in summary`` — e.g., ``run_id`` is present with
    value ``"run_leaky_123"``.
    """
    doc_id = "leaky_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    _seed_full_artifacts(artifact_root, doc_id)

    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)

    summary = json.loads((doc_public / "ru" / "data" / "qa_summary.json").read_text())

    for field in SUMMARY_INTERNAL_FIELDS:
        assert field not in summary, (
            f"internal field {field!r} leaked into public qa_summary.json "
            f"(S5U-689 regression): {summary}"
        )

    # The reader still receives everything it needs.
    assert summary["document_id"] == doc_id
    assert summary["edition"] == "ru"
    assert summary["counts"] == {"info": 0, "warning": 1, "error": 0, "critical": 0}
    assert summary["waived_counts"] == {"info": 0, "warning": 0, "error": 0, "critical": 0}
    assert summary["blocking"] is False
    assert summary["schema_version"] == "public_qa_summary.v1"


def test_public_bundle_omits_internal_record_fields(qa_module: ModuleType, tmp_path: Path) -> None:
    """Guard for the S5U-689 record-level threat enumeration.

    Red-before confirmation: pre-fix behavior writes records verbatim via
    ``(out_dir / "qa_records.json").write_text(json.dumps({"records": records}, ...))``
    — so ``auto_fix``, ``evidence_refs``, ``waiver_ref``, ``expected``,
    ``actual`` all appear. Running this test against main HEAD 0bb1344
    fails on the first ``assert field not in record``.
    """
    doc_id = "leaky_doc"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    _seed_full_artifacts(artifact_root, doc_id)

    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)

    records_file = json.loads((doc_public / "ru" / "data" / "qa_records.json").read_text())
    assert records_file["schema_version"] == "public_qa_record_set.v1"
    assert len(records_file["records"]) == 1
    rec = records_file["records"][0]

    for field in RECORD_INTERNAL_FIELDS:
        assert field not in rec, (
            f"internal field {field!r} leaked into public qa_records.json "
            f"(S5U-689 regression): {rec}"
        )

    # Reader-visible fields are preserved.
    assert rec["qa_id"] == "qa.p0003.leaky"
    assert rec["layer"] == "structure"
    assert rec["severity"] == "warning"
    assert rec["code"] == "PARAGRAPH_TOO_LONG"
    assert rec["page_id"] == "p0003"
    assert rec["entity_ref"] == "p0003.b001"
    assert rec["message"].startswith("Block has 3141")
    assert rec["waived"] is False


def test_projection_from_internal_drops_summary_internals() -> None:
    """Direct Pydantic-level guard — the projection strips internal fields.

    Red-before confirmation: N/A — no production code change path; this
    test pins behavior on a new ``from_internal`` classmethod that did
    not exist prior to this PR. If ``from_internal`` drifts to include
    an internal field in the projection, this asserts catches it before
    the full export path does.
    """
    internal = QASummaryV1(
        document_id="doc_a",
        run_id="run_secret",
        edition="en",
        counts=SeverityCounts(error=2),
        blocking=True,
        record_refs=["a/b.json"],
        review_pack_ref="a/pack.json",
        qa_metrics_ref="a/metrics.json",
    )
    projected = PublicQASummaryV1.from_internal(internal)
    dumped = projected.model_dump(mode="json")

    for field in SUMMARY_INTERNAL_FIELDS:
        assert field not in dumped, f"projection leaked {field!r}: {dumped}"
    assert dumped["document_id"] == "doc_a"
    assert dumped["edition"] == "en"
    assert dumped["counts"]["error"] == 2
    assert dumped["blocking"] is True


def test_projection_from_internal_drops_record_internals() -> None:
    """Direct Pydantic-level guard for the record projection.

    Red-before confirmation: N/A — no production code change path; see
    the summary-level counterpart above.
    """
    internal = QARecordV1(
        qa_id="qa.x",
        layer="structure",  # type: ignore[arg-type]
        severity="error",  # type: ignore[arg-type]
        code="X",
        document_id="doc_a",
        page_id="p0001",
        entity_ref="p0001.b0",
        message="msg",
        expected={"a": 1},
        actual={"a": 2},
        auto_fix=AutoFix(available=True, fixer="noop"),
        evidence_refs=["a/ev.json"],
        waiver_ref="a/w.json",
    )
    projected = PublicQARecordV1.from_internal(internal)
    dumped = projected.model_dump(mode="json")

    for field in RECORD_INTERNAL_FIELDS:
        assert field not in dumped, f"record projection leaked {field!r}: {dumped}"
    # Reader-visible fields survive.
    assert dumped["qa_id"] == "qa.x"
    assert dumped["layer"] == "structure"
    assert dumped["severity"] == "error"
    assert dumped["code"] == "X"
    assert dumped["page_id"] == "p0001"
    assert dumped["entity_ref"] == "p0001.b0"
    assert dumped["message"] == "msg"


def test_record_set_projection_is_list_shaped() -> None:
    """``PublicQARecordSetV1.from_internal`` returns a wrapper with records[].

    Red-before confirmation: N/A — new classmethod, pinned shape.
    """
    internals = [
        QARecordV1(
            qa_id=f"qa.{i}",
            layer="structure",  # type: ignore[arg-type]
            severity="info",  # type: ignore[arg-type]
            code="C",
            page_id=f"p{i:04d}",
        )
        for i in range(3)
    ]
    projected = PublicQARecordSetV1.from_internal(internals)
    dumped = projected.model_dump(mode="json")
    assert dumped["schema_version"] == "public_qa_record_set.v1"
    assert [r["qa_id"] for r in dumped["records"]] == ["qa.0", "qa.1", "qa.2"]
