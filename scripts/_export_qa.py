"""Export QA artifacts (QASummaryV1 + QARecordV1 records + QAMetricsV1) to the web bundle.

Selects the latest `QASummaryV1` whose ``edition`` matches the requested
edition, resolves the referenced `QARecordV1` artifacts, and writes three JSON
files into the edition-scoped bundle:

- ``<edition>/data/qa_summary.json`` — a `PublicQASummaryV1` projection of
  the internal summary. Internal fields (``run_id``, ``record_refs``,
  ``review_pack_ref``, ``qa_metrics_ref``) are stripped at the export
  boundary — the reader only needs counts + blocking flag.
- ``<edition>/data/qa_records.json`` — a `PublicQARecordSetV1` projection
  wrapping the records. Internal provenance/fixer fields (``auto_fix``,
  ``evidence_refs``, ``waiver_ref``, ``expected``, ``actual``, record-level
  ``schema_version``, ``document_id``) are stripped.
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

Public-DTO projection (S5U-689): the pipeline artifact store continues to
hold the full internal ``QASummaryV1`` / ``QARecordV1``; only the bundle
published under ``apps/web/public`` is narrowed. Regression test
``test_public_bundle_omits_internal_fields`` asserts the blocked-key set
is absent from the on-disk public JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from atr_schemas.public_qa_record_set_v1 import PublicQARecordSetV1
from atr_schemas.public_qa_summary_v1 import PublicQASummaryV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1


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
    summary_path: Path | None = None,
    *,
    ref_bound: bool = False,
) -> int:
    """Write qa_summary.json + qa_records.json to the edition data dir.

    Returns the number of records exported. Returns 0 (and prints a notice)
    if no summary artifact is found.

    Ref-bound mode (S5U-869): callers pass ``ref_bound=True`` together with the
    QA summary artifact resolved from the *single* exported run. In this mode
    the legacy mtime-based ``_pick_summary_for_edition`` directory scan is never
    used: a supplied ``summary_path`` is exported verbatim, and ``summary_path
    is None`` means "the run carried no QA artifact" → skip QA, **never**
    mtime-fall-back to another run's summary. The caller refuses (non-zero exit)
    when a bound run advertises a QA summary whose file is missing on disk
    (``resolve_qa_summary_path``), so this function never sees a stray summary.

    Legacy mode (``ref_bound=False``, ``summary_path=None``) preserves the
    directory-scan path for callers that have not migrated to run binding.
    """
    out_dir = doc_public / edition / "data"

    if summary_path is not None:
        latest: Path | None = summary_path
    elif ref_bound:
        # Run-bound export with no QA artifact for this run — QA was not part of
        # the resolved run. Skip rather than mtime-splicing a foreign summary.
        print(f"  [{edition.upper()}] Run carries no QA summary, skipping QA export")
        return 0
    else:
        summary_dir = artifact_root / doc_id / "qa" / "document" / doc_id
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

    # Project to public DTOs (S5U-689): the pipeline artifact store keeps the
    # full internal shape, but the published bundle must omit run identifiers
    # and artifact-store refs.
    internal_summary = QASummaryV1.model_validate(summary)
    internal_records = [QARecordV1.model_validate(r) for r in records]
    public_summary = PublicQASummaryV1.from_internal(internal_summary)
    public_records = PublicQARecordSetV1.from_internal(internal_records)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "qa_summary.json").write_text(
        json.dumps(public_summary.model_dump(mode="json"), ensure_ascii=False, indent=2)
    )
    (out_dir / "qa_records.json").write_text(
        json.dumps(public_records.model_dump(mode="json"), ensure_ascii=False, indent=2)
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
