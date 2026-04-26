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
- "1.5" → "1.6" (S5U-735): seven more rules (dead_page_ref,
  decorative_icon, duplicate_content, flat_table, glued_text,
  leaked_identifier, paragraph_length) now source ``document_id``
  from the new ``RenderSourceMap.document_id`` field; chart_title_merge
  is reconciled to the same source so all rules follow the same
  schema-level contract. Cached v1.5 records for those rules still
  carry the page-id shape; the bump re-runs them.
- "1.6" → "1.7" (S5U-736): new ``table_structure_parity`` rule asserts
  EN<->RU TableBlock row/cell parity (S5U-734 follow-up). Cached v1.6
  events would short-circuit the new TABLE_PARITY_* records.
- "1.7" → "1.8" (S5U-730): ``_filter_publishable_pages`` now reads the
  new ``page_images.v1`` manifest emitted by IngestStage to align the
  dead-page-ref suppression set with the web exporter's image-injection
  rescue. Cached v1.7 events would short-circuit the manifest-aware
  filter and re-introduce the FP on image-rescued pages.
- "1.8" → "1.9" (S5U-731): ``_load_render`` and
  ``_filter_publishable_pages`` now route through
  ``store.edition_selection.load_latest_json_for_edition`` which honors
  the exporter's two-tier ``document_version`` policy. On mixed EN/RU
  artifact dirs cached v1.8 events would still load whichever render
  is newest by mtime — potentially the wrong edition.
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
    assert QAStage().version == "1.9", (
        "QAStage.version must be bumped past earlier pins so pre-existing "
        "cached events invalidate and re-emit the full current output set "
        "(manifest-aware DEAD_PAGE_REF suppression, PLACEHOLDER_PROSE_LEAKED "
        "records, FLAT_TABLE_NO_ROWS records, qa_metrics.json, "
        "confidence-band QA records, widened review pack, "
        "CHART_TITLE_MERGE records with real document_id, the seven "
        "S5U-735 rules sourcing document_id from source_map.document_id, "
        "the S5U-736 TABLE_PARITY_* records, the S5U-730 image-rescue "
        "publishability filter reading page_images.v1, and the S5U-731 "
        "edition-aware render-load that honors document_version on mixed "
        "EN/RU artifact dirs)."
    )
