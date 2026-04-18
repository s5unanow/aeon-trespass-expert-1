"""Export QA artifacts (QASummaryV1 + QARecordV1 records) to the web bundle.

Selects the latest `QASummaryV1` for a document (by mtime), resolves the
referenced `QARecordV1` artifacts, and writes two JSON files into the
edition-scoped bundle:

- ``<edition>/data/qa_summary.json`` — the `QASummaryV1` payload verbatim.
- ``<edition>/data/qa_records.json`` — ``{"records": [QARecordV1, ...]}``
  (wrapped in an object so future metadata can be added without a breaking
  change).

QA is document-level (not edition-scoped), but the files are published under
each edition so the reader can fetch them with a uniform URL shape identical
to ``glossary.json``. Re-running the export overwrites the files in place,
preserving idempotency.
"""

from __future__ import annotations

import json
from pathlib import Path


def _pick_latest_summary(summary_dir: Path) -> Path | None:
    """Return the newest summary artifact in *summary_dir* or None if empty."""
    files = list(summary_dir.glob("*.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _load_records(artifact_root: Path, record_refs: list[str]) -> list[dict]:
    """Resolve each relative ref to its JSON payload.

    Missing files are skipped silently; this can happen when a record was
    deleted between runs. Corrupt JSON raises (fail fast).
    """
    records: list[dict] = []
    for ref in record_refs:
        rec_path = artifact_root / ref
        if not rec_path.is_file():
            continue
        records.append(json.loads(rec_path.read_text()))
    return records


def export_qa(
    artifact_root: Path,
    doc_id: str,
    edition: str,
    doc_public: Path,
) -> int:
    """Write qa_summary.json + qa_records.json to the edition data dir.

    Returns the number of records exported. Returns 0 (and prints a notice)
    if no summary artifact is found.
    """
    summary_dir = artifact_root / doc_id / "qa" / "document" / doc_id
    out_dir = doc_public / edition / "data"

    if not summary_dir.is_dir():
        print(f"  [{edition.upper()}] No QA summary dir at {summary_dir}, skipping")
        return 0

    latest = _pick_latest_summary(summary_dir)
    if latest is None:
        print(f"  [{edition.upper()}] No QA summary artifacts, skipping")
        return 0

    summary = json.loads(latest.read_text())
    record_refs: list[str] = summary.get("record_refs", [])
    records = _load_records(artifact_root, record_refs)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qa_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (out_dir / "qa_records.json").write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2)
    )

    print(f"  [{edition.upper()}] Exported QA summary + {len(records)} records")
    return len(records)
