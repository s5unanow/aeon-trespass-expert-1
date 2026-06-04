"""Blocking-QA gate for the `make export` path (S5U-870).

Extracted from ``export_to_web`` so the entry script stays within the
400-line file-length budget. This module is a thin, ref-bound adapter: it
loads the resolved run's QA summary + records (never an mtime pick across
runs) and delegates the actual refuse/draft decision to the shared
``atr_pipeline.stages.publish.qa_gate.evaluate_qa_gate`` used by the
PublishStage and (in spirit) the ``atr release`` paths.

Fail-closed contract (`.claude/rules/guards.md` Rule G1): a complete run with
no resolvable QA summary refuses (the shared gate raises ``QAGateError``),
never "pass by absent state". ``review_only`` is threaded down ONLY from the
explicit argparse flag — this module never reads an env var, so an ambient
toggle cannot flip the gate's default (the issue's must-refuse env-var row).
"""

from __future__ import annotations

import json
from pathlib import Path

from _export_run import ResolvedRun, load_qa_records, resolve_qa_summary_path

from atr_pipeline.config import load_document_config
from atr_pipeline.stages.publish.qa_gate import QAGateResult, evaluate_qa_gate
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1


def resolve_block_on(doc_id: str) -> set[str]:
    """Load ``QAConfig.block_publish_on`` for the document (default error+critical)."""
    config = load_document_config(doc_id)
    return set(config.qa.block_publish_on)


def enforce_export_qa_gate(
    doc_id: str,
    edition: str,
    resolved: ResolvedRun,
    *,
    artifact_root: Path,
    review_only: bool,
) -> QAGateResult:
    """Run the blocking-QA gate for one resolved edition export.

    Raises ``QAGateError`` to refuse a blocking export unless ``review_only``
    (an explicit CLI flag) is set, in which case a blocking run proceeds as a
    loudly-labeled draft.
    """
    block_on = resolve_block_on(doc_id)
    summary_path = resolve_qa_summary_path(resolved, artifact_root)
    summary: QASummaryV1 | None = None
    records: list[QARecordV1] = []
    if summary_path is not None:
        summary = QASummaryV1.model_validate(json.loads(summary_path.read_text()))
        records = [
            QARecordV1.model_validate(d)
            for d in load_qa_records(summary.record_refs, artifact_root)
        ]
    return evaluate_qa_gate(
        context=f"Export [{edition.upper()}]",
        summary=summary,
        records=records,
        block_on=block_on,
        review_only=review_only,
        run_id=resolved.run_id,
    )


def draft_banner(edition: str, gate_result: QAGateResult) -> str:
    """Loud, operator-facing banner for a review-only draft export."""
    return (
        f"  *** REVIEW-ONLY DRAFT [{edition.upper()}]: exporting over BLOCKING QA "
        f"(codes={gate_result.blocking_codes}, pages={gate_result.blocking_pages}). "
        f"This bundle MUST NOT be released as-is. Review pack: "
        f"{gate_result.review_pack_ref or '<none>'} ***"
    )


def stamp_draft_provenance(provenance: dict[str, str], gate_result: QAGateResult) -> dict[str, str]:
    """Stamp the draft disposition into the bundle manifest provenance.

    A no-op for non-draft bundles. For drafts, marks the bundle so the web side
    and any downstream auditor can see it was built over blocking QA.
    """
    if gate_result.is_draft:
        provenance["review_only_draft"] = "true"
        provenance["blocking_qa_codes"] = ",".join(gate_result.blocking_codes)
    return provenance
