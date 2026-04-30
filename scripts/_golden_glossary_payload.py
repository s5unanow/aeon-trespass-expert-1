"""Walking-skeleton golden glossary payload builder.

The glossary fixture differs from the per-stage payloads in that it reads
from the live concept registry (`configs/glossary/concepts.toml`) rather
than holding a static literal. Kept in its own sibling module so the
registry-loading boundary is explicit (S5U-711).
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.stages.glossary.registry_loader import load_concept_registry


def build_glossary_payload(repo_root: Path) -> dict[str, object]:
    """Build the glossary fixture payload from the live concept registry.

    All registry concepts are included; only concept.progress has page_refs
    in the wider walking-skeleton scenario, but the entries here just
    flatten the registry's concept metadata.
    """
    registry = load_concept_registry(repo_root / "configs" / "glossary" / "concepts.toml")
    glossary_entries: list[dict[str, object]] = []
    for concept in registry.concepts:
        entry: dict[str, object] = {
            "concept_id": concept.concept_id,
            "preferred_term": concept.target.lemma,
            "source_term": concept.source.lemma,
            "aliases": list(concept.source.aliases),
            "icon_binding": concept.icon_binding,
            "notes": concept.notes or "",
        }
        glossary_entries.append(entry)
    return {"document_id": "walking_skeleton", "entries": glossary_entries}
