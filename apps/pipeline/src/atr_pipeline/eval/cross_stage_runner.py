"""Cross-stage reference verification orchestrator.

Loads artifacts from multiple pipeline stages, runs cross-stage reference
checks, and builds a verification report.
"""

from __future__ import annotations

from datetime import UTC, datetime

from atr_pipeline.eval.cross_stage_refs import PageArtifacts, run_cross_stage_checks
from atr_pipeline.eval.invariant_models import PageVerificationResult, VerificationReport
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import Severity
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.render_page_v1 import RenderPageV1
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1


def load_native_page(store: ArtifactStore, doc_id: str, page_id: str) -> NativePageV1 | None:
    data = store.load_latest_json(
        document_id=doc_id, schema_family="native_page.v1", scope="page", entity_id=page_id
    )
    return NativePageV1.model_validate(data) if data else None


def load_evidence_page(store: ArtifactStore, doc_id: str, page_id: str) -> PageEvidenceV1 | None:
    data = store.load_latest_json(
        document_id=doc_id, schema_family="page_evidence.v1", scope="page", entity_id=page_id
    )
    return PageEvidenceV1.model_validate(data) if data else None


def load_ir_page(
    store: ArtifactStore, doc_id: str, page_id: str, edition: str = "en"
) -> PageIRV1 | None:
    data = store.load_latest_json(
        document_id=doc_id, schema_family=f"page_ir.v1.{edition}", scope="page", entity_id=page_id
    )
    return PageIRV1.model_validate(data) if data else None


def load_render_page(store: ArtifactStore, doc_id: str, page_id: str) -> RenderPageV1 | None:
    data = store.load_latest_json(
        document_id=doc_id, schema_family="render_page.v1", scope="page", entity_id=page_id
    )
    return RenderPageV1.model_validate(data) if data else None


def load_symbol_matches(store: ArtifactStore, doc_id: str, page_id: str) -> SymbolMatchSetV1 | None:
    data = store.load_latest_json(
        document_id=doc_id, schema_family="symbol_match_set.v1", scope="page", entity_id=page_id
    )
    return SymbolMatchSetV1.model_validate(data) if data else None


def _discover_pages(store: ArtifactStore, document_id: str) -> list[str]:
    """Discover page IDs from the broadest available artifact family."""
    page_ids: set[str] = set()
    for family in ("native_page.v1", "page_ir.v1.en", "render_page.v1"):
        page_root = store.root / document_id / family / "page"
        if page_root.exists():
            page_ids.update(d.name for d in page_root.iterdir() if d.is_dir())
    return sorted(page_ids)


def run_cross_stage_verification(
    *,
    document_id: str,
    store: ArtifactStore,
    page_filter: list[str] | None = None,
) -> VerificationReport:
    """Run cross-stage reference checks on all (or filtered) pages.

    Loads whatever artifacts exist per page and runs applicable checks.
    Missing artifacts are skipped gracefully — only boundaries where
    both sides are present are verified.
    """
    all_pages = _discover_pages(store, document_id)
    if page_filter:
        filter_set = set(page_filter)
        pages_to_check = [p for p in all_pages if p in filter_set]
    else:
        pages_to_check = all_pages

    release_dir = store.root / document_id / "release"
    has_release = release_dir.exists()

    page_results: list[PageVerificationResult] = []
    severity_totals: dict[str, int] = {}

    for page_id in pages_to_check:
        native = load_native_page(store, document_id, page_id)
        evidence = load_evidence_page(store, document_id, page_id)
        ir = load_ir_page(store, document_id, page_id)
        symbols = load_symbol_matches(store, document_id, page_id)
        render = load_render_page(store, document_id, page_id)

        records = run_cross_stage_checks(
            PageArtifacts(
                page_id=page_id,
                document_id=document_id,
                native=native,
                evidence=evidence,
                ir=ir,
                symbols=symbols,
                render=render,
                release_dir=release_dir if has_release else None,
            )
        )

        for r in records:
            severity_totals[r.severity] = severity_totals.get(r.severity, 0) + 1

        page_passed = not any(r.severity in {Severity.ERROR, Severity.CRITICAL} for r in records)
        page_results.append(
            PageVerificationResult(page_id=page_id, records=records, passed=page_passed)
        )

    blocking = any(not p.passed for p in page_results)

    return VerificationReport(
        document_id=document_id,
        timestamp=datetime.now(tz=UTC).isoformat(),
        pages=page_results,
        severity_counts=severity_totals,
        blocking=blocking,
        passed=not blocking,
    )
