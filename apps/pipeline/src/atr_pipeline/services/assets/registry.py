"""AssetRegistryBuilder — build the document-level asset registry from evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from atr_pipeline.services.assets.identity import asset_class_id, occurrence_id
from atr_schemas.asset_class_v1 import AssetClassV1, AssetIdentity
from atr_schemas.asset_occurrence_v1 import AssetOccurrenceV1
from atr_schemas.asset_registry_v1 import AssetRegistryV1
from atr_schemas.enums import AssetSourceKind, OccurrenceContext
from atr_schemas.evidence_primitives_v1 import (
    EvidenceImageOccurrence,
    EvidenceVectorCluster,
)

if TYPE_CHECKING:
    from atr_schemas.page_evidence_v1 import PageEvidenceV1


class AssetRegistryBuilder:
    """Accumulates evidence across pages and produces an ``AssetRegistryV1``.

    Usage::

        builder = AssetRegistryBuilder(document_id="ato_core_v1_1")
        for evidence in page_evidences:
            builder.ingest_page(evidence)
        registry = builder.build()
    """

    def __init__(self, document_id: str) -> None:
        self._document_id = document_id
        self._classes: dict[str, AssetClassV1] = {}
        self._occurrences: list[AssetOccurrenceV1] = []
        self._page_seq: dict[str, int] = {}

    def ingest_page(self, evidence: PageEvidenceV1) -> None:
        """Extract image and vector-cluster occurrences from one page."""
        page_id = evidence.page_id
        for entity in evidence.entities:
            if isinstance(entity, EvidenceImageOccurrence):
                self._ingest_image(entity, page_id)
            elif isinstance(entity, EvidenceVectorCluster):
                self._ingest_vector_cluster(entity, page_id)

    def build(self) -> AssetRegistryV1:
        """Return the finalised registry."""
        return AssetRegistryV1(
            document_id=self._document_id,
            classes=list(self._classes.values()),
            occurrences=list(self._occurrences),
        )

    def _next_seq(self, page_id: str) -> int:
        seq = self._page_seq.get(page_id, 0)
        self._page_seq[page_id] = seq + 1
        return seq

    def _ingest_image(
        self,
        img: EvidenceImageOccurrence,
        page_id: str,
    ) -> None:
        source_kind = AssetSourceKind.EMBEDDED_RASTER
        exact_hash = img.image_hash
        cid = asset_class_id(source_kind, exact_hash)

        if cid not in self._classes:
            self._classes[cid] = AssetClassV1(
                class_id=cid,
                source_kind=source_kind,
                identity=AssetIdentity(exact_hash=exact_hash),
                width_px=img.width_px,
                height_px=img.height_px,
                canonical_evidence_id=img.evidence_id,
            )

        context = _classify_image_context(img)
        self._occurrences.append(
            AssetOccurrenceV1(
                occurrence_id=occurrence_id(page_id, self._next_seq(page_id)),
                class_id=cid,
                page_id=page_id,
                bbox=img.bbox,
                norm_bbox=img.norm_bbox,
                context=context,
                evidence_ids=[img.evidence_id],
            )
        )

    def _ingest_vector_cluster(
        self,
        cluster: EvidenceVectorCluster,
        page_id: str,
    ) -> None:
        source_kind = AssetSourceKind.VECTOR_CLUSTER
        exact_hash = cluster.cluster_hash
        cid = asset_class_id(source_kind, exact_hash)

        if cid not in self._classes:
            self._classes[cid] = AssetClassV1(
                class_id=cid,
                source_kind=source_kind,
                identity=AssetIdentity(
                    exact_hash=exact_hash,
                    vector_signature=exact_hash,
                ),
                canonical_evidence_id=cluster.evidence_id,
            )

        self._occurrences.append(
            AssetOccurrenceV1(
                occurrence_id=occurrence_id(page_id, self._next_seq(page_id)),
                class_id=cid,
                page_id=page_id,
                bbox=cluster.bbox,
                norm_bbox=cluster.norm_bbox,
                context=OccurrenceContext.DECORATION,
                evidence_ids=[cluster.evidence_id, *cluster.path_ids],
            )
        )


def _classify_image_context(img: EvidenceImageOccurrence) -> OccurrenceContext:
    """Heuristic: small images are likely inline; large ones are region floats."""
    area = img.bbox.width * img.bbox.height
    if area < 900:  # roughly 30x30 pt or smaller
        return OccurrenceContext.INLINE
    return OccurrenceContext.REGION_FLOAT
