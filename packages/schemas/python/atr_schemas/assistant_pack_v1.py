"""AssistantPackV1 — manifest for assistant retrieval artifacts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantPackV1(BaseModel):
    """Manifest describing the assistant artifact bundle for a document edition.

    Produced by the pipeline export step, consumed by the assistant
    query service to locate chunks and the FTS5 index.
    """

    schema_version: str = Field(default="assistant_pack.v1", pattern=r"^assistant_pack\.v\d+$")
    document_id: str
    edition: str
    chunks_count: int = Field(ge=0, default=0)
    index_path: str = ""
    chunks_path: str = ""
    build_id: str = ""
    generated_at: str = ""
    pipeline_version: str = ""
