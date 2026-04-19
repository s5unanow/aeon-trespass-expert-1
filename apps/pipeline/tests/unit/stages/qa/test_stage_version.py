"""Version-pin test for the QA stage.

S5U-640: `QAStage.version` is part of the executor's cache key
(`apps/pipeline/src/atr_pipeline/runner/executor.py:47`). The original
S5U-597 PR added `qa_metrics.json` emission inside `QAStage.run` but left
the version at `"1.0"`, so any pre-existing cached QA event short-circuited
at `executor.py:55` and skipped metrics emission. Bumping the version
invalidates those cache entries exactly once, forcing `QAStage.run` to
execute and emit metrics.

This test pins the post-S5U-640 version so a future revert (e.g. a cherry-pick
back to the pre-bump code) fails loudly instead of silently re-introducing
the cache-skip regression.
"""

from __future__ import annotations

from atr_pipeline.stages.qa.stage import QAStage


def test_qa_stage_version_is_bumped_for_metrics_emission() -> None:
    """Regression pin for S5U-640.

    If this test ever fails because the version was reverted to "1.0", the
    qa_metrics.json artifact will be skipped on every pre-S5U-597 cached
    document. Either bump the version again (correct fix) or declare metrics
    as a cache-aware stage output (larger refactor; see plan-s5u-640-641.md).
    """
    assert QAStage().version == "1.1", (
        "QAStage.version must be bumped past '1.0' so pre-S5U-597 cached "
        "events invalidate and re-emit qa_metrics.json (see S5U-640)."
    )
