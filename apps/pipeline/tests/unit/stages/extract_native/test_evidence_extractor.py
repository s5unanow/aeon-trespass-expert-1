"""Tests for evidence extraction from PDF pages."""

from __future__ import annotations

import re
from pathlib import Path

from atr_pipeline.stages.extract_native.evidence_extractor import extract_page_evidence
from atr_schemas.evidence_primitives_v1 import (
    EvidenceChar,
    EvidenceImageOccurrence,
    EvidenceLine,
    EvidenceTextSpan,
)
from atr_schemas.page_evidence_v1 import PageEvidenceV1

FIXTURE_DIR = (
    Path(__file__).resolve().parents[6]
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "source"
)

EVIDENCE_ID_RE = re.compile(r"^e\.\w+\.\d{3,}$")


def _extract() -> PageEvidenceV1:
    pdf_path = FIXTURE_DIR / "sample_page_01.pdf"
    return extract_page_evidence(pdf_path, page_number=1, document_id="walking_skeleton")


def test_produces_page_evidence_v1() -> None:
    evidence = _extract()
    assert isinstance(evidence, PageEvidenceV1)
    assert evidence.page_id == "p0001"
    assert evidence.page_number == 1
    assert evidence.schema_version == "page_evidence.v1"


def test_transform_metadata() -> None:
    evidence = _extract()
    assert evidence.transform.extractor == "pymupdf_evidence"
    assert evidence.transform.coordinate_space == "pdf_points"
    assert evidence.transform.page_dimensions_pt.width > 0
    assert evidence.transform.page_dimensions_pt.height > 0


def test_has_chars() -> None:
    evidence = _extract()
    chars = [e for e in evidence.entities if isinstance(e, EvidenceChar)]
    assert len(chars) > 0
    all_text = "".join(c.text for c in chars)
    assert "A" in all_text  # from "Attack"


def test_has_lines() -> None:
    evidence = _extract()
    lines = [e for e in evidence.entities if isinstance(e, EvidenceLine)]
    assert len(lines) > 0
    assert all(len(ln.char_ids) > 0 for ln in lines)


def test_has_text_spans() -> None:
    evidence = _extract()
    spans = [e for e in evidence.entities if isinstance(e, EvidenceTextSpan)]
    assert len(spans) > 0
    assert any(sp.font_name != "" for sp in spans)


def test_has_image_occurrences() -> None:
    evidence = _extract()
    images = [e for e in evidence.entities if isinstance(e, EvidenceImageOccurrence)]
    assert len(images) >= 1
    assert all(img.image_hash != "" for img in images)


def test_evidence_ids_unique() -> None:
    evidence = _extract()
    ids = [e.evidence_id for e in evidence.entities]
    assert len(ids) == len(set(ids)), (
        f"Duplicate evidence IDs found: {len(ids)} total, {len(set(ids))} unique"
    )


def test_evidence_ids_match_pattern() -> None:
    evidence = _extract()
    for entity in evidence.entities:
        assert EVIDENCE_ID_RE.match(entity.evidence_id), (
            f"Evidence ID {entity.evidence_id!r} does not match pattern"
        )


def test_norm_bboxes_in_range() -> None:
    evidence = _extract()
    for entity in evidence.entities:
        nb = entity.norm_bbox
        assert 0.0 <= nb.x0 <= 1.0, f"{entity.evidence_id}: norm_bbox.x0={nb.x0}"
        assert 0.0 <= nb.y0 <= 1.0, f"{entity.evidence_id}: norm_bbox.y0={nb.y0}"
        assert 0.0 <= nb.x1 <= 1.0, f"{entity.evidence_id}: norm_bbox.x1={nb.x1}"
        assert 0.0 <= nb.y1 <= 1.0, f"{entity.evidence_id}: norm_bbox.y1={nb.y1}"


def test_bboxes_within_page() -> None:
    evidence = _extract()
    w = evidence.transform.page_dimensions_pt.width
    h = evidence.transform.page_dimensions_pt.height
    tolerance = 2.0
    for entity in evidence.entities:
        b = entity.bbox
        assert b.x0 >= -tolerance, f"{entity.evidence_id}: bbox.x0={b.x0}"
        assert b.y0 >= -tolerance, f"{entity.evidence_id}: bbox.y0={b.y0}"
        assert b.x1 <= w + tolerance, f"{entity.evidence_id}: bbox.x1={b.x1} > {w}"
        assert b.y1 <= h + tolerance, f"{entity.evidence_id}: bbox.y1={b.y1} > {h}"


def test_line_char_ids_reference_valid_chars() -> None:
    evidence = _extract()
    char_ids = {e.evidence_id for e in evidence.entities if isinstance(e, EvidenceChar)}
    lines = [e for e in evidence.entities if isinstance(e, EvidenceLine)]
    for line in lines:
        for cid in line.char_ids:
            assert cid in char_ids, f"Line {line.evidence_id} references unknown char {cid}"


def test_span_char_ids_reference_valid_chars() -> None:
    evidence = _extract()
    char_ids = {e.evidence_id for e in evidence.entities if isinstance(e, EvidenceChar)}
    spans = [e for e in evidence.entities if isinstance(e, EvidenceTextSpan)]
    for span in spans:
        for cid in span.char_ids:
            assert cid in char_ids, f"Span {span.evidence_id} references unknown char {cid}"
