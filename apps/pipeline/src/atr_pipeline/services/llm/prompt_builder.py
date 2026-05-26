# ruff: noqa: RUF001  — Cyrillic text in translation examples is intentional.
"""Build LLM prompts from TranslationBatchV1 and concept constraints."""

from __future__ import annotations

import json

from atr_pipeline.services.llm.prompt_style_memory import (
    FORBIDDEN_STYLE_PHRASES,
    STYLE_MEMORY,
)
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1

_SYSTEM_PROMPT = """\
You are an expert board-game rulebook translator specialising in \
English → Russian translation. You translate structured JSON segments \
that may contain inline icon nodes, cross-references, and glossary terms.

RULES — follow every rule exactly:
1. Translate only text nodes (type="text"). Copy every non-text node \
   (type="icon", "figure_ref", "xref", "line_break", "term_mark") \
   UNCHANGED — same fields, same values, same position relative to \
   surrounding text.
2. The output MUST contain EXACTLY the same icon nodes as the input — \
   same count, same order, same symbol_id and instance_id values. \
   NEVER invent, add, or remove icon nodes. If the source has 0 icons, \
   the target must have 0 icons.
3. Use the EXACT Russian surface forms listed in the terminology section \
   below. If a concept has allowed_surface_forms, pick the grammatically \
   correct one. Never use a forbidden translation.
4. Preserve emphasis marks (bold, italic) on text nodes where appropriate \
   for Russian typography.
5. Output valid JSON matching the schema exactly — no markdown, no \
   commentary, no extra keys.
6. Produce publishable Russian, not merely structurally valid Russian. \
   Preserve meaning, but recast syntax when Russian needs it: split \
   overloaded sentences, resolve fragments from adjacent context, and \
   choose idiomatic collocations over English word order.
7. Use a mythic-fantasy / ancient-Greek gamebook register. Avoid modern \
   administrative or business phrasing unless the source requires it. \
   Demonyms and generic nouns are lowercase in running Russian prose \
   unless they are true proper names or formal UI/card titles.
8. For gamebook commands, "Note passage NNNN" means record/mark the \
   passage for later; prefer "Отметьте" or "Запишите", not \
   "Запомните". "See NNNN" means navigate to that passage; prefer \
   "Перейдите к NNNN", not "См. NNNN". For short fragments such as \
   "But only a few", use the adjacent context to restore the antecedent \
   before translating.
9. Do not add new plot facts, but do make concise implicit antecedents, \
   physical causes, and scene relations explicit when Russian needs them.
"""


