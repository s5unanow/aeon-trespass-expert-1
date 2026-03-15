"""Stage protocol — the canonical execution interface for all pipeline stages."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from atr_schemas.enums import StageScope


@runtime_checkable
class Stage(Protocol):
    """Protocol that all pipeline stages must implement."""

    @property
    def name(self) -> str: ...

    @property
    def scope(self) -> StageScope: ...

    @property
    def version(self) -> str: ...

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> BaseModel: ...


# Forward reference resolved at runtime
from atr_pipeline.runner.stage_context import StageContext  # noqa: E402

__all__ = ["Stage", "StageContext"]
