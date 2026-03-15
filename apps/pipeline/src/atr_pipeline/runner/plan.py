"""Pipeline plan — define the ordered sequence of stages for a document run."""

from __future__ import annotations

# Stage names in execution order
WALKING_SKELETON_STAGES = [
    "ingest",
    "extract_native",
    "symbols",
    "structure",
    "translate",
    "render",
    "qa",
]


def resolve_stage_range(
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
    all_stages: list[str] | None = None,
) -> list[str]:
    """Return the ordered list of stages between from_stage and to_stage (inclusive)."""
    stages = all_stages or WALKING_SKELETON_STAGES

    start = 0
    if from_stage:
        if from_stage not in stages:
            msg = f"Unknown stage: {from_stage}. Available: {stages}"
            raise ValueError(msg)
        start = stages.index(from_stage)

    end = len(stages)
    if to_stage:
        if to_stage not in stages:
            msg = f"Unknown stage: {to_stage}. Available: {stages}"
            raise ValueError(msg)
        end = stages.index(to_stage) + 1

    return stages[start:end]
