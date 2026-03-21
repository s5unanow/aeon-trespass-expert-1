"""Unit tests for AssetRegistryBuilder."""

from atr_pipeline.services.assets.registry import AssetRegistryBuilder
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import AssetSourceKind, OccurrenceContext
from atr_schemas.evidence_primitives_v1 import (
    EvidenceChar,
    EvidenceImageOccurrence,
    EvidenceVectorCluster,
)
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1

_DIMS = PageDimensions(width=595.2, height=841.8)
_RECT = Rect(x0=50.0, y0=100.0, x1=200.0, y1=120.0)
_NORM = NormRect(x0=0.08, y0=0.12, x1=0.34, y1=0.14)
_SMALL_RECT = Rect(x0=100.0, y0=100.0, x1=110.0, y1=110.0)
_SMALL_NORM = NormRect(x0=0.17, y0=0.12, x1=0.18, y1=0.13)


def _make_evidence(
    page_id: str,
    entities: list[object],
) -> PageEvidenceV1:
    page_number = int(page_id[1:])
    return PageEvidenceV1(
        document_id="test",
        page_id=page_id,
        page_number=page_number,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
        entities=entities,  # type: ignore[arg-type]
    )


def test_empty_evidence_produces_empty_registry() -> None:
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", []))
    reg = builder.build()
    assert reg.document_id == "test"
    assert reg.classes == []
    assert reg.occurrences == []


def test_single_image_creates_class_and_occurrence() -> None:
    img = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=_SMALL_RECT,
        norm_bbox=_SMALL_NORM,
        width_px=14,
        height_px=14,
        image_hash="deadbeef1234",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [img]))
    reg = builder.build()

    assert len(reg.classes) == 1
    assert reg.classes[0].class_id == "ac.raster.deadbeef1234"
    assert reg.classes[0].source_kind == AssetSourceKind.EMBEDDED_RASTER
    assert reg.classes[0].identity.exact_hash == "deadbeef1234"
    assert reg.classes[0].width_px == 14
    assert reg.classes[0].canonical_evidence_id == "e.img.000"

    assert len(reg.occurrences) == 1
    assert reg.occurrences[0].occurrence_id == "ao.p0001.000"
    assert reg.occurrences[0].class_id == "ac.raster.deadbeef1234"
    assert reg.occurrences[0].page_id == "p0001"


def test_duplicate_images_share_class() -> None:
    """Same image_hash on two pages → one class, two occurrences."""
    img1 = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=_SMALL_RECT,
        norm_bbox=_SMALL_NORM,
        width_px=14,
        height_px=14,
        image_hash="deadbeef1234",
    )
    img2 = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=_SMALL_RECT,
        norm_bbox=_SMALL_NORM,
        width_px=14,
        height_px=14,
        image_hash="deadbeef1234",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [img1]))
    builder.ingest_page(_make_evidence("p0002", [img2]))
    reg = builder.build()

    assert len(reg.classes) == 1
    assert len(reg.occurrences) == 2
    assert reg.occurrences[0].page_id == "p0001"
    assert reg.occurrences[1].page_id == "p0002"


def test_different_images_create_different_classes() -> None:
    img1 = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=_SMALL_RECT,
        norm_bbox=_SMALL_NORM,
        image_hash="aaaa00001111",
    )
    img2 = EvidenceImageOccurrence(
        evidence_id="e.img.001",
        bbox=_SMALL_RECT,
        norm_bbox=_SMALL_NORM,
        image_hash="bbbb00002222",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [img1, img2]))
    reg = builder.build()

    assert len(reg.classes) == 2
    assert len(reg.occurrences) == 2


def test_vector_cluster_creates_class() -> None:
    cluster = EvidenceVectorCluster(
        evidence_id="e.vclust.000",
        bbox=_RECT,
        norm_bbox=_NORM,
        path_ids=["e.vec.000", "e.vec.001"],
        cluster_hash="cafebabe5678",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [cluster]))
    reg = builder.build()

    assert len(reg.classes) == 1
    assert reg.classes[0].class_id == "ac.vector.cafebabe5678"
    assert reg.classes[0].source_kind == AssetSourceKind.VECTOR_CLUSTER
    assert reg.classes[0].identity.vector_signature == "cafebabe5678"

    assert len(reg.occurrences) == 1
    assert reg.occurrences[0].context == OccurrenceContext.DECORATION
    assert reg.occurrences[0].evidence_ids == [
        "e.vclust.000",
        "e.vec.000",
        "e.vec.001",
    ]


def test_non_asset_entities_are_skipped() -> None:
    """Text entities like EvidenceChar should not produce assets."""
    char = EvidenceChar(
        evidence_id="e.char.000",
        text="A",
        bbox=_RECT,
        norm_bbox=_NORM,
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [char]))
    reg = builder.build()

    assert reg.classes == []
    assert reg.occurrences == []


def test_small_image_classified_inline() -> None:
    """Images smaller than 30x30 pt are classified as INLINE."""
    img = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=Rect(x0=100, y0=100, x1=120, y1=120),  # 20x20
        norm_bbox=_SMALL_NORM,
        image_hash="small1234567",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [img]))
    reg = builder.build()

    assert reg.occurrences[0].context == OccurrenceContext.INLINE


def test_large_image_classified_region_float() -> None:
    """Images larger than 30x30 pt are classified as REGION_FLOAT."""
    img = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=Rect(x0=50, y0=50, x1=300, y1=400),  # 250x350
        norm_bbox=NormRect(x0=0.08, y0=0.06, x1=0.50, y1=0.48),
        image_hash="large1234567",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [img]))
    reg = builder.build()

    assert reg.occurrences[0].context == OccurrenceContext.REGION_FLOAT


def test_mixed_assets_multi_page() -> None:
    """Mix of images and vectors across pages builds a coherent registry."""
    img = EvidenceImageOccurrence(
        evidence_id="e.img.000",
        bbox=_SMALL_RECT,
        norm_bbox=_SMALL_NORM,
        image_hash="aabb11223344",
    )
    cluster = EvidenceVectorCluster(
        evidence_id="e.vclust.000",
        bbox=_RECT,
        norm_bbox=_NORM,
        path_ids=["e.vec.000"],
        cluster_hash="ccdd55667788",
    )
    builder = AssetRegistryBuilder(document_id="test")
    builder.ingest_page(_make_evidence("p0001", [img, cluster]))
    builder.ingest_page(_make_evidence("p0002", [img]))  # same image reused
    reg = builder.build()

    assert len(reg.classes) == 2
    assert len(reg.occurrences) == 3  # 2 images + 1 vector
    assert len(reg.get_occurrences_for_class("ac.raster.aabb11223344")) == 2
    assert len(reg.get_occurrences_for_page("p0001")) == 2
    assert len(reg.get_occurrences_for_page("p0002")) == 1
