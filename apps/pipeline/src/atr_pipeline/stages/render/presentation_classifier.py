"""Classify page presentation mode: article vs facsimile."""

from __future__ import annotations

from typing import Literal

from atr_pipeline.config.models import PageOverride
from atr_schemas.layout_page_v1 import DifficultyScoreV1


def classify_presentation_mode(
    page_id: str,
    difficulty: DifficultyScoreV1 | None,
    threshold: float,
    page_overrides: dict[str, PageOverride],
) -> Literal["article", "facsimile"]:
    """Determine whether a page should render as article or facsimile.

    Priority order:
    1. Explicit config override (primary mechanism)
    2. Auto heuristic: hard_page + low native text coverage
    3. Default: article
    """
    override = page_overrides.get(page_id)
    if override and override.presentation_mode is not None:
        return override.presentation_mode

    if difficulty and difficulty.hard_page and difficulty.native_text_coverage < threshold:
        return "facsimile"

    return "article"
