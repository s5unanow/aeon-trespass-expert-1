"""Waiver loading and matching for QA records."""

from __future__ import annotations

import json
from pathlib import Path

from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.waiver_v1 import WaiverSetV1, WaiverV1


def load_waivers(waivers_dir: Path, document_id: str) -> list[WaiverV1]:
    """Load waivers for a document from the waivers directory.

    Looks for ``{waivers_dir}/{document_id}.json``.
    Returns an empty list if the file does not exist.
    """
    waiver_file = waivers_dir / f"{document_id}.json"
    if not waiver_file.exists():
        return []
    data = json.loads(waiver_file.read_text(encoding="utf-8"))
    waiver_set = WaiverSetV1.model_validate(data)
    return list(waiver_set.waivers)


def apply_waivers(
    records: list[QARecordV1],
    waivers: list[WaiverV1],
) -> list[QARecordV1]:
    """Apply matching waivers to QA records.

    A waiver matches a record when:
    - ``waiver.code == record.code``
    - ``waiver.page_id`` is ``None`` (matches all pages) or equals ``record.page_id``

    Returns a new list with matched records marked as waived.
    """
    if not waivers:
        return records

    index: dict[str, list[WaiverV1]] = {}
    for w in waivers:
        index.setdefault(w.code, []).append(w)

    result: list[QARecordV1] = []
    for record in records:
        matching = _find_waiver(record, index)
        if matching is not None:
            record = record.model_copy(
                update={"waived": True, "waiver_ref": matching.waiver_id},
            )
        result.append(record)
    return result


def _find_waiver(
    record: QARecordV1,
    index: dict[str, list[WaiverV1]],
) -> WaiverV1 | None:
    """Find the first matching waiver for a record."""
    candidates = index.get(record.code, [])
    for w in candidates:
        if w.page_id is None or w.page_id == record.page_id:
            return w
    return None
