"""Artifact path resolution."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.store.artifact_ref import ArtifactRef


def artifact_path(root: Path, ref: ArtifactRef) -> Path:
    """Resolve an ArtifactRef to an absolute filesystem path."""
    return root / ref.relative_path


def build_ref(
    *,
    document_id: str,
    schema_family: str,
    scope: str,
    entity_id: str,
    content_hash: str,
) -> ArtifactRef:
    """Build an ArtifactRef from components."""
    return ArtifactRef(
        schema_family=schema_family,
        scope=scope,
        entity_id=entity_id,
        content_hash=content_hash,
        document_id=document_id,
    )
