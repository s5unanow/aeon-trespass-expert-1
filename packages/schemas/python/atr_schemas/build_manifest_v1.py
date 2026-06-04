"""BuildManifestV1 — published release manifest."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReleaseFile(BaseModel):
    """A file included in the release bundle."""

    path: str
    sha256: str = ""
    size_bytes: int = 0


class BuildManifestV1(BaseModel):
    """Manifest for a published static release."""

    schema_version: str = Field(default="build_manifest.v1", pattern=r"^build_manifest\.v\d+$")
    build_id: str
    document_id: str
    edition: str = "ru"
    run_id: str = ""
    source_pdf_sha256: str = ""
    content_version: str = ""
    generated_at: str = ""
    pipeline_version: str = ""
    files: list[ReleaseFile] = Field(default_factory=list)
    # S5U-894 — review-only draft label. On a clean release these defaults
    # (False / empty) leave the manifest unlabeled. PublishStage stamps them on
    # a ``--review-only`` bundle built over blocking QA so the on-disk manifest
    # is self-describing — a downstream consumer reading the bundle can tell it
    # MUST NOT be released, matching ``make export``'s ``provenance`` stamp
    # (``stamp_draft_provenance``). The two publish surfaces now agree.
    review_only_draft: bool = False
    """True when this bundle was built over BLOCKING QA via the explicit
    ``--review-only`` escape hatch. A clean release leaves this False."""
    blocking_qa_codes: list[str] = Field(default_factory=list)
    """Sorted unique QA codes that blocked release, named on a draft so the
    label says exactly what must be fixed/waived. Empty on a clean release."""
    review_pack_ref: str = ""
    """Artifact-store ref of the run's review pack (``QASummaryV1.review_pack_ref``),
    surfaced so the bundle points at its review pack. Empty when absent."""
