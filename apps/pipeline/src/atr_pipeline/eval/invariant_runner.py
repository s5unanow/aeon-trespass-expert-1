"""Invariant verification orchestrator — loads artifacts, runs checks, builds report."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from atr_pipeline.eval.invariant_models import PageVerificationResult, VerificationReport
from atr_pipeline.eval.invariants import run_invariant_checks
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import Severity
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.resolved_page_v1 import ResolvedPageV1

logger = logging.getLogger(__name__)


def load_resolved_page(
    store: ArtifactStore,
    document_id: str,
    page_id: str,
) -> ResolvedPageV1 | None:
    """Load the latest resolved page from the artifact store."""
    data = store.load_latest_json(
        document_id=document_id, schema_family="resolved_page.v1", scope="page", entity_id=page_id
    )
    return ResolvedPageV1.model_validate(data) if data else None


def load_evidence_page(
    store: ArtifactStore,
    document_id: str,
    page_id: str,
) -> PageEvidenceV1 | None:
    """Load the latest evidence page from the artifact store."""
    data = store.load_latest_json(
        document_id=document_id, schema_family="page_evidence.v1", scope="page", entity_id=page_id
    )
    return PageEvidenceV1.model_validate(data) if data else None


def _discover_pages(store: ArtifactStore, document_id: str) -> list[str]:
    """Discover page IDs that have resolved artifacts."""
    page_root = store.root / document_id / "resolved_page.v1" / "page"
    if not page_root.exists():
        return []
    return sorted(d.name for d in page_root.iterdir() if d.is_dir())


def run_verification(
    *,
    document_id: str,
    store: ArtifactStore,
    page_filter: list[str] | None = None,
) -> VerificationReport:
    """Run invariant checks on all (or filtered) resolved pages.

    Args:
        document_id: Document to verify.
        store: Artifact store for loading pages.
        page_filter: Optional list of page IDs to check.

    Returns:
        VerificationReport with per-page results and severity counts.
    """
    all_pages = _discover_pages(store, document_id)
    if page_filter:
        filter_set = set(page_filter)
        pages_to_check = [p for p in all_pages if p in filter_set]
    else:
        pages_to_check = all_pages

    page_results: list[PageVerificationResult] = []
    severity_totals: dict[str, int] = {}

    for page_id in pages_to_check:
        resolved = load_resolved_page(store, document_id, page_id)
        if resolved is None:
            logger.warning("resolved page missing: page_id=%s doc=%s", page_id, document_id)
            continue

        evidence = load_evidence_page(store, document_id, page_id)
        records = run_invariant_checks(resolved, evidence)

        for r in records:
            severity_totals[r.severity] = severity_totals.get(r.severity, 0) + 1

        page_passed = not any(r.severity in {Severity.ERROR, Severity.CRITICAL} for r in records)
        page_results.append(
            PageVerificationResult(page_id=page_id, records=records, passed=page_passed)
        )

    blocking = any(not p.passed for p in page_results)
    all_passed = not blocking

    return VerificationReport(
        document_id=document_id,
        timestamp=datetime.now(tz=UTC).isoformat(),
        pages=page_results,
        severity_counts=severity_totals,
        blocking=blocking,
        passed=all_passed,
    )
