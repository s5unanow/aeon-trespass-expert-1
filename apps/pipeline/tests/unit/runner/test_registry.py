"""Tests for the stage registry."""

from __future__ import annotations

from atr_pipeline.runner.plan import WALKING_SKELETON_STAGES
from atr_pipeline.runner.registry import build_stage_registry
from atr_pipeline.runner.stage_protocol import Stage


def test_registry_keys_match_walking_skeleton_stages() -> None:
    """Registry has exactly the stages defined in the walking skeleton plan."""
    registry = build_stage_registry()
    assert sorted(registry.keys()) == sorted(WALKING_SKELETON_STAGES)


def test_registry_values_satisfy_stage_protocol() -> None:
    """Every stage in the registry satisfies the Stage protocol."""
    registry = build_stage_registry()
    for name, stage in registry.items():
        assert isinstance(stage, Stage), f"{name} does not satisfy Stage protocol"
        assert stage.name == name
