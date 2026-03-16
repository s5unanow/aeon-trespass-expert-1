"""Build LLM prompts from TranslationBatchV1 and concept constraints."""

from __future__ import annotations

import json

from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1

_SYSTEM_PROMPT = """\
You are an expert board-game rulebook translator specialising in \
English → Russian translation. You translate structured JSON segments \
that may contain inline icon nodes, cross-references, and glossary terms.

RULES — follow every rule exactly:
1. Translate only text nodes (type="text"). Preserve every non-text node \
   (type="icon", "figure_ref", "xref", "line_break", "term_mark") \
   UNCHANGED — same fields, same values, same position relative to \
   surrounding text.
2. Keep the SAME number and ORDER of icon nodes in the output as in the \
   input.  Never add, remove, or reorder icon nodes.
3. Use the EXACT Russian surface forms listed in the terminology section \
   below. If a concept has allowed_surface_forms, pick the grammatically \
   correct one. Never use a forbidden translation.
4. Preserve emphasis marks (bold, italic) on text nodes where appropriate \
   for Russian typography.
5. Output valid JSON matching the schema exactly — no markdown, no \
   commentary, no extra keys.
"""


def build_system_prompt(
    batch: TranslationBatchV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> str:
    """Build the system prompt with terminology constraints."""
    parts = [_SYSTEM_PROMPT]

    if concept_registry and concept_registry.concepts:
        parts.append("\nTERMINOLOGY:")
        for c in concept_registry.concepts:
            entry = (
                f"- {c.source.lemma} → {c.target.lemma}"
                f"  (allowed: {', '.join(c.target.allowed_surface_forms) or c.target.lemma})"
            )
            if c.forbidden_targets:
                entry += f"  FORBIDDEN: {', '.join(c.forbidden_targets)}"
            if c.icon_binding:
                entry += f"  [bound to icon {c.icon_binding}]"
            parts.append(entry)

    return "\n".join(parts)


def build_user_message(batch: TranslationBatchV1) -> str:
    """Build the user message containing segments to translate."""
    segments_payload = []
    for seg in batch.segments:
        seg_dict: dict[str, object] = {
            "segment_id": seg.segment_id,
            "block_type": seg.block_type,
            "source_inline": [
                node.model_dump(mode="json") for node in seg.source_inline
            ],
        }
        if seg.locked_nodes:
            seg_dict["locked_nodes"] = seg.locked_nodes
        if seg.required_concepts:
            seg_dict["required_concepts"] = seg.required_concepts
        if seg.context.prev_heading:
            seg_dict["context"] = {"prev_heading": seg.context.prev_heading}
        segments_payload.append(seg_dict)

    return json.dumps(
        {
            "batch_id": batch.batch_id,
            "source_lang": batch.source_lang,
            "target_lang": batch.target_lang,
            "segments": segments_payload,
        },
        ensure_ascii=False,
        indent=2,
    )


def build_response_schema() -> dict[str, object]:
    """Return the JSON Schema that the LLM response must conform to."""
    inline_node_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "text": {"type": "string"},
            "lang": {"type": "string"},
            "marks": {"type": "array", "items": {"type": "string"}},
            "symbol_id": {"type": "string"},
            "instance_id": {"type": "string"},
            "concept_id": {"type": "string"},
            "surface_form": {"type": "string"},
            "asset_id": {"type": "string"},
            "label": {"type": "string"},
            "target_page_id": {"type": "string"},
            "target_section_id": {"type": "string"},
        },
        "required": ["type"],
        "additionalProperties": False,
    }

    concept_realization_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "concept_id": {"type": "string"},
            "surface_form": {"type": "string"},
        },
        "required": ["concept_id", "surface_form"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "batch_id": {"type": "string"},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "string"},
                        "target_inline": {
                            "type": "array",
                            "items": inline_node_schema,
                        },
                        "concept_realizations": {
                            "type": "array",
                            "items": concept_realization_schema,
                        },
                    },
                    "required": [
                        "segment_id",
                        "target_inline",
                        "concept_realizations",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["batch_id", "segments"],
        "additionalProperties": False,
    }
