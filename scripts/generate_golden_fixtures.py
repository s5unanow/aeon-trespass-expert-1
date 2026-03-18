#!/usr/bin/env python3
"""Generate golden expected JSON fixtures for the walking skeleton.

These are the expected outputs that integration tests compare against.
"""

import json
from pathlib import Path

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

    # --- source_manifest.json ---
    write_json(
        "source_manifest.json",
        {
            "schema_version": "source_manifest.v1",
            "document_id": "walking_skeleton",
            "source_pdf_sha256": "__DYNAMIC__",
            "page_count": 1,
            "pages": [{"page_id": "p0001", "page_number": 1, "raster_ref": None}],
            "config_hash": "",
            "extractor_version": "",
        },
    )

    # --- native_page.p0001.json ---
    write_json(
        "native_page.p0001.json",
        {
            "schema_version": "native_page.v1",
            "document_id": "walking_skeleton",
            "page_id": "p0001",
            "page_number": 1,
            "dimensions_pt": {"width": 595.2, "height": 841.8},
            "words": "__DYNAMIC__",
            "spans": [],
            "image_blocks": "__DYNAMIC__",
            "extractor_meta": {"engine": "pymupdf"},
        },
    )

    # --- symbol_matches.p0001.json ---
    write_json(
        "symbol_matches.p0001.json",
        {
            "schema_version": "symbol_match_set.v1",
            "document_id": "walking_skeleton",
            "page_id": "p0001",
            "matches": [
                {
                    "symbol_id": "sym.progress",
                    "instance_id": "syminst.p0001.01",
                    "bbox": {"x0": 130.0, "y0": 112.0, "x1": 146.0, "y1": 128.0},
                    "score": "__DYNAMIC__",
                    "source_asset_id": "",
                    "inline": True,
                }
            ],
            "unmatched_candidates": 0,
        },
    )

    # --- page_ir.en.p0001.json ---
    write_json(
        "page_ir.en.p0001.json",
        {
            "schema_version": "page_ir.v1",
            "document_id": "walking_skeleton",
            "page_id": "p0001",
            "page_number": 1,
            "language": "en",
            "dimensions_pt": {"width": 595.2, "height": 841.8},
            "section_hint": None,
            "blocks": [
                {
                    "type": "heading",
                    "block_id": "p0001.b001",
                    "bbox": None,
                    "level": 2,
                    "children": [
                        {
                            "type": "text",
                            "text": "Attack Test",
                            "marks": [],
                            "lang": "en",
                            "source_word_ids": [],
                        },
                    ],
                    "translatable": True,
                    "style_hint": None,
                    "source_ref": None,
                    "annotations": None,
                },
                {
                    "type": "paragraph",
                    "block_id": "p0001.b002",
                    "bbox": None,
                    "children": [
                        {
                            "type": "text",
                            "text": "Gain 1 ",
                            "marks": [],
                            "lang": "en",
                            "source_word_ids": [],
                        },
                        {
                            "type": "icon",
                            "symbol_id": "sym.progress",
                            "instance_id": "syminst.p0001.01",
                            "bbox": None,
                            "display_hint": {},
                            "source_asset_id": "",
                        },
                        {
                            "type": "text",
                            "text": " Progress.",
                            "marks": [],
                            "lang": "en",
                            "source_word_ids": [],
                        },
                    ],
                    "translatable": True,
                    "style_hint": None,
                    "source_ref": None,
                    "annotations": None,
                },
            ],
            "assets": [],
            "reading_order": ["p0001.b001", "p0001.b002"],
            "confidence": None,
            "qa_state": None,
            "provenance": None,
        },
    )

    # --- translation_batch.p0001.json ---
    write_json(
        "translation_batch.p0001.json",
        {
            "schema_version": "translation_batch.v1",
            "batch_id": "tr.p0001.01",
            "source_lang": "en",
            "target_lang": "ru",
            "prompt_profile": "translate_rules_ru.v1",
            "segments": [
                {
                    "segment_id": "p0001.b001",
                    "block_type": "heading",
                    "source_inline": [
                        {
                            "type": "text",
                            "text": "Attack Test",
                            "marks": [],
                            "lang": "en",
                            "source_word_ids": [],
                        },
                    ],
                    "context": {"page_id": "p0001", "section_path": [], "prev_heading": ""},
                    "required_concepts": [],
                    "forbidden_targets": [],
                    "locked_nodes": [],
                    "source_checksum": "",
                },
                {
                    "segment_id": "p0001.b002",
                    "block_type": "paragraph",
                    "source_inline": [
                        {
                            "type": "text",
                            "text": "Gain 1 ",
                            "marks": [],
                            "lang": "en",
                            "source_word_ids": [],
                        },
                        {
                            "type": "icon",
                            "symbol_id": "sym.progress",
                            "instance_id": "syminst.p0001.01",
                            "bbox": None,
                            "display_hint": {},
                            "source_asset_id": "",
                        },
                        {
                            "type": "text",
                            "text": " Progress.",
                            "marks": [],
                            "lang": "en",
                            "source_word_ids": [],
                        },
                    ],
                    "context": {
                        "page_id": "p0001",
                        "section_path": [],
                        "prev_heading": "Attack Test",
                    },
                    "required_concepts": ["concept.progress"],
                    "forbidden_targets": [],
                    "locked_nodes": ["sym.progress"],
                    "source_checksum": "",
                },
            ],
        },
    )

    # --- translation_result.p0001.json ---
    write_json(
        "translation_result.p0001.json",
        {
            "schema_version": "translation_result.v1",
            "batch_id": "tr.p0001.01",
            "segments": [
                {
                    "segment_id": "p0001.b001",
                    "target_inline": [
                        {
                            "type": "text",
                            "text": "Проверка атаки",
                            "marks": [],
                            "lang": "ru",
                            "source_word_ids": [],
                        },
                    ],
                    "concept_realizations": [],
                },
                {
                    "segment_id": "p0001.b002",
                    "target_inline": [
                        {
                            "type": "text",
                            "text": "Получите 1 ",
                            "marks": [],
                            "lang": "ru",
                            "source_word_ids": [],
                        },
                        {
                            "type": "icon",
                            "symbol_id": "sym.progress",
                            "instance_id": "syminst.p0001.01",
                            "bbox": None,
                            "display_hint": {},
                            "source_asset_id": "",
                        },
                        {
                            "type": "text",
                            "text": " Прогресс.",
                            "marks": [],
                            "lang": "ru",
                            "source_word_ids": [],
                        },
                    ],
                    "concept_realizations": [
                        {"concept_id": "concept.progress", "surface_form": "Прогресс"},
                    ],
                },
            ],
        },
    )

    # --- page_ir.ru.p0001.json ---
    write_json(
        "page_ir.ru.p0001.json",
        {
            "schema_version": "page_ir.v1",
            "document_id": "walking_skeleton",
            "page_id": "p0001",
            "page_number": 1,
            "language": "ru",
            "dimensions_pt": {"width": 595.2, "height": 841.8},
            "section_hint": None,
            "blocks": [
                {
                    "type": "heading",
                    "block_id": "p0001.b001",
                    "bbox": None,
                    "level": 2,
                    "children": [
                        {
                            "type": "text",
                            "text": "Проверка атаки",
                            "marks": [],
                            "lang": "ru",
                            "source_word_ids": [],
                        },
                    ],
                    "translatable": True,
                    "style_hint": None,
                    "source_ref": None,
                    "annotations": None,
                },
                {
                    "type": "paragraph",
                    "block_id": "p0001.b002",
                    "bbox": None,
                    "children": [
                        {
                            "type": "text",
                            "text": "Получите 1 ",
                            "marks": [],
                            "lang": "ru",
                            "source_word_ids": [],
                        },
                        {
                            "type": "icon",
                            "symbol_id": "sym.progress",
                            "instance_id": "syminst.p0001.01",
                            "bbox": None,
                            "display_hint": {},
                            "source_asset_id": "",
                        },
                        {
                            "type": "text",
                            "text": " Прогресс.",
                            "marks": [],
                            "lang": "ru",
                            "source_word_ids": [],
                        },
                    ],
                    "translatable": True,
                    "style_hint": None,
                    "source_ref": None,
                    "annotations": None,
                },
            ],
            "assets": [],
            "reading_order": ["p0001.b001", "p0001.b002"],
            "confidence": None,
            "qa_state": None,
            "provenance": None,
        },
    )

    # --- render_page.p0001.json ---
    write_json(
        "render_page.p0001.json",
        {
            "schema_version": "render_page.v1",
            "document_version": "",
            "page": {
                "id": "p0001",
                "title": "Проверка атаки",
                "section_path": [],
                "source_page_number": 1,
            },
            "nav": {"prev": None, "next": None, "parent_section": ""},
            "blocks": [
                {
                    "kind": "heading",
                    "id": "p0001.b001",
                    "level": 2,
                    "children": [
                        {"kind": "text", "text": "Проверка атаки", "marks": []},
                    ],
                },
                {
                    "kind": "paragraph",
                    "id": "p0001.b002",
                    "children": [
                        {"kind": "text", "text": "Получите 1 ", "marks": []},
                        {"kind": "icon", "symbol_id": "sym.progress", "alt": "Прогресс"},
                        {"kind": "text", "text": " Прогресс.", "marks": []},
                    ],
                },
            ],
            "figures": {},
            "glossary_mentions": ["concept.progress"],
            "search": {
                "raw_text": "Проверка атаки Получите 1 Прогресс",
                "normalized_terms": ["проверка", "атака", "получить", "прогресс"],
            },
            "source_map": {
                "page_id": "p0001",
                "block_refs": ["p0001.b001", "p0001.b002"],
            },
            "build_meta": None,
        },
    )

    # --- glossary_payload.json ---
    write_json(
        "glossary_payload.json",
        {
            "document_id": "walking_skeleton",
            "entries": [
                {
                    "concept_id": "concept.progress",
                    "preferred_term": "Прогресс",
                    "source_term": "Progress",
                    "aliases": [],
                    "icon_binding": "sym.progress",
                    "notes": "",
                }
            ],
        },
    )

    # --- qa_summary.json ---
    write_json(
        "qa_summary.json",
        {
            "schema_version": "qa_summary.v1",
            "document_id": "walking_skeleton",
            "run_id": "",
            "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
            "blocking": False,
            "record_refs": [],
        },
    )


if __name__ == "__main__":
    main()
