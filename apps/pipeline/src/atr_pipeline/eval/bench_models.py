"""Pydantic models for the checkpointed extraction benchmark."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CheckpointSpec(BaseModel):
    """A single checkpoint in a benchmark ladder."""

    order: int = Field(ge=1)
    name: str
    golden_set: str
    description: str = ""


class BenchmarkLadderConfig(BaseModel):
    """Configuration for a benchmark checkpoint ladder."""

    schema_version: int = 1
    name: str
    description: str = ""
    checkpoints: list[CheckpointSpec] = Field(default_factory=list)


class CheckpointResult(BaseModel):
    """Result of evaluating a single checkpoint."""

    order: int
    name: str
    golden_set: str
    passed: bool
    skipped: bool = False
    is_frontier: bool = False
    is_regression: bool = False
    detail: str = ""


class BenchmarkReport(BaseModel):
    """Full benchmark ladder report."""

    ladder_name: str
    timestamp: str
    checkpoints: list[CheckpointResult] = Field(default_factory=list)
    frontier_checkpoint: int | None = None
    regressions: list[int] = Field(default_factory=list)
    highest_passing: int = 0
    passed: bool = True
