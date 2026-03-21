"""Tests for the full-document audit runner."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.eval.audit_runner import run_audit
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.common import PageDimensions
from atr_schemas.evidence_primitives_v1 import EvidenceChar
from atr_schemas.page_evidence_v1 import (
    EvidenceTransformMeta,
    PageEvidenceV1,
)
from atr_schemas.resolved_page_v1 import (
    ResolvedBlock,
    ResolvedPageV1,
    ResolvedSymbolRef,
)


def _write_artifact(
    artifacts_root: Path, doc_id: str, family: str, page_id: str, data: str
) -> None:
    """Write a JSON artifact file."""
    art_dir = artifacts_root / doc_id / family / "page" / page_id
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "test.json").write_text(data)


def _make_resolved(doc_id: str, page_id: str, page_number: int = 1) -> ResolvedPageV1:
    return ResolvedPageV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=page_number,
        blocks=[
            ResolvedBlock(block_id=f"{page_id}.b001", block_type="paragraph"),
            ResolvedBlock(block_id=f"{page_id}.b002", block_type="heading"),
        ],
        main_flow_order=[f"{page_id}.b001", f"{page_id}.b002"],
        symbol_refs=[
            ResolvedSymbolRef(
                symbol_id="sym_001",
                instance_id=f"{page_id}.s001",
                anchor_kind="inline",
            ),
        ],
    )


def _make_evidence(doc_id: str, page_id: str) -> PageEvidenceV1:
    return PageEvidenceV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=1,
        transform=EvidenceTransformMeta(
            page_dimensions_pt=PageDimensions(width=612.0, height=792.0),
        ),
        entities=[
            EvidenceChar(
                evidence_id="e.char.001",
                text="A",
                bbox={"x0": 0, "y0": 0, "x1": 10, "y1": 20},
                norm_bbox={"x0": 0, "y0": 0, "x1": 0.1, "y1": 0.1},
            ),
        ],
    )


def test_audit_empty_store(tmp_path: Path) -> None:
    """Audit on empty store returns report with zero pages."""
    store = ArtifactStore(tmp_path)
    report = run_audit(document_id="no_doc", store=store)
    assert report.pages_in_scope == 0
    assert report.pages_audited == 0
    assert report.passed is True
    assert report.blocking is False


def test_audit_single_page(tmp_path: Path) -> None:
    """Audit collects diagnostics for a single resolved page."""
    doc = "test_doc"
    resolved = _make_resolved(doc, "p0001")
    _write_artifact(tmp_path, doc, "resolved_page.v1", "p0001", resolved.model_dump_json())

    evidence = _make_evidence(doc, "p0001")
    _write_artifact(tmp_path, doc, "page_evidence.v1", "p0001", evidence.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    assert report.pages_in_scope == 1
    assert report.pages_audited == 1
    assert len(report.pages) == 1

    page = report.pages[0]
    assert page.page_id == "p0001"
    assert page.block_count == 2
    assert page.symbol_count == 1
    assert page.reading_order_failure is False


def test_audit_multiple_pages(tmp_path: Path) -> None:
    """Audit handles multiple pages."""
    doc = "test_doc"
    for i in range(1, 4):
        page_id = f"p{i:04d}"
        resolved = _make_resolved(doc, page_id, page_number=i)
        _write_artifact(tmp_path, doc, "resolved_page.v1", page_id, resolved.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    assert report.pages_in_scope == 3
    assert report.pages_audited == 3


def test_audit_page_filter(tmp_path: Path) -> None:
    """Audit respects page filter."""
    doc = "test_doc"
    for i in range(1, 4):
        page_id = f"p{i:04d}"
        resolved = _make_resolved(doc, page_id, page_number=i)
        _write_artifact(tmp_path, doc, "resolved_page.v1", page_id, resolved.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store, page_filter=["p0001", "p0003"])

    assert report.pages_in_scope == 2
    assert report.pages_audited == 2
    assert {p.page_id for p in report.pages} == {"p0001", "p0003"}


def test_audit_missing_resolved_counted(tmp_path: Path) -> None:
    """Pages with no resolved artifact are counted as missing."""
    doc = "test_doc"
    # Create a native page (discovered) but no resolved page
    art_dir = tmp_path / doc / "native_page.v1" / "page" / "p0001"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "test.json").write_text("{}")

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    assert report.pages_in_scope == 1
    assert report.pages_audited == 0
    assert report.pages_missing_ir == 1


def test_audit_invariant_failures_tracked(tmp_path: Path) -> None:
    """Pages with invariant failures appear in failure list."""
    doc = "test_doc"
    resolved = _make_resolved(doc, "p0001")
    # Add a dangling flow ref
    resolved.main_flow_order.append("nonexistent_block")
    _write_artifact(tmp_path, doc, "resolved_page.v1", "p0001", resolved.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    assert report.pages_audited == 1
    page = report.pages[0]
    assert "DANGLING_FLOW_REF" in page.invariant_issue_counts
    assert page.reading_order_failure is True
    assert "p0001" in report.invariant_failure_pages
    assert "p0001" in report.reading_order_failure_pages
    assert report.total_issue_counts.get("DANGLING_FLOW_REF", 0) > 0


def test_audit_fallback_blocks_tracked(tmp_path: Path) -> None:
    """Pages with fallback blocks appear in fallback list."""
    doc = "test_doc"
    resolved = _make_resolved(doc, "p0001")
    from atr_schemas.resolved_page_v1 import FallbackProvenance

    resolved.blocks[0].fallback = FallbackProvenance(strategy="ocr", reason="low confidence")
    _write_artifact(tmp_path, doc, "resolved_page.v1", "p0001", resolved.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    page = report.pages[0]
    assert page.fallback_block_count == 1
    assert "p0001" in report.fallback_route_pages


def test_audit_baseline_delta(tmp_path: Path) -> None:
    """Audit computes delta when baseline is provided."""
    doc = "test_doc"
    resolved = _make_resolved(doc, "p0001")
    resolved.main_flow_order.append("missing_ref")
    _write_artifact(tmp_path, doc, "resolved_page.v1", "p0001", resolved.model_dump_json())

    # Write a baseline with different issue counts
    baseline = {
        "document_id": doc,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "pages_in_scope": 1,
        "pages_audited": 1,
        "pages_missing_ir": 0,
        "pages": [],
        "total_issue_counts": {"DANGLING_FLOW_REF": 3},
        "fallback_route_pages": [],
        "hard_pages": [],
        "invariant_failure_pages": [],
        "reading_order_failure_pages": [],
        "blocking": False,
        "passed": True,
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store, baseline_path=baseline_path)

    assert report.baseline_snapshot_id == "2026-01-01T00:00:00+00:00"
    assert report.baseline_delta is not None
    # Current has 1 DANGLING_FLOW_REF, baseline had 3 → delta = -2
    assert report.baseline_delta["DANGLING_FLOW_REF"] == -2.0


def test_audit_report_is_non_blocking(tmp_path: Path) -> None:
    """Audit report is always non-blocking regardless of failures."""
    doc = "test_doc"
    resolved = _make_resolved(doc, "p0001")
    resolved.main_flow_order.append("bad_ref")
    _write_artifact(tmp_path, doc, "resolved_page.v1", "p0001", resolved.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    assert report.blocking is False
    assert report.passed is True


def test_audit_report_serializable(tmp_path: Path) -> None:
    """Audit report serializes to JSON and round-trips."""
    doc = "test_doc"
    resolved = _make_resolved(doc, "p0001")
    _write_artifact(tmp_path, doc, "resolved_page.v1", "p0001", resolved.model_dump_json())

    store = ArtifactStore(tmp_path)
    report = run_audit(document_id=doc, store=store)

    from atr_pipeline.eval.audit_models import AuditReport

    json_str = report.model_dump_json(indent=2)
    roundtripped = AuditReport.model_validate(json.loads(json_str))
    assert roundtripped.document_id == report.document_id
    assert len(roundtripped.pages) == len(report.pages)
