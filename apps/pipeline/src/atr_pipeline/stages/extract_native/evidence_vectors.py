"""Extract image, vector-path, vector-cluster, and table evidence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from atr_pipeline.utils.hashing import sha256_bytes, sha256_str
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.evidence_primitives_v1 import (
    EvidenceImageOccurrence,
    EvidenceTableCandidate,
    EvidenceVectorCluster,
    EvidenceVectorPath,
)

from .evidence_text import normalize_rect

if TYPE_CHECKING:
    import fitz

logger = logging.getLogger(__name__)


def extract_image_evidence(
    page: fitz.Page,
    doc: fitz.Document,
    dims: PageDimensions,
) -> list[EvidenceImageOccurrence]:
    """Extract image occurrences with stable content hashes."""
    results: list[EvidenceImageOccurrence] = []
    for i, img_info in enumerate(page.get_images(full=True)):
        xref = img_info[0]
        try:
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            r = rects[0]
            rect = Rect(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1)

            image_hash = ""
            try:
                img_data = doc.extract_image(xref)
                if img_data and img_data.get("image"):
                    image_hash = sha256_bytes(img_data["image"])[:12]
            except Exception:
                logger.debug("Could not extract image data for xref=%d", xref)

            results.append(
                EvidenceImageOccurrence(
                    evidence_id=f"e.img.{i:03d}",
                    bbox=rect,
                    norm_bbox=normalize_rect(rect, dims),
                    width_px=img_info[2],
                    height_px=img_info[3],
                    colorspace=str(img_info[5]) if len(img_info) > 5 else "",
                    xref=xref,
                    image_hash=image_hash,
                )
            )
        except Exception:
            logger.debug("Skipping image xref=%d: cannot locate on page", xref)
    return results


def extract_vector_evidence(
    page: fitz.Page,
    dims: PageDimensions,
) -> tuple[list[EvidenceVectorPath], list[EvidenceVectorCluster]]:
    """Extract vector paths and cluster them by spatial proximity."""
    paths: list[EvidenceVectorPath] = []
    drawings = page.get_drawings()

    for i, d in enumerate(drawings):
        r = d.get("rect")
        if r is None:
            continue
        rect = Rect(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1)
        ops = [str(item[0]) for item in d.get("items", [])]

        paths.append(
            EvidenceVectorPath(
                evidence_id=f"e.vec.{i:03d}",
                bbox=rect,
                norm_bbox=normalize_rect(rect, dims),
                path_ops=ops,
                stroke_color=_color_to_int(d.get("color")),
                fill_color=_color_to_int(d.get("fill")),
                line_width=d.get("width") or 0.0,
            )
        )

    clusters = _cluster_paths(paths, dims)
    return paths, clusters


def extract_table_evidence(
    page: fitz.Page,
    dims: PageDimensions,
) -> list[EvidenceTableCandidate]:
    """Detect table candidates using PyMuPDF find_tables."""
    results: list[EvidenceTableCandidate] = []
    try:
        finder = page.find_tables()
        for i, table in enumerate(finder.tables):
            bbox = table.bbox
            rect = Rect(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
            results.append(
                EvidenceTableCandidate(
                    evidence_id=f"e.tbl.{i:03d}",
                    bbox=rect,
                    norm_bbox=normalize_rect(rect, dims),
                    row_count=table.row_count,
                    col_count=table.col_count,
                    confidence=1.0,
                )
            )
    except Exception:
        logger.debug("Table detection failed for page, skipping")
    return results


# -- helpers --


def _color_to_int(color: object) -> int | None:
    """Convert a PyMuPDF color (None, float, or tuple) to packed int."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        v = _clamp_channel(float(color))
        return (v << 16) | (v << 8) | v
    if isinstance(color, (list, tuple)):
        if len(color) == 3:
            r, g, b = (_clamp_channel(float(c)) for c in color)
            return (r << 16) | (g << 8) | b
        if len(color) == 1:
            v = _clamp_channel(float(color[0]))
            return (v << 16) | (v << 8) | v
    return None


def _clamp_channel(value: float) -> int:
    """Clamp a [0,1] colour channel to an 8-bit int."""
    return max(0, min(255, int(value * 255)))


def _cluster_paths(
    paths: list[EvidenceVectorPath],
    dims: PageDimensions,
    proximity_pt: float = 2.0,
) -> list[EvidenceVectorCluster]:
    """Cluster vector paths by spatial overlap using union-find."""
    n = len(paths)
    if n == 0:
        return []

    groups = _group_by_overlap(paths, proximity_pt)
    return _build_clusters(paths, groups, dims)


def _group_by_overlap(
    paths: list[EvidenceVectorPath],
    proximity_pt: float,
) -> dict[int, list[int]]:
    """Union-find grouping of paths whose bboxes overlap within margin."""
    n = len(paths)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if _bboxes_overlap(paths[i].bbox, paths[j].bbox, proximity_pt):
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return groups


def _build_clusters(
    paths: list[EvidenceVectorPath],
    groups: dict[int, list[int]],
    dims: PageDimensions,
) -> list[EvidenceVectorCluster]:
    """Convert path groups into EvidenceVectorCluster entities."""
    clusters: list[EvidenceVectorCluster] = []
    ci = 0
    for indices in groups.values():
        if len(indices) < 2:
            continue
        union_box = paths[indices[0]].bbox
        all_ops: list[str] = []
        path_ids: list[str] = []
        for idx in indices:
            union_box = _union_rect(union_box, paths[idx].bbox)
            all_ops.extend(paths[idx].path_ops)
            path_ids.append(paths[idx].evidence_id)
        clusters.append(
            EvidenceVectorCluster(
                evidence_id=f"e.vclust.{ci:03d}",
                bbox=union_box,
                norm_bbox=normalize_rect(union_box, dims),
                path_ids=path_ids,
                cluster_hash=sha256_str(" ".join(sorted(all_ops)))[:12],
            )
        )
        ci += 1
    return clusters


def _bboxes_overlap(a: Rect, b: Rect, margin: float) -> bool:
    """Check if two bboxes overlap within a margin."""
    return not (
        a.x1 + margin < b.x0 or b.x1 + margin < a.x0 or a.y1 + margin < b.y0 or b.y1 + margin < a.y0
    )


def _union_rect(a: Rect, b: Rect) -> Rect:
    return Rect(
        x0=min(a.x0, b.x0),
        y0=min(a.y0, b.y0),
        x1=max(a.x1, b.x1),
        y1=max(a.y1, b.y1),
    )
