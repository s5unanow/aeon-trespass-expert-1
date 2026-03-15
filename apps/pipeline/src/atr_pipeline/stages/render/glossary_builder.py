"""Build GlossaryPayloadV1 from concept registry and render pages."""

from __future__ import annotations

from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.glossary_payload_v1 import GlossaryEntryV1, GlossaryPayloadV1
from atr_schemas.render_page_v1 import RenderPageV1


def build_glossary_payload(
    document_id: str,
    concept_registry: ConceptRegistryV1 | None,
    render_pages: list[RenderPageV1],
) -> GlossaryPayloadV1:
    """Build a glossary payload from concepts mentioned in render pages."""
    # Collect all concept mentions across pages
    mentioned: set[str] = set()
    for page in render_pages:
        mentioned.update(page.glossary_mentions)

    entries: list[GlossaryEntryV1] = []
    if concept_registry:
        for concept in concept_registry.concepts:
            if concept.concept_id in mentioned or not mentioned:
                entries.append(
                    GlossaryEntryV1(
                        concept_id=concept.concept_id,
                        preferred_term=concept.target.lemma,
                        source_term=concept.source.lemma,
                        aliases=list(concept.source.aliases),
                        icon_binding=concept.icon_binding,
                        notes=concept.notes,
                    )
                )

    return GlossaryPayloadV1(document_id=document_id, entries=entries)
