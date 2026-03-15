"""Immutable artifact store — the primary data plane for pipeline outputs."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.atomic_write import atomic_write_text
from atr_pipeline.store.pathing import artifact_path, build_ref
from atr_pipeline.utils.hashing import content_hash


class ArtifactStore:
    """Immutable artifact store backed by the filesystem.

    Artifacts are content-addressed JSON files. Writing the same content
    twice with the same key returns the same ref without re-writing.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def put_json(
        self,
        *,
        document_id: str,
        schema_family: str,
        scope: str,
        entity_id: str,
        data: dict[str, object] | BaseModel,
    ) -> ArtifactRef:
        """Write a JSON artifact and return its ref.

        If an artifact with the same content hash already exists, returns
        the existing ref without writing.
        """
        json_data = json.loads(data.model_dump_json()) if isinstance(data, BaseModel) else data

        c_hash = content_hash(json_data)
        ref = build_ref(
            document_id=document_id,
            schema_family=schema_family,
            scope=scope,
            entity_id=entity_id,
            content_hash=c_hash,
        )

        target = artifact_path(self._root, ref)
        if target.exists():
            return ref

        text = json.dumps(json_data, indent=2, ensure_ascii=False) + "\n"
        atomic_write_text(target, text)
        return ref

    def has(self, ref: ArtifactRef) -> bool:
        """Check if an artifact exists."""
        return artifact_path(self._root, ref).exists()

    def get_json(self, ref: ArtifactRef) -> dict[str, object]:
        """Read an artifact as a parsed JSON dict."""
        target = artifact_path(self._root, ref)
        if not target.exists():
            msg = f"Artifact not found: {ref.relative_path}"
            raise FileNotFoundError(msg)
        with open(target, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    def get_path(self, ref: ArtifactRef) -> Path:
        """Return the absolute filesystem path for an artifact."""
        return artifact_path(self._root, ref)

    def put_bytes(
        self,
        *,
        document_id: str,
        schema_family: str,
        scope: str,
        entity_id: str,
        data: bytes,
        extension: str = ".bin",
    ) -> Path:
        """Write a raw binary artifact (e.g. PNG raster) and return its path.

        This is for non-JSON artifacts like page rasters.
        """
        from atr_pipeline.store.atomic_write import atomic_write_bytes
        from atr_pipeline.utils.hashing import sha256_bytes

        c_hash = sha256_bytes(data)[:12]
        rel = f"{document_id}/{schema_family}/{scope}/{entity_id}/{c_hash}{extension}"
        target = self._root / rel
        if not target.exists():
            atomic_write_bytes(target, data)
        return target
