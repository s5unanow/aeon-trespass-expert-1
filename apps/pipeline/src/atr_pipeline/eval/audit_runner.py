"""Full-document extraction audit orchestrator.

Loads all page artifacts for a document, runs invariant checks,
collects per-page diagnostics, and builds a non-blocking audit report.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from atr_pipeline.eval.audit_models import AuditReport, PageAuditResult
from atr_pipeline.eval.invariants import run_invariant_checks
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.resolved_page_v1 import ResolvedPageV1

# Below this threshold a symbol ref is counted as "unresolved".
_UNRESOLVED_CONFIDENCE = 0.5

logger = logging.getLogger(__name__)


def _load_latest_json(store: ArtifactStore, doc_id: str, family: str, page_id: str) -> str | None:
    """Read the latest JSON artifact for a (family, page_id) pair."""
    page_dir = store.root / doc_id / family / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return jsons[-1].read_text()


def _load_resolved(store: ArtifactStore, doc_id: str, page_id: str) -> ResolvedPageV1 | None:
    raw = _load_latest_json(store, doc_id, "resolved_page.v1", page_id)
    return ResolvedPageV1.model_validate(json.loads(raw)) if raw else None


def _load_evidence(store: ArtifactStore, doc_id: str, page_id: str) -> PageEvidenceV1 | None:
    raw = _load_latest_json(store, doc_id, "page_evidence.v1", page_id)
    return PageEvidenceV1.model_validate(json.loads(raw)) if raw else None


def _load_layout(store: ArtifactStore, doc_id: str, page_id: str) -> LayoutPageV1 | None:
    raw = _load_latest_json(store, doc_id, "layout_page.v1", page_id)
    return LayoutPageV1.model_validate(json.loads(raw)) if raw else None


def _discover_all_pages(store: ArtifactStore, document_id: str) -> list[str]:
    """Discover page IDs from the broadest available artifact families."""
    page_ids: set[str] = set()
    for family in (
        "native_page.v1",
        "resolved_page.v1",
        "page_ir.v1.en",
        "layout_page.v1",
    ):
        page_root = store.root / document_id / family / "page"
        if page_root.exists():
            page_ids.update(d.name for d in page_root.iterdir() if d.is_dir())
    return sorted(page_ids)


def _audit_page(
    store: ArtifactStore,
    document_id: str,
    page_id: str,
) -> PageAuditResult | None:
    """Collect diagnostics for a single page. Returns None if no artifacts exist."""
    resolved = _load_resolved(store, document_id, page_id)
    if resolved is None:
        return None

    evidence = _load_evidence(store, document_id, page_id)
    layout = _load_layout(store, document_id, page_id)

    # Block and symbol counts
    block_count = len(resolved.blocks)
    symbol_count = len(resolved.symbol_refs) + sum(len(b.symbol_refs) for b in resolved.blocks)
    unresolved_symbol_count = sum(
        1 for ref in resolved.symbol_refs if ref.confidence < _UNRESOLVED_CONFIDENCE
    ) + sum(
        1
        for b in resolved.blocks
        for ref in b.symbol_refs
        if ref.confidence < _UNRESOLVED_CONFIDENCE
    )

    # Fallback usage
    fallback_block_count = sum(1 for b in resolved.blocks if b.fallback is not None)

    # Difficulty / routing from layout
    hard_page = False
    recommended_route = ""
    if layout and layout.difficulty:
        hard_page = layout.difficulty.hard_page
        recommended_route = layout.difficulty.recommended_route

    # Invariant checks
    records = run_invariant_checks(resolved, evidence)
    issue_counts: dict[str, int] = {}
    for r in records:
        issue_counts[r.code] = issue_counts.get(r.code, 0) + 1

    reading_order_failure = "DANGLING_FLOW_REF" in issue_counts

    return PageAuditResult(
        page_id=page_id,
        block_count=block_count,
        symbol_count=symbol_count,
        unresolved_symbol_count=unresolved_symbol_count,
        fallback_block_count=fallback_block_count,
        hard_page=hard_page,
        recommended_route=recommended_route,
        invariant_issue_counts=issue_counts,
        reading_order_failure=reading_order_failure,
    )


def _load_baseline(baseline_path: Path) -> AuditReport | None:
    """Load a previous audit report as a comparison baseline."""
    if not baseline_path.exists():
        return None
    try:
        return AuditReport.model_validate(json.loads(baseline_path.read_text()))
    except (json.JSONDecodeError, ValueError, OSError):
        logger.warning("failed to load baseline: %s", baseline_path, exc_info=True)
        return None


def _compute_delta(current: dict[str, int], baseline: dict[str, int]) -> dict[str, float]:
    """Compute issue-count delta between current and baseline."""
    all_keys = sorted(set(current) | set(baseline))
    delta: dict[str, float] = {}
    for key in all_keys:
        cur = current.get(key, 0)
        base = baseline.get(key, 0)
        delta[key] = float(cur - base)
    return delta


def run_audit(
    *,
    document_id: str,
    store: ArtifactStore,
    page_filter: list[str] | None = None,
    baseline_path: Path | None = None,
) -> AuditReport:
    """Run a full-document extraction audit.

    Iterates over all pages (or a filtered subset), collects
    diagnostics per page, and builds an aggregate report.
    This is non-blocking by design — it never causes CI failure.

    Args:
        document_id: Document to audit.
        store: Artifact store containing extraction outputs.
        page_filter: Optional list of page IDs to limit scope.
        baseline_path: Optional path to a previous audit report for delta.

    Returns:
        AuditReport with per-page and aggregate diagnostics.
    """
    all_pages = _discover_all_pages(store, document_id)
    if page_filter:
        filter_set = set(page_filter)
        pages_to_audit = [p for p in all_pages if p in filter_set]
    else:
        pages_to_audit = all_pages

    page_results: list[PageAuditResult] = []
    pages_missing = 0

    for page_id in pages_to_audit:
        result = _audit_page(store, document_id, page_id)
        if result is None:
            pages_missing += 1
            logger.warning("no resolved artifacts for page %s", page_id)
            continue
        page_results.append(result)

    # Aggregate
    total_issues: dict[str, int] = {}
    fallback_pages: list[str] = []
    hard_pages: list[str] = []
    invariant_pages: list[str] = []
    ro_failure_pages: list[str] = []

    for p in page_results:
        for code, count in p.invariant_issue_counts.items():
            total_issues[code] = total_issues.get(code, 0) + count
        if p.fallback_block_count > 0:
            fallback_pages.append(p.page_id)
        if p.hard_page:
            hard_pages.append(p.page_id)
        if p.invariant_issue_counts:
            invariant_pages.append(p.page_id)
        if p.reading_order_failure:
            ro_failure_pages.append(p.page_id)

    # Baseline delta
    baseline_snapshot_id: str | None = None
    baseline_delta: dict[str, float] | None = None
    if baseline_path:
        baseline = _load_baseline(baseline_path)
        if baseline:
            baseline_snapshot_id = baseline.timestamp
            baseline_delta = _compute_delta(total_issues, baseline.total_issue_counts)

    return AuditReport(
        document_id=document_id,
        timestamp=datetime.now(tz=UTC).isoformat(),
        pages_in_scope=len(pages_to_audit),
        pages_audited=len(page_results),
        pages_missing_ir=pages_missing,
        pages=page_results,
        total_issue_counts=total_issues,
        fallback_route_pages=fallback_pages,
        hard_pages=hard_pages,
        invariant_failure_pages=invariant_pages,
        reading_order_failure_pages=ro_failure_pages,
        baseline_snapshot_id=baseline_snapshot_id,
        baseline_delta=baseline_delta,
    )
