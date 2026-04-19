"""Export QA artifacts (QASummaryV1 + QARecordV1 records + QAMetricsV1) to the web bundle.

Selects the latest `QASummaryV1` whose ``edition`` matches the requested
edition, resolves the referenced `QARecordV1` artifacts, and writes three JSON
files into the edition-scoped bundle:

- ``<edition>/data/qa_summary.json`` — the `QASummaryV1` payload verbatim.
- ``<edition>/data/qa_records.json`` — ``{"records": [QARecordV1, ...]}``
  (wrapped in an object so future metadata can be added without a breaking
  change).
- ``<edition>/data/qa_metrics.json`` — the latest edition-matched
  `QAMetricsV1` payload verbatim (S5U-597). Written only when a metrics
  artifact exists; older runs predating metrics emission silently skip.

The QA stage runs per edition (`ctx.edition`) — EN produces structural
findings only, RU additionally emits translation QA — but both write into
the same artifact directory keyed by ``schema_family=qa`` / ``entity_id=doc_id``.
This module disambiguates them by reading the ``edition`` field embedded in
each summary (populated by the QA stage). For backwards compatibility with
summaries produced before the field was added, an untagged summary
(``edition == ""``) is accepted only when *no* tagged summary exists —
mirroring the render-page selection logic in ``export_to_web._pick_latest``.
Re-running the export overwrites the files in place, preserving idempotency.
"""

from __future__ import annotations

import json
from pathlib import Path


def _pick_summary_for_edition(summary_dir: Path, edition: str) -> Path | None:
    """Return the newest summary artifact matching *edition*.

    Selection rules (two tiers):

    1. Prefer the newest summary whose payload contains ``edition == edition``.
    2. Fall back to the newest untagged summary (``edition == ""``) *only*
       when no tagged summaries are present in the directory. Once any
       tagged summary exists the fallback is suppressed — this prevents a
       stale pre-tagging summary from being picked up ahead of a tagged
       summary for the *other* edition.
    """
    files = list(summary_dir.glob("*.json"))
    if not files:
        return None

    best_match: Path | None = None
    best_match_mtime: float = 0.0
    best_untagged: Path | None = None
    best_untagged_mtime: float = 0.0
    has_any_tagged = False

    for path in files:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        payload_edition = data.get("edition", "")
        mtime = path.stat().st_mtime
        if payload_edition == edition:
            if mtime > best_match_mtime:
                best_match = path
                best_match_mtime = mtime
        elif payload_edition != "":
            has_any_tagged = True
        elif mtime > best_untagged_mtime:
            best_untagged = path
            best_untagged_mtime = mtime

    if best_match is not None:
        return best_match
    if not has_any_tagged:
        return best_untagged
    return None


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

    latest = _pick_summary_for_edition(summary_dir, edition)
    if latest is None:
        print(f"  [{edition.upper()}] No QA summary artifacts for edition, skipping")
        return 0

    summary = json.loads(latest.read_text())
    record_refs: list[str] = summary.get("record_refs", [])
    records = _load_records(artifact_root, record_refs)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qa_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (out_dir / "qa_records.json").write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2)
    )

    metrics_exported = _export_metrics(artifact_root, doc_id, edition, out_dir, summary)
    metrics_note = " + metrics" if metrics_exported else ""
    print(f"  [{edition.upper()}] Exported QA summary + {len(records)} records{metrics_note}")
    return len(records)


def _export_metrics(
    artifact_root: Path,
    doc_id: str,
    edition: str,
    out_dir: Path,
    summary: dict,
) -> bool:
    """Write qa_metrics.json for the metrics artifact paired with *summary*.

    Selection (S5U-641):

    1. Prefer ``summary["qa_metrics_ref"]`` — the exact metrics artifact
       bound to this summary by the QA stage. This prevents pairing an
       authoritative summary with a stray metrics file from an interrupted
       prior run.
    2. Fall back to latest-by-mtime edition-matched selection **only** for
       legacy summaries (pre-S5U-641) that have no ``qa_metrics_ref``.
       This preserves export behavior for older artifact stores.

    Returns ``True`` when a metrics artifact was written, ``False`` otherwise
    (older runs emit no metrics, or the ref points at a missing file; both
    are non-fatal — export continues without metrics).
    """
    ref = summary.get("qa_metrics_ref", "") or ""
    if ref:
        target = artifact_root / ref
        if not target.is_file():
            # The summary claims a specific artifact but it's gone — log and
            # skip rather than silently substituting a stray. This is an
            # artifact-store corruption case, not a legacy-data case.
            print(f"  [{edition.upper()}] qa_metrics_ref={ref!r} missing; skipping metrics")
            return False
        payload = json.loads(target.read_text())
        (out_dir / "qa_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return True

    # Legacy fallback (summary has no ref field — pre-S5U-641 artifact).
    metrics_dir = artifact_root / doc_id / "qa_metrics.v1" / "document" / doc_id
    if not metrics_dir.is_dir():
        return False
    latest = _pick_summary_for_edition(metrics_dir, edition)
    if latest is None:
        return False
    payload = json.loads(latest.read_text())
    (out_dir / "qa_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return True
