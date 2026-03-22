"""Confidence-band policy: models, loader, and page evaluator."""

from __future__ import annotations

import logging
import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from atr_pipeline.config.loader import _find_repo_root

logger = logging.getLogger(__name__)

_DEFAULT_BANDS_PATH = "configs/qa/confidence_bands.toml"


class BandAction(StrEnum):
    """Actions the pipeline can take for a confidence band."""

    PRIMARY = "primary"
    HARD_ROUTE = "hard_route"
    QA_REQUIRED = "qa_required"
    PUBLISH_BLOCKING = "publish_blocking"


class ConfidenceBand(BaseModel):
    """A single named confidence band with a threshold range and action."""

    name: str
    min_confidence: float = Field(ge=0.0, le=1.01)
    max_confidence: float = Field(ge=0.0, le=1.01)
    action: BandAction
    description: str = ""


class ConfidenceBandPolicy(BaseModel):
    """Versioned confidence-band policy loaded from TOML."""

    version: int = 1
    bands: list[ConfidenceBand] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_bands(self) -> ConfidenceBandPolicy:
        if not self.bands:
            return self

        for band in self.bands:
            if band.min_confidence >= band.max_confidence:
                msg = (
                    f"Band '{band.name}': min_confidence ({band.min_confidence}) "
                    f"must be < max_confidence ({band.max_confidence})"
                )
                raise ValueError(msg)

        sorted_bands = sorted(self.bands, key=lambda b: b.min_confidence)

        for i in range(len(sorted_bands) - 1):
            current = sorted_bands[i]
            next_band = sorted_bands[i + 1]
            if abs(current.max_confidence - next_band.min_confidence) > 1e-9:
                msg = (
                    f"Band gap/overlap between '{current.name}' "
                    f"(max={current.max_confidence}) and "
                    f"'{next_band.name}' "
                    f"(min={next_band.min_confidence})"
                )
                raise ValueError(msg)

        first = sorted_bands[0]
        if first.min_confidence > 1e-9:
            msg = (
                f"Bands must start at 0.0, but lowest band "
                f"'{first.name}' starts at {first.min_confidence}"
            )
            raise ValueError(msg)

        last = sorted_bands[-1]
        if last.max_confidence < 1.0:
            msg = (
                f"Bands must cover confidence=1.0, but highest band "
                f"'{last.name}' ends at {last.max_confidence}"
            )
            raise ValueError(msg)

        return self


class BandResult(BaseModel):
    """Result of evaluating a page's confidence against the band policy."""

    page_id: str
    confidence: float
    band_name: str
    action: BandAction
    description: str = ""


def load_confidence_bands(*, repo_root: Path | None = None) -> ConfidenceBandPolicy:
    """Load confidence-band policy from configs/qa/confidence_bands.toml."""
    root = repo_root or _find_repo_root()
    path = root / _DEFAULT_BANDS_PATH
    if not path.exists():
        msg = f"Confidence-band config not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return ConfidenceBandPolicy.model_validate(data)


def evaluate_page_confidence(
    page_id: str,
    confidence: float,
    policy: ConfidenceBandPolicy,
) -> BandResult:
    """Determine which confidence band a page falls into.

    Bands are matched as ``[min, max)`` except for the top band which
    uses ``[min, max]`` (inclusive upper bound) so that confidence=1.0
    is always matchable with ``max_confidence=1.0``.

    Returns a ``BandResult`` with the band name and action.
    """
    sorted_bands = sorted(policy.bands, key=lambda b: b.min_confidence)
    top_band = sorted_bands[-1] if sorted_bands else None
    for band in sorted_bands:
        if band is top_band:
            matched = band.min_confidence <= confidence <= band.max_confidence
        else:
            matched = band.min_confidence <= confidence < band.max_confidence
        if matched:
            logger.debug(
                "page %s confidence=%.3f -> band=%s action=%s",
                page_id,
                confidence,
                band.name,
                band.action.value,
            )
            return BandResult(
                page_id=page_id,
                confidence=confidence,
                band_name=band.name,
                action=band.action,
                description=band.description,
            )

    msg = f"No band matched confidence {confidence} for page {page_id}"
    raise ValueError(msg)
