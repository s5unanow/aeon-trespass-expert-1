"""Stage execution result."""

from __future__ import annotations

from dataclasses import dataclass

from atr_pipeline.store.artifact_ref import ArtifactRef


@dataclass(frozen=True)
class StageResult:
    """Result of a single stage invocation."""

    stage_name: str
    cache_key: str
    cached: bool
    artifact_ref: ArtifactRef | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None
