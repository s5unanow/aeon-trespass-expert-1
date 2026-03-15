"""ArtifactRef — pointer to an immutable artifact in the store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactRef:
    """Immutable reference to a stored artifact.

    Path convention: {document_id}/{schema_family}/{scope}/{entity_id}/{content_hash}.json
    """

    schema_family: str
    scope: str
    entity_id: str
    content_hash: str
    document_id: str = ""

    @property
    def relative_path(self) -> str:
        """Relative path within the artifact store."""
        parts = [self.document_id, self.schema_family, self.scope, self.entity_id]
        return "/".join(parts) + f"/{self.content_hash}.json"
