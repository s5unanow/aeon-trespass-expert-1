"""Tests for scripts/ingest_user_feedback.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from atr_schemas.enums import QALayer, Severity
from atr_schemas.feedback_submission_v1 import FeedbackSubmissionV1
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
                timestamp="2026-04-18T13:00:00.000Z",
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


# ---------------------------------------------------------------------------
# Input-validation adversarial coverage (S5U-607)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,bad_value",
    [
        # page_id: path traversal, absolute path, wrong shape, too long.
        ("page_id", "../escape/pwn"),
        ("page_id", "/etc/passwd"),
        ("page_id", "p42"),  # too short
        ("page_id", "p00042a"),  # trailing non-digit
        ("page_id", "P0042"),  # wrong case
        ("page_id", "p0042\x00"),  # null byte
        ("page_id", "p" + "9" * 1024),  # very long
        # document_id: uppercase, dots, slashes, dots-dot, huge.
        ("document_id", "ATO_CORE"),
        ("document_id", "ato.core"),
        ("document_id", "../etc"),
        ("document_id", "a" * 65),
        # edition: wrong length, digits, traversal.
        ("edition", "rus"),
        ("edition", "r1"),
        ("edition", ".."),
        # issue_type: not in the enum (TS union is 4 values).
        ("issue_type", "exploit"),
        ("issue_type", ""),
        # timestamp: unparseable, path separators, way too long.
        ("timestamp", "not-a-date"),
        ("timestamp", "2026/04/18"),
        ("timestamp", "../2026-01-01T00:00:00Z"),
        ("timestamp", "2026-01-01T00:00:00Z" + "X" * 128),
    ],
)
def test_feedback_submission_rejects_malicious_fields(field: str, bad_value: str) -> None:
    payload = {
        "schema_version": "user_feedback.v1",
        "document_id": "ato_core_v1_1",
        "edition": "ru",
        "page_id": "p0042",
        "issue_type": "translation",
        "note": "",
        "url": "",
        "user_agent": "",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    payload[field] = bad_value
    with pytest.raises(ValidationError):
        FeedbackSubmissionV1.model_validate(payload)


def test_feedback_submission_caps_long_free_text_fields() -> None:
    payload = {
        "schema_version": "user_feedback.v1",
        "document_id": "ato_core_v1_1",
        "edition": "ru",
        "page_id": "p0042",
        "issue_type": "translation",
        "note": "x" * 5000,
        "url": "",
        "user_agent": "",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        FeedbackSubmissionV1.model_validate(payload)


def test_s5u_607_path_traversal_repro_now_fails_cleanly(
    ingest_mod: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression for S5U-607: the exact repro from the Linear issue.

    Before the fix, ``page_id="../escape/pwn"`` would either crash with
    ``FileNotFoundError`` (pre-S5U-602) or — after atomic-write lands —
    silently write outside ``--output-dir``. Now it must be rejected at
    validation time with nothing written anywhere.
    """
    feedback_dir = tmp_path / "fb"
    feedback_dir.mkdir()
    output_dir = tmp_path / "out"
    escape_dir = tmp_path / "escape"
    (feedback_dir / "evil.json").write_text(
        json.dumps(
            {
                "schema_version": "user_feedback.v1",
                "document_id": "x",  # also invalid — but page_id fires first
                "edition": "ru",
                "page_id": "../escape/pwn",
                "issue_type": "translation",
                "note": "",
                "url": "",
                "user_agent": "",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
    )

    written = ingest_mod.ingest_directory(feedback_dir, output_dir)

    assert written == []
    assert not escape_dir.exists(), "path-traversal sink must not be reachable"
    # output_dir is created by mkdir(parents=True) but must contain nothing.
    assert list(output_dir.iterdir()) == []
    err = capsys.readouterr().err
    assert "SKIP evil.json" in err


def test_safe_output_path_rejects_escaping_qa_id(ingest_mod: ModuleType, tmp_path: Path) -> None:
    """Belt-and-braces: even if a bad ``qa_id`` slips past validation,
    ``_safe_output_path`` refuses to resolve outside the output dir."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    with pytest.raises(ValueError, match="escapes output dir"):
        ingest_mod._safe_output_path(output_dir, "../pwn")
