"""Tests for scripts/ingest_user_feedback.py + the shared user-feedback helpers.

After S5U-605 the ingest script routes records through ``ArtifactStore``
instead of a flat ``artifacts/qa_records/user_feedback/`` directory, and the
record conversion lives in ``atr_pipeline.stages.qa.user_feedback``. These
tests pin both the shared helpers and the script's public behaviour.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from atr_pipeline.stages.qa.user_feedback import (
    feedback_to_qa_record,
    load_user_feedback_records,
    persist_submissions,
    schema_family_for,
)
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, Severity
from atr_schemas.feedback_submission_v1 import FeedbackSubmissionV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.user_feedback_record_set_v1 import UserFeedbackRecordSetV1

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


# ---------------------------------------------------------------------------
# Helper-level behaviour
# ---------------------------------------------------------------------------


def test_feedback_to_qa_record_shape() -> None:
    submission = FeedbackSubmissionV1.model_validate(_submission())
    record = feedback_to_qa_record(submission, source_file="foo.json")
    assert isinstance(record, QARecordV1)
    assert record.layer == QALayer.USER_FEEDBACK
    assert record.severity == Severity.INFO
    assert record.page_id == "p0042"
    assert record.document_id == "ato_core_v1_1"
    assert record.code == "USER_FEEDBACK_TRANSLATION"
    assert "Wrong term" in record.message
    assert record.actual is not None
    assert record.actual["source_file"] == "foo.json"
    assert record.actual["edition"] == "ru"


def test_feedback_to_qa_record_empty_note_allowed() -> None:
    submission = FeedbackSubmissionV1.model_validate(_submission(note=""))
    record = feedback_to_qa_record(submission, source_file="x.json")
    assert record.message == "Reader feedback (translation)"


def test_schema_family_for_is_edition_suffixed() -> None:
    assert schema_family_for("ru") == "user_feedback_record_set.v1.ru"
    assert schema_family_for("en") == "user_feedback_record_set.v1.en"


def test_persist_submissions_groups_and_roundtrips(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    submissions = [
        (FeedbackSubmissionV1.model_validate(_submission()), "a.json"),
        (
            FeedbackSubmissionV1.model_validate(
                _submission(
                    issue_type="rendering",
                    note="overlap",
                    timestamp="2026-04-18T13:00:00.000Z",
                )
            ),
            "b.json",
        ),
        # Different edition for the same page → must land in a separate set.
        (
            FeedbackSubmissionV1.model_validate(
                _submission(edition="en", timestamp="2026-04-18T14:00:00.000Z")
            ),
            "c.json",
        ),
    ]

    written = persist_submissions(store=store, submissions=submissions)
    assert set(written) == {
        ("ato_core_v1_1", "ru", "p0042"),
        ("ato_core_v1_1", "en", "p0042"),
    }

    ru_records = load_user_feedback_records(
        store=store,
        document_id="ato_core_v1_1",
        edition="ru",
        page_id="p0042",
    )
    en_records = load_user_feedback_records(
        store=store,
        document_id="ato_core_v1_1",
        edition="en",
        page_id="p0042",
    )
    assert len(ru_records) == 2
    assert len(en_records) == 1
    # Confirm the artifact layout — proves we're using ArtifactStore, not
    # a flat directory.
    ru_dir = tmp_path / "ato_core_v1_1" / "user_feedback_record_set.v1.ru" / "page" / "p0042"
    assert ru_dir.is_dir()
    # Exactly one content-addressed JSON per (page, edition) group.
    assert len(list(ru_dir.glob("*.json"))) == 1


def test_load_user_feedback_records_missing_returns_empty(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    records = load_user_feedback_records(
        store=store,
        document_id="nope",
        edition="ru",
        page_id="p0001",
    )
    assert records == []


# ---------------------------------------------------------------------------
# Script-level behaviour
# ---------------------------------------------------------------------------


def test_ingest_directory_writes_via_artifact_store(ingest_mod: ModuleType, tmp_path: Path) -> None:
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
    store = ArtifactStore(tmp_path / "artifacts")

    written = ingest_mod.ingest_directory(feedback_dir, store)

    assert set(written) == {
        ("ato_core_v1_1", "ru", "p0042"),
        ("ato_core_v1_1", "ru", "p0100"),
    }
    # The orphan flat directory the old script used must not be created.
    legacy = tmp_path / "artifacts" / "qa_records" / "user_feedback"
    assert not legacy.exists()


def test_ingest_directory_skips_invalid_json(ingest_mod: ModuleType, tmp_path: Path) -> None:
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "good.json").write_text(json.dumps(_submission()))
    (feedback_dir / "bad.json").write_text("{not valid json")
    (feedback_dir / "missing-fields.json").write_text(json.dumps({"document_id": "x"}))

    store = ArtifactStore(tmp_path / "artifacts")
    written = ingest_mod.ingest_directory(feedback_dir, store)
    assert len(written) == 1


def test_ingest_is_idempotent(ingest_mod: ModuleType, tmp_path: Path) -> None:
    feedback_dir = tmp_path / "feedback"
    feedback_dir.mkdir()
    (feedback_dir / "one.json").write_text(json.dumps(_submission()))
    store = ArtifactStore(tmp_path / "artifacts")

    first = ingest_mod.ingest_directory(feedback_dir, store)
    second = ingest_mod.ingest_directory(feedback_dir, store)
    assert first == second

    entity_dir = (
        tmp_path
        / "artifacts"
        / "ato_core_v1_1"
        / "user_feedback_record_set.v1.ru"
        / "page"
        / "p0042"
    )
    # ArtifactStore is content-addressed: identical content → single file.
    assert len(list(entity_dir.glob("*.json"))) == 1


def test_ingest_no_print_calls_remain(ingest_mod: ModuleType) -> None:
    """S5U-602 regression: the script must not use bare ``print``.

    Diagnostics flow through ``structlog`` so pipeline logging conventions
    apply uniformly.
    """
    src = SCRIPT_PATH.read_text()
    assert "print(" not in src


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


def test_s5u_607_path_traversal_repro_still_blocked(ingest_mod: ModuleType, tmp_path: Path) -> None:
    """Regression for S5U-607: path-traversal ``page_id`` is still rejected.

    After S5U-605 the writer is ``ArtifactStore.put_json``, which refuses to
    resolve outside its root anyway, but the primary defence is still the
    ``FeedbackSubmissionV1`` pattern validation.
    """
    feedback_dir = tmp_path / "fb"
    feedback_dir.mkdir()
    store_root = tmp_path / "artifacts"
    escape_dir = tmp_path / "escape"
    (feedback_dir / "evil.json").write_text(
        json.dumps(
            {
                "schema_version": "user_feedback.v1",
                "document_id": "ato_core_v1_1",
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

    store = ArtifactStore(store_root)
    written = ingest_mod.ingest_directory(feedback_dir, store)

    assert written == []
    assert not escape_dir.exists()


def test_user_feedback_record_set_schema_rejects_bad_page_id() -> None:
    """Belt-and-braces at the schema layer too."""
    with pytest.raises(ValidationError):
        UserFeedbackRecordSetV1.model_validate(
            {
                "document_id": "x",
                "edition": "ru",
                "page_id": "../pwn",
                "records": [],
            }
        )
