"""Extraction evaluation harness — measures extraction quality against golden sets."""

from atr_pipeline.eval.cross_stage_runner import run_cross_stage_verification
from atr_pipeline.eval.invariant_runner import run_verification
from atr_pipeline.eval.runner import run_evaluation

__all__ = ["run_cross_stage_verification", "run_evaluation", "run_verification"]
