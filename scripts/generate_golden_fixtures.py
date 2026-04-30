#!/usr/bin/env python3
"""Generate golden expected JSON fixtures for the walking skeleton.

These are the expected outputs that integration tests compare against.

The per-stage payload builders live in ``_golden_pipeline_payloads`` and the
glossary payload in ``_golden_glossary_payload`` — split out per S5U-711 to
keep this entry point under the 400-line ceiling.
"""

import json
from pathlib import Path

from _golden_glossary_payload import build_glossary_payload
from _golden_pipeline_payloads import (
    build_native_page,
    build_page_ir_en,
    build_page_ir_ru,
    build_qa_summary,
    build_render_page,
    build_source_manifest,
    build_symbol_matches,
    build_translation_batch,
    build_translation_result,
)

OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "expected"
)


def write_json(name: str, data: dict) -> None:  # type: ignore[type-arg]
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {name}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_json("source_manifest.json", build_source_manifest())
    write_json("native_page.p0001.json", build_native_page())
    write_json("symbol_matches.p0001.json", build_symbol_matches())
    write_json("page_ir.en.p0001.json", build_page_ir_en())
    write_json("translation_batch.p0001.json", build_translation_batch())
    write_json("translation_result.p0001.json", build_translation_result())
    write_json("page_ir.ru.p0001.json", build_page_ir_ru())
    write_json("render_page.p0001.json", build_render_page())

    repo_root = Path(__file__).resolve().parent.parent
    write_json("glossary_payload.json", build_glossary_payload(repo_root))

    write_json("qa_summary.json", build_qa_summary())


if __name__ == "__main__":
    main()
