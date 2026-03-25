"""Build GlossaryPayloadV1 from concept registry and render pages."""

from __future__ import annotations

from collections import defaultdict

from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.glossary_payload_v1 import GlossaryEntryV1, GlossaryPageRef, GlossaryPayloadV1
from atr_schemas.render_page_v1 import RenderPageV1


def _build_page_refs(
    render_pages: list[RenderPageV1],
) -> dict[str, list[GlossaryPageRef]]:
    """Build reverse index: concept_id -> list of page refs."""
    refs: dict[str, list[GlossaryPageRef]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    for page in render_pages:
        for concept_id in page.glossary_mentions:
            if page.page.id not in seen[concept_id]:
                seen[concept_id].add(page.page.id)
                refs[concept_id].append(
                    GlossaryPageRef(
                        page_id=page.page.id,
                        source_page_number=page.page.source_page_number,
                    )
                )
    return dict(refs)


def build_glossary_payload(
    document_id: str,
    concept_registry: ConceptRegistryV1 | None,
    render_pages: list[RenderPageV1],
) -> GlossaryPayloadV1:
    """Build a glossary payload from all registered concepts."""
    page_refs = _build_page_refs(render_pages)

    entries: list[GlossaryEntryV1] = []
    if concept_registry:
        for concept in concept_registry.concepts:
            entries.append(
                GlossaryEntryV1(
                    concept_id=concept.concept_id,
                    preferred_term=concept.target.lemma,
                    source_term=concept.source.lemma,
                    aliases=list(concept.source.aliases),
                    icon_binding=concept.icon_binding,
                    notes=concept.notes,
                    page_refs=page_refs.get(concept.concept_id, []),
                )
            )

    return GlossaryPayloadV1(document_id=document_id, entries=entries)
