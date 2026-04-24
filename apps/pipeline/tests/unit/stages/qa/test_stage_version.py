"""Version-pin test for the QA stage.

`QAStage.version` is part of the executor's cache key
(`apps/pipeline/src/atr_pipeline/runner/executor.py:47`). Each time a new
observable side effect is added to `QAStage.run` (new artifact write, new
record type, widened review-pack emission condition), the version must be
bumped in the same PR so pre-existing cached events invalidate and re-emit.
See `.claude/rules/pipeline.md` § "Stage-output cache invalidation".

Bump history:
- "1.0" → "1.1" (S5U-640): force qa_metrics.json re-emission after S5U-597
  added the artifact write without bumping.
- "1.1" → "1.2" (S5U-588): force confidence-band QA records + widened
  review-pack writes to be emitted on pre-existing cached documents.
- "1.2" → "1.3" (S5U-701): manifest-aware dead-page-ref suppresses false
  positives whose target IS in the published page set, and a new
  PLACEHOLDER_PROSE_LEAKED (ERROR) record fires on descriptive placeholder
  prose like "Potential symbol" / "??? symbol".  Both change the record
  set a cached QA pass would otherwise replay.
- "1.3" → "1.4" (S5U-704): new ``flat_table`` rule emits
  FLAT_TABLE_NO_ROWS records for TableBlocks lacking row/cell structure.
  Cached QA runs must re-emit the broader record set.
- "1.4" → "1.5" (S5U-705): ``chart_title_merge_rule`` now writes the real
  ``document_id`` into ``QARecordV1.document_id`` (sourced from
  ``source_ir.document_id``) instead of the ``render_page.source_map.page_id``
  value plumbed by the S5U-698 introduction. Cached records from v1.4
  carry the wrong ``document_id`` shape, so the bump forces a re-run.
"""

from __future__ import annotations

from atr_pipeline.stages.qa.stage import QAStage


def test_qa_stage_version_is_bumped_for_metrics_emission() -> None:
    """Regression pin for the QA stage version.

    If this test fails because the version was reverted to an earlier value,
    stage side effects added since that version will be skipped on every
    pre-existing cached document. Bump the version again (correct fix) or
    declare the affected outputs as cache-aware (larger refactor; see
    plan-s5u-640-641.md).
    """
    assert QAStage().version == "1.5", (
        "QAStage.version must be bumped past earlier pins so pre-existing "
        "cached events invalidate and re-emit the full current output set "
        "(manifest-aware DEAD_PAGE_REF suppression, PLACEHOLDER_PROSE_LEAKED "
        "records, FLAT_TABLE_NO_ROWS records, qa_metrics.json, "
        "confidence-band QA records, widened review pack, "
        "CHART_TITLE_MERGE records with real document_id)."
    )
