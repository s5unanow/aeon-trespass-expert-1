#!/usr/bin/env python3
"""Validate that golden fixture JSON files match their Pydantic schemas."""

import json
import sys
from pathlib import Path

from atr_schemas import PageIRV1, QASummaryV1, RenderPageV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1

FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "expected"
)

# Map fixture files to their schema models (skip dynamic-field fixtures)
VALIDATABLE = {
    "page_ir.en.p0001.json": PageIRV1,
    "page_ir.ru.p0001.json": PageIRV1,
    "render_page.p0001.json": RenderPageV1,
    "translation_batch.p0001.json": TranslationBatchV1,
    "translation_result.p0001.json": TranslationResultV1,
    "qa_summary.json": QASummaryV1,
}


def main() -> int:
    errors = 0
    for filename, model in VALIDATABLE.items():
        path = FIXTURE_DIR / filename
        if not path.exists():
            print(f"  MISSING: {filename}")
            errors += 1
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            model.model_validate(data)
            print(f"  OK: {filename}")
        except Exception as e:
            print(f"  FAIL: {filename} — {e}")
            errors += 1

    if errors:
        print(f"\n{errors} fixture(s) failed validation.")
    else:
        print("\nAll fixtures valid.")
    return errors


if __name__ == "__main__":
    sys.exit(main())
