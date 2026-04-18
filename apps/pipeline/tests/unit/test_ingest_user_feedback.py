"""Tests for scripts/ingest_user_feedback.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "ingest_user_feedback.py"


@pytest.fixture()
def ingest_mod() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("ingest_user_feedback_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ingest_user_feedback_test"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("ingest_user_feedback_test", None)


def _submission(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "user_feedback.v1",
        "document_id": "ato_core_v1_1",
        "edition": "ru",
        "page_id": "p0042",
        "issue_type": "translation",
        "note": "Wrong term for Ikarus.",
        "url": "http://localhost:3001/documents/ato_core_v1_1/ru/p0042",
        "user_agent": "Mozilla/5.0",
        "timestamp": "2026-04-18T12:34:56.000Z",
    }
    base.update(overrides)
    return base


def test_feedback_to_qa_record_shape(ingest_mod: ModuleType) -> None:
    submission = ingest_mod.FeedbackSubmission.model_validate(_submission())
    record = ingest_mod.feedback_to_qa_record(submission, source_file="foo.json")
    assert isinstance(record, QARecordV1)
    assert record.layer == QALayer.USER_FEEDBACK
    assert record.severity == Severity.INFO
    assert record.page_id == "p0042"
    assert record.document_id == "ato_core_v1_1"
    assert record.code == "USER_FEEDBACK_TRANSLATION"
    assert "Wrong term" in record.message
    assert record.actual is not None
    assert record.actual["source_file"] == "foo.json"


def test_feedback_to_qa_record_empty_note_allowed(ingest_mod: ModuleType) -> None:
    submission = ingest_mod.FeedbackSubmission.model_validate(_submission(note=""))
    record = ingest_mod.feedback_to_qa_record(submission, source_file="x.json")
    assert record.message == "Reader feedback (translation)"


def test_ingest_directory_end_to_end(ingest_mod: ModuleType, tmp_path: Path) -> None:
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "one.json").write_text(json.dumps(_submission()))
    (feedback_dir / "two.json").write_text(
        json.dumps(
            _submission(
                page_id="p0100",
                issue_type="rendering",
                timestamp="2026-04-18T13-00-00-000Z",
            )
        )
    )
    output_dir = tmp_path / "out"

    written = ingest_mod.ingest_directory(feedback_dir, output_dir)

    assert len(written) == 2
    for path in written:
        data = json.loads(path.read_text())
        QARecordV1.model_validate(data)
        assert data["layer"] == "user_feedback"
        assert data["severity"] == "info"


def test_ingest_directory_skips_invalid_json(
    ingest_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "good.json").write_text(json.dumps(_submission()))
    (feedback_dir / "bad.json").write_text("{not valid json")
    (feedback_dir / "missing-fields.json").write_text(json.dumps({"document_id": "x"}))

    output_dir = tmp_path / "out"
    written = ingest_mod.ingest_directory(feedback_dir, output_dir)

    assert len(written) == 1
    err = capsys.readouterr().err
    assert "SKIP bad.json" in err
    assert "SKIP missing-fields.json" in err


def test_ingest_is_idempotent(ingest_mod: ModuleType, tmp_path: Path) -> None:
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "one.json").write_text(json.dumps(_submission()))
    output_dir = tmp_path / "out"

    first = ingest_mod.ingest_directory(feedback_dir, output_dir)
    second = ingest_mod.ingest_directory(feedback_dir, output_dir)
    assert first == second  # stable paths based on qa_id
    assert len(list(output_dir.iterdir())) == 1
