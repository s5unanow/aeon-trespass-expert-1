"""Source abstraction for document configs — the ``source_kind`` union (S5U-779).

A document is compiled from exactly one source. Historically that was always a
PDF (``document.source_pdf``); this module generalises that to a discriminated
union so a photographed image set can be a first-class source too.

The union lives here (not in ``models.py``) to keep that module under the
400-line ceiling. ``DocumentConfig`` composes it and normalises the legacy
``source_pdf`` string into a :class:`PdfSource` at access time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class PdfSource(BaseModel):
    """A born-digital PDF source (the historical default)."""

    source_kind: Literal["pdf"] = "pdf"
    source_pdf: str
    """Repo-relative (or absolute) path to the source PDF."""


class ImageSetSource(BaseModel):
    """A photographed image-set source (S5U-780).

    Points at an image-set manifest (:class:`~atr_schemas.image_set_manifest_v1.ImageSetManifestV1`)
    that lists the ordered source images. The manifest — not this config — holds
    the per-image entries, so a document config stays small even for a book with
    hundreds of photographed pages.
    """

    source_kind: Literal["image_set"] = "image_set"
    manifest: str
    """Repo-relative (or absolute) path to the image-set manifest file."""


# Discriminated on ``source_kind`` — an unknown tag fails closed at config load
# with a clear Pydantic validation error (criterion 4).
SourceSpec = Annotated[
    PdfSource | ImageSetSource,
    Field(discriminator="source_kind"),
]


def validate_exactly_one_source(source_pdf: str | None, source: SourceSpec | None) -> None:
    """Enforce that a document names exactly one source, or raise ``ValueError``.

    ``source`` is already union-validated by Pydantic (an unknown ``source_kind``
    has failed before this runs); this only rejects the both-set / neither-set
    cases so a config can't silently carry two sources or none.
    """
    if source is not None and source_pdf is not None:
        msg = "document must specify either 'source_pdf' or a [document.source] table, not both"
        raise ValueError(msg)
    if source is None and source_pdf is None:
        msg = "document must specify a source: set 'source_pdf' or a [document.source] table"
        raise ValueError(msg)


def resolve_source(source_pdf: str | None, source: SourceSpec | None) -> SourceSpec:
    """Return the source as a :class:`SourceSpec`, normalising legacy ``source_pdf``.

    Re-derived on every call (never frozen) so a caller that mutates
    ``source_pdf`` after load is honoured — mirroring the historical behaviour
    where the PDF path read the field directly.
    """
    if source is not None:
        return source
    if source_pdf is not None:
        return PdfSource(source_pdf=source_pdf)
    # Unreachable when validate_exactly_one_source ran; explicit so a future
    # refactor that weakens the validator fails loud, not silent.
    msg = "document has no source configured"
    raise ValueError(msg)


def _resolve_under_root(raw: str, repo_root: Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else repo_root / p


def resolve_pdf_path(spec: SourceSpec, repo_root: str | Path) -> Path:
    """Resolve the PDF path for a PDF source, or raise if the source is not a PDF."""
    if not isinstance(spec, PdfSource):
        msg = f"source_kind is {spec.source_kind!r}, not 'pdf' — source_pdf_path unavailable"
        raise ValueError(msg)
    return _resolve_under_root(spec.source_pdf, Path(repo_root))


def resolve_manifest_path(spec: SourceSpec, repo_root: str | Path) -> Path:
    """Resolve the manifest path for an image-set source, or raise otherwise."""
    if not isinstance(spec, ImageSetSource):
        msg = f"source_kind is {spec.source_kind!r}, not 'image_set' — manifest path unavailable"
        raise ValueError(msg)
    return _resolve_under_root(spec.manifest, Path(repo_root))