def build_system_prompt(
    batch: TranslationBatchV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> str:
    """Build the system prompt with terminology constraints."""
    parts = [_SYSTEM_PROMPT, STYLE_MEMORY, FORBIDDEN_STYLE_PHRASES]

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
    segment_texts = [_inline_text(seg.source_inline) for seg in batch.segments]
    for idx, seg in enumerate(batch.segments):
        seg_dict: dict[str, object] = {
            "segment_id": seg.segment_id,
            "block_type": seg.block_type,
            "source_inline": [node.model_dump(mode="json") for node in seg.source_inline],
        }
        if seg.block_type == "narrative_group":
            seg_dict["translation_unit"] = "full_section"
            seg_dict["section_source_text"] = _section_source_text(seg.source_inline)
            seg_dict["block_boundary_contract"] = (
                "Copy every xref marker whose target_section_id starts with "
                "'translation-block:' unchanged. Translate the prose between "
                "markers as one continuous section, then keep each translated "
                "block after its corresponding marker."
            )
        source_context = {
            "prev_segment_text": segment_texts[idx - 1] if idx > 0 else "",
            "next_segment_text": segment_texts[idx + 1] if idx + 1 < len(segment_texts) else "",
        }
        if source_context["prev_segment_text"] or source_context["next_segment_text"]:
            seg_dict["source_context"] = source_context
        if _is_short_fragment(segment_texts[idx]):
            seg_dict["short_fragment_requires_context"] = True
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


def _inline_text(nodes: object) -> str:
    """Return plain text from an inline-node sequence for prompt context."""
    if not isinstance(nodes, list):
        return ""
    parts: list[str] = []
    for node in nodes:
        text = getattr(node, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _section_source_text(nodes: object) -> str:
    """Return readable block-delimited text for narrative-group prompts."""
    if not isinstance(nodes, list):
        return ""
    blocks: list[str] = []
    current_label = ""
    current_parts: list[str] = []

    def flush() -> None:
        if current_label or current_parts:
            text = "".join(current_parts).strip()
            if text:
                blocks.append(f"[{current_label}]\n{text}" if current_label else text)

    for node in nodes:
        if getattr(node, "type", "") == "xref" and getattr(
            node, "target_section_id", ""
        ).startswith("translation-block:"):
            flush()
            current_label = getattr(node, "target_section_id", "").removeprefix(
                "translation-block:"
            )
            current_parts = []
            continue
        text = getattr(node, "text", None)
        if isinstance(text, str):
            current_parts.append(text)
        elif getattr(node, "type", "") == "line_break":
            current_parts.append("\n")
    flush()
    return "\n\n".join(blocks)


def _is_short_fragment(text: str) -> bool:
    """True for source snippets likely to need neighboring context."""
    words = [w for w in text.replace("—", " ").replace("-", " ").split() if w]
    return 0 < len(words) <= 5


def build_few_shot_examples() -> list[dict[str, str]]:
    """Return few-shot example pairs for translation consistency.

    Each example is a dict with "user" (source JSON) and "assistant"
    (target JSON) keys, demonstrating correct translation style, icon
    preservation, and terminology usage.
    """
    return [
        {
            "user": json.dumps(
                {
                    "batch_id": "example_1",
                    "source_lang": "en",
                    "target_lang": "ru",
                    "segments": [
                        {
                            "segment_id": "ex_heading",
                            "block_type": "heading",
                            "source_inline": [
                                {"type": "text", "text": "Battle Phase"},
                            ],
                        },
                        {
                            "segment_id": "ex_para",
                            "block_type": "paragraph",
                            "source_inline": [
                                {"type": "text", "text": "Each Argonaut has a "},
                                {"type": "text", "text": "Danger", "marks": ["bold"]},
                                {"type": "text", "text": " "},
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i1"},
                                {
                                    "type": "text",
                                    "text": " stat on their Triskelion. When you gain ",
                                },
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i2"},
                                {"type": "text", "text": ", rotate the dial clockwise."},
                            ],
                            "locked_nodes": ["i1", "i2"],
                            "required_concepts": ["concept.danger"],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "assistant": json.dumps(
                {
                    "batch_id": "example_1",
                    "segments": [
                        {
                            "segment_id": "ex_heading",
                            "target_inline": [
                                {"type": "text", "text": "Фаза Битвы"},
                            ],
                            "concept_realizations": [],
                        },
                        {
                            "segment_id": "ex_para",
                            "target_inline": [
                                {"type": "text", "text": "У каждого Аргонавта есть показатель "},
                                {"type": "text", "text": "Опасность", "marks": ["bold"]},
                                {"type": "text", "text": " "},
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i1"},
                                {"type": "text", "text": " на Трискелионе. Когда вы получаете "},
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i2"},
                                {"type": "text", "text": ", поверните диск по часовой стрелке."},
                            ],
                            "concept_realizations": [
                                {"concept_id": "concept.danger", "surface_form": "Опасность"},
                            ],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
        {
            "user": json.dumps(
                {
                    "batch_id": "example_2",
                    "source_lang": "en",
                    "target_lang": "ru",
                    "segments": [
                        {
                            "segment_id": "ex_list",
                            "block_type": "paragraph",
                            "source_inline": [
                                {"type": "text", "text": "You must gain 1 "},
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i1"},
                                {
                                    "type": "text",
                                    "text": " for each die you decide to re-roll. Using ",
                                },
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i2"},
                                {"type": "text", "text": ", you can re-roll "},
                                {"type": "text", "text": "Attack Rolls", "marks": ["bold"]},
                                {"type": "text", "text": " and "},
                                {"type": "text", "text": "Evasion Rolls", "marks": ["bold"]},
                                {"type": "text", "text": "."},
                            ],
                            "locked_nodes": ["i1", "i2"],
                            "required_concepts": ["concept.fate"],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "assistant": json.dumps(
                {
                    "batch_id": "example_2",
                    "segments": [
                        {
                            "segment_id": "ex_list",
                            "target_inline": [
                                {"type": "text", "text": "Вы должны получить 1 "},
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i1"},
                                {
                                    "type": "text",
                                    "text": " за каждый кубик, который вы решите "
                                    "перебросить. Используя ",
                                },
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i2"},
                                {"type": "text", "text": ", вы можете перебросить "},
                                {"type": "text", "text": "Броски Атаки", "marks": ["bold"]},
                                {"type": "text", "text": " и "},
                                {"type": "text", "text": "Броски Уклонения", "marks": ["bold"]},
                                {"type": "text", "text": "."},
                            ],
                            "concept_realizations": [
                                {"concept_id": "concept.fate", "surface_form": "Судьба"},
                            ],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


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
