"""Shared helpers for LLM adapter tests (S5U-677 split).

Extracted from ``test_adapters.py`` so that ``test_adapters.py`` and the
sibling ``test_gemini_cli_adapter.py`` can both reference the same minimal
``TranslationBatchV1`` and the same valid result-JSON string without
either duplicating the fixture or importing across test modules. Mirrors
the precedent established by ``_codex_cli_helpers.py`` (S5U-748).

These are not test fixtures (no pytest decorators) — plain functions so
they can be called from inline ``with patch(...)`` blocks where pytest
fixture injection isn't ergonomic.
"""

from __future__ import annotations

import json

from atr_schemas.page_ir_v1 import TextInline
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)


def sample_batch() -> TranslationBatchV1:
    return TranslationBatchV1(
        batch_id="tr.p0001.01",
        source_lang="en",
        target_lang="ru",
        segments=[
            TranslationSegment(
                segment_id="blk_001",
                block_type="heading",
                source_inline=[TextInline(text="Attack Test")],
                context=SegmentContext(page_id="p0001"),
            ),
        ],
    )


def valid_result_json(batch_id: str = "tr.p0001.01") -> str:
    return json.dumps(
        {
            "batch_id": batch_id,
            "segments": [
                {
                    "segment_id": "blk_001",
                    "target_inline": [{"type": "text", "text": "Тест атаки"}],
                    "concept_realizations": [],
                },
            ],
        }
    )
