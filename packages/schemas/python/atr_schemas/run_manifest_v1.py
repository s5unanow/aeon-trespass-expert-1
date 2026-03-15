"""RunManifestV1 — run metadata and provenance."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StageInvocationRef(BaseModel):
    """Reference to a stage invocation within a run."""

    stage_name: str
    scope: str
    entity_id: str
    cache_key: str
    status: str = ""
    artifact_ref: str = ""
    duration_ms: int = 0


class RunManifestV1(BaseModel):
    """Metadata for a single pipeline run."""

    schema_version: str = Field(default="run_manifest.v1", pattern=r"^run_manifest\.v\d+$")
    run_id: str
    pipeline_version: str = ""
    git_commit: str = ""
    config_hash: str = ""
    source_pdf_sha256: str = ""
    started_at: str = ""
    finished_at: str = ""
    stages: list[StageInvocationRef] = Field(default_factory=list)
    provider_versions: dict[str, str] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    qa_summary_ref: str = ""
    release_ref: str = ""
